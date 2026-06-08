# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Clarification drafter — Gemini-powered tailored question generation."""

from __future__ import annotations

import os
from google.adk.tools import ToolContext
from google import genai


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "1",
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    return _client


_CLARIFICATION_PROMPT = """You are drafting a clarifying question from an AP clerk to an employee about a submitted expense. The question should be short, specific, and easy to answer in under 30 seconds.

EXPENSE SUMMARY: {expense_summary}

SPECIFIC CONCERN THAT NEEDS RESOLUTION:
{specific_concern}

Draft a clarifying question following these rules:
- Anchor to the specific concern — name the exact ambiguity (dollar amount, item, vendor name, time, etc.)
- Vary tone naturally — don't always start with the same opener
- Be respectful, not accusatory ("we noticed" / "could you confirm" / "we'd like to verify")
- Keep it to one short paragraph
- End with a specific question that yields a one-line answer
- Do NOT lecture or explain policy

Output ONLY a JSON object with these fields (no markdown fences, no prose):
{{
  "question": "<the drafted question, single short paragraph>",
  "specificity_score": <0.0 to 1.0 — how concretely the question anchors to specific evidence>,
  "estimated_reply_seconds": <integer estimate of how long the employee will need to answer>
}}

Examples of good questions:
- "We noticed your expense at Total Wine and More on 5/17 was at 11:14 PM. Could you confirm the business purpose? The memo says 'client lunch' but the timing and items don't quite match — short note is fine."
- "Your recent expense at Stapels caught our system — that's one letter off from Staples. Was that a typo, or is Stapels a different vendor? One line is plenty."
- "We don't have prior expense history for employee ID emp_99. Could you verify the ID is correct? If you're new, just say new hire and we'll route accordingly."
"""


async def draft_clarification(
    expense_summary: str, specific_concern: str, tool_context: ToolContext
) -> str:
    """Draft a specific clarifying question to send back to the expense submitter.

    Uses a Gemini sub-call to generate a tailored question rather than a templated
    one. The question varies in tone and structure based on the concern type
    (typosquat, mismatch, missing history) and anchors to the specific evidence.

    Use this tool when the other checks have surfaced a concrete ambiguity that
    the submitter could resolve with a short answer. Never call this for generic
    "looks weird" cases — only when you can name the exact ambiguity in one
    sentence.

    Args:
      expense_summary: A one-line description of the expense (vendor, amount, date).
      specific_concern: The exact ambiguity you want resolved, in one sentence.
      tool_context: ADK tool context (unused).

    Returns:
      Text containing the drafted clarification question with a specificity
      score and estimated reply time.
    """
    if not specific_concern or len(specific_concern.strip()) < 20:
        return (
            "REJECTED: specific_concern is missing or too vague. "
            "Refusing to draft a generic question. Re-evaluate the expense and "
            "call this tool only when you can name the exact ambiguity in one "
            "sentence. Specificity score: 0.0."
        )

    if not expense_summary or len(expense_summary.strip()) < 10:
        return (
            "REJECTED: expense_summary is missing or too short. "
            "Cannot draft a clarifying question without the expense context. "
            "Specificity score: 0.0."
        )

    client = _get_client()
    prompt = _CLARIFICATION_PROMPT.format(
        expense_summary=expense_summary,
        specific_concern=specific_concern,
    )

    try:
        response = await client.aio.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        result_text = response.text.strip() if response.text else ""
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            if lines and lines[-1].startswith("```"):
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            result_text = "\n".join(lines)
        return f"Drafted clarification question (Gemini-generated):\n{result_text}"
    except Exception as e:
        return (
            f"Clarification drafting failed due to error: {type(e).__name__}. "
            f"Recommend escalating to manual review with the original concern: "
            f"'{specific_concern[:200]}'. Specificity score: 0.30."
        )