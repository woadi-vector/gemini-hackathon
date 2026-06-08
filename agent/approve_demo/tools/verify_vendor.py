# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Vendor verification tool — Gemini-powered typosquat detection and category inference."""

from __future__ import annotations

import os
from google.adk.tools import ToolContext
from google import genai


# Known-vendor list. Day 4 work could move this to a database; for the demo it's fine here.
_KNOWN_VENDORS = {
    "Staples": {"category": "office_supplies", "tax_id": "12-3456789"},
    "Amazon": {"category": "various", "tax_id": "91-1646860"},
    "FedEx": {"category": "shipping", "tax_id": "71-0427007"},
    "Delta Air Lines": {"category": "travel", "tax_id": "58-0218548"},
    "Marriott": {"category": "lodging", "tax_id": "52-2055918"},
    "Best Buy Business": {"category": "equipment", "tax_id": "41-0907483"},
    "Office Depot": {"category": "office_supplies", "tax_id": "59-2663954"},
    "Uber": {"category": "transport", "tax_id": "45-2647441"},
    "United Airlines": {"category": "travel", "tax_id": "36-2675207"},
    "Hilton": {"category": "lodging", "tax_id": "36-3402549"},
}


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


_VENDOR_ANALYSIS_PROMPT = """You are evaluating a vendor name for an expense report. Determine:

1. Whether the vendor is a recognizable legitimate business
2. Whether it might be a typosquat (one or two letters off from a well-known vendor)
3. What expense category it likely belongs to

VENDOR NAME: {vendor_name}

KNOWN-VENDOR LIST (the approved vendors for this business):
{known_vendors_list}

Output ONLY a JSON object with these fields (no markdown fences, no prose):
{{
  "recognized_legitimate": true | false,
  "typosquat_risk": true | false,
  "likely_typosquat_of": "<known vendor name, or null>",
  "inferred_category": "<office_supplies | travel | lodging | meals_entertainment | equipment | shipping | transport | other>",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<one sentence citing the specific evidence — typosquat distance, name match, category cues>"
}}

A typosquat is one to three character changes from a well-known vendor name (e.g., "Stapels" → "Staples"). If the vendor name is recognizable (Costco, Target, Walmart) but not on the known-vendor list, mark recognized_legitimate=true but include that fact in reasoning.
"""


async def verify_vendor(vendor_name: str, tool_context: ToolContext) -> str:
    """Check if a vendor is known, flag typosquats, infer category if unknown.

    Uses a Gemini sub-call to do fuzzy matching against the known-vendor list and
    to infer category from context when the vendor isn't explicitly known. This
    is stronger than exact-match because it catches typosquats (one letter off
    from a known vendor) and recognizes major retailers not on the approved list.

    Use this tool for any expense from a vendor whose name you don't immediately
    recognize, or when the vendor name looks slightly off from a familiar name.

    Args:
      vendor_name: The exact vendor name as it appears on the expense.
      tool_context: ADK tool context (unused).

    Returns:
      Text describing whether the vendor is known, typosquat risk (naming the
      likely target), inferred category, and confidence score.
    """
    if not vendor_name or not vendor_name.strip():
        return "Vendor name is empty. Cannot verify. Confidence: 0.20."

    # Exact match short-circuit — saves a model call and is deterministic
    if vendor_name in _KNOWN_VENDORS:
        info = _KNOWN_VENDORS[vendor_name]
        return (
            f"Vendor '{vendor_name}' is in the approved known-vendor list. "
            f"Category: {info['category']}. Tax ID on file: {info['tax_id']}. "
            f"No typosquat risk. Confidence: 0.98."
        )

    # Unknown vendor: use Gemini for fuzzy analysis
    client = _get_client()
    known_list_text = "\n".join(f"- {name} ({info['category']})" for name, info in _KNOWN_VENDORS.items())
    prompt = _VENDOR_ANALYSIS_PROMPT.format(
        vendor_name=vendor_name,
        known_vendors_list=known_list_text,
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
        return f"Vendor analysis (Gemini fuzzy matching against known list):\n{result_text}"
    except Exception as e:
        return (
            f"Vendor verification failed due to error: {type(e).__name__}. "
            f"Vendor '{vendor_name}' is not in the known list and could not be analyzed. "
            f"Confidence: 0.30. Recommend routing to clarify."
        )