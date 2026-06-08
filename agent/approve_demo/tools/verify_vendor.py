# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Vendor verification tool — checks vendor against known list, flags typosquats."""

from google.adk.tools import ToolContext


# Stub known-vendor list for Day 1. Real data Day 3.
_KNOWN_VENDORS = {
    "Staples": {"category": "office_supplies", "tax_id": "12-3456789"},
    "Amazon": {"category": "various", "tax_id": "91-1646860"},
    "FedEx": {"category": "shipping", "tax_id": "71-0427007"},
    "Delta Air Lines": {"category": "travel", "tax_id": "58-0218548"},
    "Marriott": {"category": "lodging", "tax_id": "52-2055918"},
}


async def verify_vendor(vendor_name: str, tool_context: ToolContext) -> str:
    """Check if a vendor is in the known-vendor list. Flag typosquats and new vendors.

    Use this tool for any expense from a vendor whose name you don't immediately
    recognize from common business vendors, or when the vendor name looks slightly
    off — even one letter different from a familiar name. Typosquats (e.g., "Stapels"
    vs "Staples") are a common fraud vector.

    Args:
      vendor_name: The exact vendor name as it appears on the expense.
      tool_context: ADK tool context (unused).

    Returns:
      Text describing whether the vendor is known, any typosquat risk found
      (naming the similar known vendor), category if known, and a confidence score
      between 0.0 and 1.0.
    """
    # STUB — replace Day 3 with real Levenshtein typosquat detection
    if vendor_name in _KNOWN_VENDORS:
        info = _KNOWN_VENDORS[vendor_name]
        return (
            f"Vendor '{vendor_name}' is in the known-vendor list. "
            f"Category: {info['category']}. Tax ID on file: {info['tax_id']}. "
            f"No typosquat risk detected. Confidence: 0.95."
        )
    return (
        f"Vendor '{vendor_name}' is NOT in the known-vendor list. "
        f"This is either a new vendor or potentially a typosquat. "
        f"Recommend routing to clarify and asking submitter to confirm. "
        f"Confidence: 0.60."
    )