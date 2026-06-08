# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Receipt/memo coherence check — uses Gemini sub-call for semantic comparison."""

from __future__ import annotations

import os
from google.adk.tools import ToolContext
from google import genai


# Lazy-init the genai client so import is cheap and env is loaded by the time we call.
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


_COHERENCE_PROMPT = """You are evaluating whether an expense memo (stated business purpose) is coherent with what a receipt actually shows.

MEMO:
{memo}

RECEIPT:
{receipt_text}

Output ONLY a JSON object with these fields (no markdown fences, no prose):
{{
  "coherent": true | false,
  "confidence": <0.0 to 1.0>,
  "reasoning": "<one sentence citing specific items, amounts, or times from the receipt that support or contradict the memo>"
}}

Be strict. A "client lunch" memo with a liquor-store receipt at 11pm is NOT coherent. A "client lunch" memo with a coffee-shop receipt during business hours IS coherent. Cite specific evidence.
"""


async def check_receipt_coherence(
    memo: str, receipt_text: str, tool_context: ToolContext
) -> str:
    """Compare the stated business purpose against what the receipt actually shows.

    Uses a Gemini sub-call to semantically compare the memo and receipt, rather
    than crude keyword matching. Catches cases like a "client lunch" memo paired
    with a liquor-store receipt at 11pm — the kind of mismatch where the words
    might overlap but the meaning doesn't.

    Use this tool when the expense includes both a memo and receipt_text. Skip
    when either is missing or trivially short.

    Args:
      memo: The employee's stated business purpose for the expense.
      receipt_text: The text content of the receipt (OCR'd or itemized).
      tool_context: ADK tool context (unused).

    Returns:
      Text describing whether memo and receipt are semantically coherent,
      grounded in specific evidence from the receipt, with a confidence score.
    """
    if not memo or not memo.strip() or not receipt_text or not receipt_text.strip():
        return (
            "Cannot evaluate coherence — either memo or receipt is missing or empty. "
            "Confidence: 0.30."
        )

    if len(memo.strip()) < 10 or len(receipt_text.strip()) < 10:
        return (
            "Memo or receipt too short to evaluate coherence reliably. "
            "Confidence: 0.40."
        )

    client = _get_client()
    prompt = _COHERENCE_PROMPT.format(memo=memo, receipt_text=receipt_text)

    try:
        response = await client.aio.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        result_text = response.text.strip() if response.text else ""
        # Strip code fences if the model added them despite instructions
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        return f"Coherence analysis (Gemini semantic comparison):\n{result_text}"

    except Exception as e:
        # If the sub-call fails, fall back to a low-confidence "unknown" rather than
        # silently passing or auto-flagging. Never approve on uncertainty.
        return (
            f"Coherence check failed due to error: {type(e).__name__}. "
            f"Cannot determine coherence. Confidence: 0.30. "
            f"Recommend routing to clarify."
        )