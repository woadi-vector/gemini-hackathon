"""Routing Decision Quality Eval — binary pass/fail.

Reads each fixture's expected_route and compares against the agent's actual route
extracted from its final response. A Gemini Pro judge is used (rather than direct
string compare) because it can reason about *why* the routes match or differ, which
gives Phoenix's dashboard richer explanations to surface.

This eval is the cleanest signal of correctness — it has ground truth in the
fixture file, and binary scoring makes pass/fail moments unambiguous in the demo.
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


# Gemini 2.5 Pro as the judge — more discerning than Flash, still cheap on Vertex
JUDGE_MODEL = "gemini-2.5-pro"
AGENT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


# The judge's rubric. Binary classification: PASS or FAIL.
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
- PASS if the agent's route matches the expected route exactly, OR if the agent's route is defensibly close (e.g., agent picked "clarify" when "flag" was expected, both express concern over the expense).
- FAIL if the agent's route contradicts the expected route (e.g., expected "flag" but agent picked "approve").
- For "approve" vs "clarify" disagreements, FAIL — these are opposite stances (approving vs asking for more info).
- For "flag" vs "clarify" disagreements, PASS — both reflect concern.

Respond with ONLY one word: PASS or FAIL."""


def _extract_route_from_response(response_text: str) -> str:
    """Pull the route field from the agent's final JSON output."""
    if not response_text:
        return "unknown"
    # Strip markdown fences
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[-1].startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    # Find a JSON object in the text
    match = re.search(r'\{[^{}]*"route"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1)
    return "unknown"


def _extract_reasoning_from_response(response_text: str) -> str:
    """Pull the reasoning field from the agent's final JSON output."""
    if not response_text:
        return ""
    match = re.search(r'"reasoning"\s*:\s*"([^"]+(?:\\.[^"]*)*)"', response_text)
    if match:
        return match.group(1).replace('\\"', '"').replace("\\n", "\n")
    return ""


async def run_agent_and_capture(fixture: dict) -> dict:
    """Run the agent on a fixture and capture its final response."""
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
                    final_text = part.text  # last text wins — final synthesis

    return {
        "fixture_id": fixture["id"],
        "label": fixture["label"],
        "expense": fixture["expense"],
        "expected_route": fixture["expected_route"],
        "agent_route": _extract_route_from_response(final_text),
        "agent_reasoning": _extract_reasoning_from_response(final_text),
        "raw_response": final_text,
    }


async def evaluate_one(judge: LLM, run_result: dict) -> dict:
    """Send one run to the judge and get back PASS/FAIL."""
    # Inferred rationale based on the fixture label — gives the judge context
    expected_rationale = run_result["label"]

    prompt = ROUTING_RUBRIC.format(
        expense_json=json.dumps(run_result["expense"], indent=2),
        expected_route=run_result["expected_route"],
        expected_rationale=expected_rationale,
        agent_route=run_result["agent_route"],
        agent_reasoning=run_result["agent_reasoning"] or "(no reasoning extracted)",
    )

    # Use Phoenix's classifier with binary labels
    classifier = create_classifier(
        name="routing_correctness",
        llm=judge,
        prompt_template=prompt,
        choices={"PASS": 1.0, "FAIL": 0.0},
    )

    scores = await classifier.async_evaluate(eval_input={})
    score = scores[0] if isinstance(scores, list) else scores
    return {
        "fixture_id": run_result["fixture_id"],
        "expected_route": run_result["expected_route"],
        "agent_route": run_result["agent_route"],
        "verdict": score.label,
        "score": score.score,
        "explanation": getattr(score, "explanation", None),
    }


async def main():
    fixtures_path = REPO_ROOT / "fixtures" / "expenses.json"
    with open(fixtures_path) as f:
        fixtures = json.load(f)

    # Phoenix's factory auto-injects GOOGLE_API_KEY if present, which collides
    # with Vertex auth. Strip it for the duration of judge initialization.
    os.environ.pop("GOOGLE_API_KEY", None)

    # Initialize the judge LLM with Vertex
    judge = LLM(
        provider="google",
        model=JUDGE_MODEL,
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )

    print("=" * 70)
    print("ROUTING DECISION QUALITY EVAL")
    print(f"Agent model: {AGENT_MODEL}  |  Judge model: {JUDGE_MODEL}")
    print("=" * 70)

    results = []
    for fixture in fixtures:
        print(f"\n[{fixture['id']}] Running agent...")
        run_result = await run_agent_and_capture(fixture)
        print(f"  Expected: {run_result['expected_route']}  |  Agent: {run_result['agent_route']}")

        print(f"  Sending to judge...")
        verdict = await evaluate_one(judge, run_result)
        results.append(verdict)
        print(f"  Verdict: {verdict['verdict']} (score: {verdict['score']})")

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    passes = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"\n{passes}/{len(results)} passed\n")
    for r in results:
        marker = "✓" if r["verdict"] == "PASS" else "✗"
        print(f"  {marker} {r['fixture_id']}: expected={r['expected_route']}, got={r['agent_route']}")


if __name__ == "__main__":
    asyncio.run(main())