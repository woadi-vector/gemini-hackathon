"""FastAPI wrapper exposing APEX Approve agent via HTTP."""
import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent / "agent"))
from approve_demo.agent import root_agent
from google.adk.runners import InMemoryRunner
from google.genai import types

app = FastAPI(
    title="APEX Approve",
    description=(
        "An agentic AP clerk for small-business expense triage. "
        "Built on Gemini 2.5 Flash, Google ADK, and Arize Phoenix MCP. "
        "POST an expense to /triage to see the agent route it."
    ),
    version="0.1.0",
)


class Expense(BaseModel):
    expense_id: str
    employee_id: str
    vendor: str
    amount: float
    memo: str = ""
    receipt_text: str = ""


@app.get("/")
def root():
    return {
        "service": "APEX Approve",
        "tagline": "An agentic AP clerk that doesn't trust itself blindly.",
        "docs": "/docs",
        "triage_endpoint": "POST /triage",
        "example_payload": {
            "expense_id": "demo_001",
            "employee_id": "emp_42",
            "vendor": "Staples",
            "amount": 47.50,
            "memo": "office supplies",
            "receipt_text": "STAPLES 7-pk pens 12.99 notebook 8.99 ...",
        },
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/triage")
async def triage(expense: Expense) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name="apex_approve")
    session = await runner.session_service.create_session(
        app_name="apex_approve", user_id="api"
    )
    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=json.dumps(expense.model_dump()))],
    )
    final_text = ""
    async for event in runner.run_async(
        user_id="api", session_id=session.id, new_message=user_message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    final_text = part.text
    try:
        if "```" in final_text:
            final_text = final_text.split("```")[1]
            if final_text.startswith("json"):
                final_text = final_text[4:]
        decision = json.loads(final_text.strip())
    except (json.JSONDecodeError, IndexError):
        decision = {"raw_output": final_text, "parse_error": True}
    return {"expense": expense.model_dump(), "decision": decision}
