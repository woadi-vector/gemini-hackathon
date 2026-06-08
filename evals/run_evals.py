"""Unified eval runner — runs all three Phoenix LLM-as-a-Judge evals against all fixtures.

Replaces the three separate scripts (eval_routing.py, eval_tool_selection.py,
eval_reasoning.py) with a single pass that runs the agent once per fixture and
sends each run to all three judges. ~3x faster, ~3x cheaper, single demo command.

Each fixture produces three Phoenix evaluator traces (routing_correctness,
tool_selection_quality, reasoning_specificity) attached to the same agent trace.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "agent"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from phoenix.evals import LLM, create_classifier  # noqa: E402

from instrumentation import setup_tracing  # noqa: E402
from approve_demo.agent import root_agent  # noqa: E402


JUDGE_MODEL = "gemini-2.5-pro"
AGENT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


# ─────────────────────────────────────────────────────────────────────────────
# RUBRICS
# ─────────────────────────────────────────────────────────────────────────────

ROUTING_RUBRIC = """You are evaluating whether an AP expense triage agent routed an expense correctly.

The agent must choose one of: approve, flag, clarify, reject.
The agent should NEVER output reject (humans decide rejections).

EXPENSE:
{expense_json}

EXPECTED ROUTE (ground truth): {expected_route}
EXPECTED ROUTE RATIONALE: {expected_rationale}

AGENT'S ACTUAL ROUTE: {agent_route}
AGENT'S REASONING:
{agent_reasoning}

Did the agent route correctly?

Output rules:
- PASS if the agent's route matches the expected route exactly, OR if the agent's route is defensibly close (e.g., agent picked "clarify" when "flag" was expected, both express concern).
- FAIL if the agent's route contradicts the expected route (e.g., expected "flag" but agent picked "approve").
- For "approve" vs "clarify" disagreements, FAIL — opposite stances.
- For "flag" vs "clarify" disagreements, PASS — both reflect concern.

Respond with ONLY one word: PASS or FAIL."""


TOOL_SELECTION_RUBRIC = """You are evaluating whether an AP expense triage agent called the right tools for an expense.

Available tools:
- verify_vendor: checks vendor against known list, flags typosquats
- check_employee_pattern: examines history for structuring, drift, anomalies
- check_receipt_coherence: compares memo against receipt for mismatches
- draft_clarification: drafts a question to send back to the submitter

EXPENSE:
{expense_json}

CASE TYPE: {case_label}
CASE NOTES: {case_notes}

TOOLS THE AGENT MUST CALL FOR THIS CASE: {must_include}
TOOLS THE AGENT MUST NOT CALL FOR THIS CASE: {must_not_include}

AGENT'S ACTUAL TOOL CALLS: {actual_tools_called}

Output rules:
- PASS if all "must_include" tools were called AND none of the "must_not_include" tools were called. Extra tools are acceptable.
- FAIL if any "must_include" tool was skipped.
- FAIL if any "must_not_include" tool was called.

Respond with ONLY one word: PASS or FAIL."""


REASONING_RUBRIC = """You are evaluating the SPECIFICITY of an AP expense triage agent's reasoning.

The agent should anchor every claim to specific evidence. Generic-sounding reasoning is the failure mode we are scoring against.

EXPENSE THE AGENT PROCESSED:
{expense_json}

AGENT'S REASONING:
{agent_reasoning}

Grade on this 4-point scale. The bar is HIGH — most reasoning should land between FAIR and GOOD.

EXCELLENT (reserve for outstanding cases — should be rare):
- Cites at least FIVE distinct concrete values from the expense
- Attributes findings to AT LEAST TWO named tools with their specific findings
- Names the underlying mechanism of any concern using PRECISE TERMINOLOGY (e.g., "structuring under $500 threshold", "typosquat against Staples")
- For approvals: explicitly states what was checked and ruled out
- Zero hedging language

GOOD:
- Cites 3-4 specific values
- Names at least one tool with a specific finding
- Mentions the type of issue but may use looser wording
- Minimal hedging

FAIR:
- Cites 1-2 specific values, mostly paraphrasing
- References tools but without specific findings
- Vague about the type of issue
- Some hedging language

POOR:
- Mostly generic prose
- Could apply to many different expenses
- No tool attribution
- Heavy hedging

CRITICAL: a reasoning that misses what the agent SHOULD have caught cannot earn higher than FAIR, regardless of how specific the language is. Anchoring to the wrong evidence is still wrong.

Respond with ONLY one word: EXCELLENT, GOOD, FAIR, or POOR."""


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTORS
# ─────────────────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[-1].startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    return text


def _extract_route(response_text: str) -> str:
    if not response_text:
        return "unknown"
    text = _strip_code_fences(response_text)
    match = re.search(r'"route"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


def _extract_reasoning(response_text: str) -> str:
    if not response_text:
        return ""
    text = _strip_code_fences(response_text)
    match = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if match:
        return match.group(1).replace('\\"', '"').replace("\\n", "\n")
    return ""


def _extract_tools_called(response_text: str) -> list[str]:
    if not response_text:
        return []
    text = _strip_code_fences(response_text)
    match = re.search(r'"tools_called"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


# ─────────────────────────────────────────────────────────────────────────────
# AGENT RUN
# ─────────────────────────────────────────────────────────────────────────────

async def run_agent_and_capture(fixture: dict) -> dict:
    setup_tracing()
    app_name = "apex_approve"
    user_id = "eval_runner"
    session_id = secrets.token_hex(8)

    runner = InMemoryRunner(agent=root_agent, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    exp = fixture["expense"]
    message = (
        f"Triage this expense: employee {exp['employee_id']} submitted a "
        f"{exp['amount']} dollar expense at {exp['vendor']} on {exp['date']}. "
        f"Category: {exp['category']}. "
        f"Memo: {exp['memo']}. "
        f"Receipt text: {exp['receipt_text']}."
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        if hasattr(event, "content") and event.content:
            for part in getattr(event.content, "parts", []) or []:
                if hasattr(part, "text") and part.text:
                    final_text = part.text

    return {
        "fixture_id": fixture["id"],
        "label": fixture["label"],
        "expense": fixture["expense"],
        "expected_route": fixture["expected_route"],
        "expected_tools": fixture["expected_tools"],
        "agent_route": _extract_route(final_text),
        "agent_reasoning": _extract_reasoning(final_text),
        "tools_called": _extract_tools_called(final_text),
        "raw_response": final_text,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVAL DISPATCH
# ─────────────────────────────────────────────────────────────────────────────

async def eval_routing(judge: LLM, run: dict) -> dict:
    prompt = ROUTING_RUBRIC.format(
        expense_json=json.dumps(run["expense"], indent=2),
        expected_route=run["expected_route"],
        expected_rationale=run["label"],
        agent_route=run["agent_route"],
        agent_reasoning=run["agent_reasoning"] or "(no reasoning)",
    )
    classifier = create_classifier(
        name="routing_correctness", llm=judge, prompt_template=prompt,
        choices={"PASS": 1.0, "FAIL": 0.0},
    )
    scores = await classifier.async_evaluate(eval_input={})
    s = scores[0] if isinstance(scores, list) else scores
    return {"name": "routing_correctness", "label": s.label, "score": s.score,
            "explanation": getattr(s, "explanation", None)}


async def eval_tool_selection(judge: LLM, run: dict) -> dict:
    exp_tools = run["expected_tools"]
    prompt = TOOL_SELECTION_RUBRIC.format(
        expense_json=json.dumps(run["expense"], indent=2),
        case_label=run["label"],
        case_notes=exp_tools.get("notes", ""),
        must_include=exp_tools.get("must_include", []),
        must_not_include=exp_tools.get("must_not_include", []),
        actual_tools_called=run["tools_called"],
    )
    classifier = create_classifier(
        name="tool_selection_quality", llm=judge, prompt_template=prompt,
        choices={"PASS": 1.0, "FAIL": 0.0},
    )
    scores = await classifier.async_evaluate(eval_input={})
    s = scores[0] if isinstance(scores, list) else scores
    return {"name": "tool_selection_quality", "label": s.label, "score": s.score,
            "explanation": getattr(s, "explanation", None)}


async def eval_reasoning(judge: LLM, run: dict) -> dict:
    prompt = REASONING_RUBRIC.format(
        expense_json=json.dumps(run["expense"], indent=2),
        agent_reasoning=run["agent_reasoning"] or "(no reasoning)",
    )
    classifier = create_classifier(
        name="reasoning_specificity", llm=judge, prompt_template=prompt,
        choices={"EXCELLENT": 1.0, "GOOD": 0.67, "FAIR": 0.33, "POOR": 0.0},
    )
    scores = await classifier.async_evaluate(eval_input={})
    s = scores[0] if isinstance(scores, list) else scores
    return {"name": "reasoning_specificity", "label": s.label, "score": s.score,
            "explanation": getattr(s, "explanation", None)}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    os.environ.pop("GOOGLE_API_KEY", None)

    fixtures_path = REPO_ROOT / "fixtures" / "expenses.json"
    with open(fixtures_path) as f:
        fixtures = json.load(f)

    judge = LLM(
        provider="google",
        model=JUDGE_MODEL,
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )

    print("=" * 74)
    print(" APEX APPROVE — UNIFIED EVAL RUN")
    print(f" Agent: {AGENT_MODEL}  |  Judge: {JUDGE_MODEL}")
    print(f" Evals: routing_correctness, tool_selection_quality, reasoning_specificity")
    print("=" * 74)

    all_results = []
    for fixture in fixtures:
        print(f"\n[{fixture['id']}] {fixture['label']}")
        print("  Running agent...")
        run = await run_agent_and_capture(fixture)
        print(f"  Route: {run['agent_route']}  |  Tools: {run['tools_called']}")

        print(f"  Running 3 evals...")
        results = await asyncio.gather(
            eval_routing(judge, run),
            eval_tool_selection(judge, run),
            eval_reasoning(judge, run),
        )

        fixture_summary = {"fixture_id": fixture["id"], "label": fixture["label"], "evals": results}
        all_results.append(fixture_summary)

        for r in results:
            marker = "✓" if r["score"] >= 0.67 else ("◐" if r["score"] >= 0.33 else "✗")
            print(f"  {marker} {r['name']}: {r['label']} ({r['score']})")

    # Summary
    print("\n" + "=" * 74)
    print(" RESULTS SUMMARY")
    print("=" * 74)
    print(f"\n{'Fixture':<10} {'Routing':<22} {'Tool Selection':<22} {'Reasoning':<14}")
    print("-" * 74)
    for fr in all_results:
        row = [fr["fixture_id"]]
        for eval_name in ["routing_correctness", "tool_selection_quality", "reasoning_specificity"]:
            r = next((e for e in fr["evals"] if e["name"] == eval_name), None)
            row.append(f"{r['label']} ({r['score']})" if r else "—")
        print(f"{row[0]:<10} {row[1]:<22} {row[2]:<22} {row[3]:<14}")

    # Aggregate scores
    print()
    for eval_name in ["routing_correctness", "tool_selection_quality", "reasoning_specificity"]:
        scores = [next((e["score"] for e in fr["evals"] if e["name"] == eval_name), 0) for fr in all_results]
        avg = sum(scores) / len(scores) if scores else 0
        print(f"  {eval_name}: avg {avg:.2f}")


if __name__ == "__main__":
    asyncio.run(main())