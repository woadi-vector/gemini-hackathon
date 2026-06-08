"""Tool Selection Quality Eval — binary pass/fail.

For each fixture, asks: did the agent call the tools the case required?
Critical miss = FAIL (e.g., approved a typosquat without calling verify_vendor).
Optional-tool-skipped = PASS (e.g., didn't call check_employee_pattern on a $12 expense).

The rubric is fixture-specific via expected_tools.must_include and expected_tools.must_not_include.
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


TOOL_SELECTION_RUBRIC = """You are evaluating whether an AP expense triage agent called the right tools for an expense.

Available tools the agent could call:
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

Did the agent select appropriate tools?

Output rules:
- PASS if all "must_include" tools were called AND none of the "must_not_include" tools were called. Extra tools beyond the required list are acceptable.
- FAIL if any "must_include" tool was skipped (the agent missed something it needed to check).
- FAIL if any "must_not_include" tool was called (the agent did something it shouldn't have).

Respond with ONLY one word: PASS or FAIL."""


def _extract_tools_called_from_response(response_text: str) -> list[str]:
    """Pull the tools_called array from the agent's final JSON output."""
    if not response_text:
        return []
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[-1].startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    # Find the tools_called array
    match = re.search(r'"tools_called"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if not match:
        return []
    inner = match.group(1)
    tools = re.findall(r'"([^"]+)"', inner)
    return tools


async def run_agent_and_capture(fixture: dict) -> dict:
    """Run the agent on a fixture and capture its tool calls + final response."""
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
        "expected_tools": fixture["expected_tools"],
        "tools_called": _extract_tools_called_from_response(final_text),
        "raw_response": final_text,
    }


async def evaluate_one(judge: LLM, run_result: dict) -> dict:
    """Send one run to the judge and get back PASS/FAIL."""
    expected = run_result["expected_tools"]

    prompt = TOOL_SELECTION_RUBRIC.format(
        expense_json=json.dumps(run_result["expense"], indent=2),
        case_label=run_result["label"],
        case_notes=expected.get("notes", "(no notes)"),
        must_include=expected.get("must_include", []),
        must_not_include=expected.get("must_not_include", []),
        actual_tools_called=run_result["tools_called"],
    )

    classifier = create_classifier(
        name="tool_selection_quality",
        llm=judge,
        prompt_template=prompt,
        choices={"PASS": 1.0, "FAIL": 0.0},
    )

    scores = await classifier.async_evaluate(eval_input={})
    score = scores[0] if isinstance(scores, list) else scores

    return {
        "fixture_id": run_result["fixture_id"],
        "must_include": expected.get("must_include", []),
        "actual_tools": run_result["tools_called"],
        "verdict": score.label,
        "score": score.score,
        "explanation": getattr(score, "explanation", None),
    }


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

    print("=" * 70)
    print("TOOL SELECTION QUALITY EVAL")
    print(f"Agent model: {AGENT_MODEL}  |  Judge model: {JUDGE_MODEL}")
    print("=" * 70)

    results = []
    for fixture in fixtures:
        print(f"\n[{fixture['id']}] Running agent...")
        run_result = await run_agent_and_capture(fixture)
        print(f"  Required: {run_result['expected_tools']['must_include']}")
        print(f"  Called:   {run_result['tools_called']}")

        print(f"  Sending to judge...")
        verdict = await evaluate_one(judge, run_result)
        results.append(verdict)
        print(f"  Verdict: {verdict['verdict']} (score: {verdict['score']})")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    passes = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\n{passes}/{len(results)} passed\n")
    for r in results:
        marker = "✓" if r["verdict"] == "PASS" else "✗"
        missing = set(r["must_include"]) - set(r["actual_tools"])
        miss_note = f"  (missing: {missing})" if missing else ""
        print(f"  {marker} {r['fixture_id']}: required={r['must_include']}, called={r['actual_tools']}{miss_note}")


if __name__ == "__main__":
    asyncio.run(main())