# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Employee pattern check — detects drift, structuring, and aggregate anomalies."""

from google.adk.tools import ToolContext


# Stub employee history for Day 1. Real data Day 3.
# Each employee has a list of recent expense summaries the agent can reason about.
_EMPLOYEE_HISTORY = {
    "emp_42": {
        "name": "Jordan Reese",
        "tenure_months": 14,
        "typical_monthly_spend": 850.00,
        "recent_expenses": [
            {"date": "2026-05-20", "vendor": "Staples", "amount": 47.32, "category": "office_supplies"},
            {"date": "2026-05-18", "vendor": "Delta Air Lines", "amount": 412.00, "category": "travel"},
            {"date": "2026-05-15", "vendor": "Marriott", "amount": 289.00, "category": "lodging"},
        ],
        "policy_violations_last_90d": 0,
    },
    "emp_17": {
        "name": "Sam Holloway",
        "tenure_months": 4,
        "typical_monthly_spend": 1200.00,
        "recent_expenses": [
            {"date": "2026-05-22", "vendor": "Best Buy Business", "amount": 480.00, "category": "equipment"},
            {"date": "2026-05-19", "vendor": "Best Buy Business", "amount": 478.50, "category": "equipment"},
            {"date": "2026-05-14", "vendor": "Best Buy Business", "amount": 485.00, "category": "equipment"},
        ],
        "policy_violations_last_90d": 1,
    },
}


async def check_employee_pattern(
    employee_id: str, tool_context: ToolContext
) -> str:
    """Examine an employee's recent expense history for anomalies.

    Use this tool when an expense's amount, vendor, or category seems unusual
    in isolation, or when you want to see if it fits a broader pattern. This is
    especially useful for catching structuring (multiple expenses just under a
    threshold to avoid receipt requirements), vendor concentration, or sudden
    spend drift from an employee's typical baseline.

    Args:
      employee_id: The employee's identifier (e.g., "emp_42").
      tool_context: ADK tool context (unused).

    Returns:
      Text summarizing the employee's recent history, typical monthly spend,
      any pattern flags (structuring, drift, concentration), and a confidence
      score between 0.0 and 1.0.
    """
    # STUB — replace Day 3 with real pattern analysis (structuring detection,
    # statistical drift, vendor concentration checks)
    if employee_id not in _EMPLOYEE_HISTORY:
        return (
            f"No history found for employee {employee_id}. Either this is a new "
            f"hire (consider extra scrutiny) or the employee ID is wrong. "
            f"Confidence: 0.50."
        )

    emp = _EMPLOYEE_HISTORY[employee_id]
    recent = emp["recent_expenses"]
    summary_lines = [
        f"Employee: {emp['name']} ({employee_id})",
        f"Tenure: {emp['tenure_months']} months",
        f"Typical monthly spend: ${emp['typical_monthly_spend']:.2f}",
        f"Policy violations last 90 days: {emp['policy_violations_last_90d']}",
        f"Recent expenses ({len(recent)}):",
    ]
    for e in recent:
        summary_lines.append(
            f"  - {e['date']}: ${e['amount']:.2f} at {e['vendor']} ({e['category']})"
        )

    # Crude structuring check: 3+ expenses to same vendor in 10 days, each < $500
    vendor_counts: dict[str, list[float]] = {}
    for e in recent:
        vendor_counts.setdefault(e["vendor"], []).append(e["amount"])
    pattern_flags = []
    for vendor, amounts in vendor_counts.items():
        if len(amounts) >= 3 and all(a < 500 for a in amounts):
            total = sum(amounts)
            pattern_flags.append(
                f"STRUCTURING SIGNAL: {len(amounts)} expenses to '{vendor}' "
                f"totaling ${total:.2f}, each under the $500 receipt threshold. "
                f"This pattern often indicates threshold avoidance."
            )

    if pattern_flags:
        summary_lines.append("")
        summary_lines.append("PATTERN FLAGS:")
        summary_lines.extend(pattern_flags)
        summary_lines.append("Confidence: 0.85.")
    else:
        summary_lines.append("")
        summary_lines.append("No anomalies detected. Confidence: 0.80.")

    return "\n".join(summary_lines)