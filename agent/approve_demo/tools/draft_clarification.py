# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Clarification drafter — generates a specific question to the submitter when confidence is low."""

from google.adk.tools import ToolContext


async def draft_clarification(
    expense_summary: str, specific_concern: str, tool_context: ToolContext
) -> str:
    """Draft a specific clarifying question to send back to the expense submitter.

    Use this tool when the other checks have surfaced a concrete ambiguity that
    the submitter could resolve with a short answer. Never call this for generic
    "looks weird" cases — only when you can name the exact ambiguity in one
    sentence. The question must be answerable in under 30 seconds by the
    submitter.

    Args:
      expense_summary: A one-line description of the expense (vendor, amount, date).
      specific_concern: The exact ambiguity you want resolved, in one sentence.
        Bad: "this looks suspicious." Good: "the $480 amount is one dollar
        under the $500 receipt threshold, and you've submitted three similar
        amounts to the same vendor in 10 days."
      tool_context: ADK tool context (unused).

    Returns:
      Text containing the drafted clarification question, anchored to the
      specific concern. Also returns a specificity score — high if the question
      cites concrete details, low if it's generic.
    """
    # STUB — replace Day 3 with a Gemini sub-call that generates the actual
    # natural-language question with full context

    if not specific_concern or len(specific_concern.strip()) < 20:
        return (
            "REJECTED: specific_concern is missing or too vague. "
            "Refusing to draft a generic question. "
            "Re-evaluate the expense and call this tool only when you can "
            "name the exact ambiguity in one sentence. "
            "Specificity score: 0.0."
        )

    # Crude scoring: longer, more concrete concerns → higher specificity
    word_count = len(specific_concern.split())
    has_dollar = "$" in specific_concern
    has_specifics = any(w[0].isdigit() for w in specific_concern.split())

    specificity = 0.5
    if word_count >= 15:
        specificity += 0.15
    if has_dollar or has_specifics:
        specificity += 0.20
    specificity = min(specificity, 0.95)

    draft = (
        f"Drafted question to submitter:\n"
        f"\n"
        f"\"Hi — quick question about your recent expense ({expense_summary}). "
        f"{specific_concern} Could you give me a one-line confirmation of the "
        f"business purpose, or let me know if I should re-route this?\"\n"
        f"\n"
        f"Specificity score: {specificity:.2f}."
    )
    return draft