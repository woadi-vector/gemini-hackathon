"""Reasoning Specificity Eval — graded (POOR/FAIR/GOOD/EXCELLENT, mapped 0.0-1.0).

Evaluates whether the agent's reasoning is anchored to specific evidence vs. generic
language. The Whetstone anti-flattery rule made concrete: every claim should cite
specific fields from the expense or specific findings from tools.

This eval is the demo center because it directly demonstrates the failure mode
Arize's product is designed to surface — agents producing confident-sounding
generic prose that doesn't actually reference the data they processed.
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


REASONING_RUBRIC = """You are evaluating the SPECIFICITY of an AP expense triage agent's reasoning.

The agent should anchor every claim to specific evidence. Generic-sounding reasoning is the failure mode we are scoring against.

EXPENSE THE AGENT PROCESSED:
{expense_json}

AGENT'S REASONING:
{agent_reasoning}

Grade on this 4-point scale. The bar is HIGH — most reasoning should land between FAIR and GOOD.

EXCELLENT (reserve for outstanding cases — should be rare):
- Cites at least FIVE distinct concrete values from the expense (e.g., dollar amount, vendor name, date, specific items, employee id, category, exact memo phrase, exact receipt phrase, transaction time)
- Attributes findings to AT LEAST TWO named tools with their actual confidence scores or specific findings
- Names the underlying mechanism of any concern using PRECISE TERMINOLOGY (e.g., "structuring under $500 threshold", "typosquat against Staples", "memo/receipt mismatch", "no employee baseline")
- For approvals: explicitly states what was checked and ruled out, not just what was confirmed
- Zero hedging language

GOOD:
- Cites 3-4 specific values from the expense
- Names at least one tool with a specific finding
- Mentions the type of issue but may use looser wording
- Minimal hedging

FAIR:
- Cites 1-2 specific values, mostly paraphrasing the expense rather than anchoring
- References tools but without specific findings, OR cites findings without tool attribution
- Vague about the type of issue
- Some hedging language

POOR:
- Mostly generic prose
- Could apply to many different expenses
- No tool attribution OR only generic references
- Heavy hedging

CRITICAL: a reasoning that misses what the agent SHOULD have caught (e.g., approves an expense without checking employee history when no history exists) cannot earn higher than FAIR, regardless of how specific the language is. Reasoning that anchors to the wrong evidence is still wrong.

Respond with ONLY one word: EXCELLENT, GOOD, FAIR, or POOR."""


def _extract_reasoning_from_response(response_text: str) -> str:
    """Pull the reasoning field from the agent's final JSON output."""
    if not response_text:
        return ""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[-1].startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    match = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if match:
        return match.group(1).replace('\\"', '"').replace("\\n", "\n")
    return ""


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
        "reasoning": _extract_reasoning_from_response(final_text),
        "raw_response": final_text,
    }


async def evaluate_one(judge: LLM, run_result: dict) -> dict:
    prompt = REASONING_RUBRIC.format(
        expense_json=json.dumps(run_result["expense"], indent=2),
        agent_reasoning=run_result["reasoning"] or "(no reasoning extracted)",
    )

    classifier = create_classifier(
        name="reasoning_specificity",
        llm=judge,
        prompt_template=prompt,
        choices={
            "EXCELLENT": 1.0,
            "GOOD": 0.67,
            "FAIR": 0.33,
            "POOR": 0.0,
        },
    )

    scores = await classifier.async_evaluate(eval_input={})
    score = scores[0] if isinstance(scores, list) else scores

    return {
        "fixture_id": run_result["fixture_id"],
        "verdict": score.label,
        "score": score.score,
        "explanation": getattr(score, "explanation", None),
        "reasoning_excerpt": (run_result["reasoning"] or "")[:120] + "..." if len(run_result.get("reasoning", "")) > 120 else run_result["reasoning"],
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
    print("REASONING SPECIFICITY EVAL")
    print(f"Agent model: {AGENT_MODEL}  |  Judge model: {JUDGE_MODEL}")
    print("=" * 70)

    results = []
    for fixture in fixtures:
        print(f"\n[{fixture['id']}] Running agent...")
        run_result = await run_agent_and_capture(fixture)
        excerpt = run_result["reasoning"][:80] + ("..." if len(run_result["reasoning"]) > 80 else "")
        print(f"  Reasoning excerpt: {excerpt}")

        print(f"  Sending to judge...")
        verdict = await evaluate_one(judge, run_result)
        results.append(verdict)
        print(f"  Verdict: {verdict['verdict']} (score: {verdict['score']})")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    avg_score = sum(r["score"] for r in results) / len(results) if results else 0
    print(f"\nAverage specificity score: {avg_score:.2f} / 1.0\n")
    for r in results:
        print(f"  {r['fixture_id']}: {r['verdict']} ({r['score']})")


if __name__ == "__main__":
    asyncio.run(main())