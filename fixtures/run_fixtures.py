"""Batch-run the fixture expenses through the apex_approve agent."""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
from pathlib import Path

# Make the agent package importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "agent"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from instrumentation import setup_tracing  # noqa: E402
from approve_demo.agent import root_agent  # noqa: E402


def format_expense(expense: dict) -> str:
    """Turn a fixture expense dict into a triage prompt message."""
    return (
        f"Triage this expense: employee {expense['employee_id']} submitted a "
        f"{expense['amount']} dollar expense at {expense['vendor']} on {expense['date']}. "
        f"Category: {expense['category']}. "
        f"Memo: {expense['memo']}. "
        f"Receipt text: {expense['receipt_text']}."
    )


async def run_one(fixture: dict) -> None:
    setup_tracing()
    app_name = "apex_approve"
    user_id = "fixture_runner"
    session_id = secrets.token_hex(8)

    runner = InMemoryRunner(agent=root_agent, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    message = format_expense(fixture["expense"])
    print(f"\n{'=' * 70}")
    print(f"FIXTURE {fixture['id']}: {fixture['label']}")
    print(f"Expected route: {fixture['expected_route']}")
    print(f"{'=' * 70}")

    async for _ in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        pass

    print(f"✓ {fixture['id']} traced. Check Phoenix.\n")


async def main() -> None:
    fixtures_path = Path(__file__).parent / "expenses.json"
    with open(fixtures_path) as f:
        fixtures = json.load(f)

    # Allow running a single fixture by id: python run_fixtures.py exp_002
    if len(sys.argv) > 1:
        target_id = sys.argv[1]
        fixtures = [f for f in fixtures if f["id"] == target_id]
        if not fixtures:
            print(f"No fixture found with id={target_id}")
            return

    for fixture in fixtures:
        await run_one(fixture)
        # Short pause between runs so Phoenix traces sort cleanly
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())