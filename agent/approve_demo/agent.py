# Copyright 2026 Vector Research Labs. Apache-2.0.

import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from dotenv import load_dotenv

from instrumentation import setup_tracing
from approve_demo.prompt import expense_triage_instruction
from approve_demo.tools.verify_vendor import verify_vendor
from approve_demo.tools.check_employee_pattern import check_employee_pattern
from approve_demo.tools.check_receipt_coherence import check_receipt_coherence
from approve_demo.tools.draft_clarification import draft_clarification
from approve_demo.tools.review_past_decisions import review_past_decisions

# Ensure ADK CLI runs (`adk run approve_demo`) load local env and tracing.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
setup_tracing()

_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

root_agent = Agent(
    model=_model,
    name="apex_approve_agent",
    instruction=expense_triage_instruction,
    tools=[
        FunctionTool(func=verify_vendor),
        FunctionTool(func=check_employee_pattern),
        FunctionTool(func=check_receipt_coherence),
        FunctionTool(func=draft_clarification),
        FunctionTool(func=review_past_decisions),
    ],
)