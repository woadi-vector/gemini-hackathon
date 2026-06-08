# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Receipt/memo coherence check — does the stated business purpose match what was actually purchased?"""

from google.adk.tools import ToolContext


async def check_receipt_coherence(
    memo: str, receipt_text: str, tool_context: ToolContext
) -> str:
    """Compare the stated business purpose against what the receipt actually shows.

    Use this tool when the expense includes both a memo (the employee's stated
    business purpose) and receipt_text (OCR or itemized line items). The point
    is to catch mismatches: a memo says "client lunch" but the receipt is from
    a liquor store at 11pm, or a memo says "office supplies" but the receipt
    shows personal electronics.

    Skip this tool when the expense has no receipt text or no memo — there's
    nothing to compare.

    Args:
      memo: The employee's stated business purpose for the expense.
      receipt_text: The text content of the receipt (OCR'd or itemized).
      tool_context: ADK tool context (unused).

    Returns:
      Text describing whether memo and receipt are coherent, listing any
      specific mismatches with the exact tokens that triggered the flag, and
      a confidence score between 0.0 and 1.0.
    """
    # STUB — replace Day 3 with a Gemini sub-call doing real semantic comparison

    memo_lower = memo.lower() if memo else ""
    receipt_lower = receipt_text.lower() if receipt_text else ""

    if not memo_lower or not receipt_lower:
        return (
            "Cannot compare coherence — either memo or receipt is missing. "
            "Confidence: 0.30."
        )

    # Crude keyword-overlap heuristic for Day 1 stub.
    # Real version: Gemini semantic comparison.
    memo_words = set(w.strip(".,;:!?") for w in memo_lower.split() if len(w) > 3)
    receipt_words = set(w.strip(".,;:!?") for w in receipt_lower.split() if len(w) > 3)

    if not memo_words:
        return "Memo too short to evaluate coherence. Confidence: 0.40."

    overlap = memo_words & receipt_words
    overlap_ratio = len(overlap) / len(memo_words)

    # Detect potentially incoherent expense type signals
    personal_signals = {"alcohol", "wine", "beer", "liquor", "tobacco", "cigarette"}
    business_signals = {"office", "client", "meeting", "supplies", "travel", "lodging"}

    personal_hits = personal_signals & receipt_words
    business_hits = business_signals & memo_words

    if business_hits and personal_hits:
        return (
            f"COHERENCE FLAG: memo states business purpose ({', '.join(business_hits)}) "
            f"but receipt contains personal-purchase signals ({', '.join(personal_hits)}). "
            f"Recommend routing to clarify. Confidence: 0.80."
        )

    if overlap_ratio >= 0.3:
        return (
            f"Memo and receipt appear coherent. Shared terms: {', '.join(sorted(overlap)[:5])}. "
            f"Confidence: 0.85."
        )

    return (
        f"Memo and receipt have low keyword overlap ({len(overlap)}/{len(memo_words)} terms). "
        f"Coherence is unclear without deeper review. Confidence: 0.55."
    )