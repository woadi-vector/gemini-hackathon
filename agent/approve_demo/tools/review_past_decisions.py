# Copyright 2026 Vector Research Labs. Apache-2.0.
"""Review past decisions — Phoenix MCP integration.

Queries the Arize Phoenix MCP server for recent triage traces from the
apex-approve project, returning a summary the agent can use as additional
context before making a routing decision.

This is the partner-MCP integration for the Arize hackathon track:
- Spawns @arizeai/phoenix-mcp as a subprocess via Node.js
- Communicates via JSON-RPC over stdio (the MCP standard transport)
- Calls the `list-traces` tool to fetch recent triage activity
- Returns a brief textual summary to the agent

The narrative role: this tool lets the agent consult its own past traces
before deciding on a new expense. It is the "system flags, humans decide"
governance principle extended one level — before flagging, the agent reviews
historical patterns to ground its judgment in evidence rather than priors.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from google.adk.tools import ToolContext


def _call_phoenix_mcp(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Spawn Phoenix MCP server, perform handshake, invoke a tool, return result.

    Uses synchronous subprocess + stdio because:
    - The MCP server lifecycle is per-call (spawn, query, terminate)
    - JSON-RPC over stdio is the MCP standard transport
    - Avoids long-lived process management in the agent runtime
    """
    api_key = os.environ.get("PHOENIX_API_KEY")
    base_url = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")

    if not api_key or not base_url:
        raise RuntimeError(
            "PHOENIX_API_KEY and PHOENIX_COLLECTOR_ENDPOINT must be set"
        )

    proc = subprocess.Popen(
        [
            "npx", "-y", "@arizeai/phoenix-mcp@latest",
            "--baseUrl", base_url,
            "--apiKey", api_key,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        # MCP handshake
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "apex-approve", "version": "0.1.0"},
            },
        }
        proc.stdin.write(json.dumps(init_request) + "\n")
        proc.stdin.flush()
        _ = proc.stdout.readline()  # consume initialize response

        # Send initialized notification (required by MCP spec)
        initialized_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        proc.stdin.write(json.dumps(initialized_notif) + "\n")
        proc.stdin.flush()

        # Call the requested tool
        call_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        proc.stdin.write(json.dumps(call_request) + "\n")
        proc.stdin.flush()

        response_line = proc.stdout.readline()
        if not response_line:
            raise RuntimeError("Empty response from Phoenix MCP server")
        return json.loads(response_line)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _summarize_traces(mcp_response: dict[str, Any], limit: int = 20) -> str:
    """Parse the MCP tool/call response and return a brief textual summary."""
    if "error" in mcp_response:
        err = mcp_response["error"]
        return (
            f"Phoenix MCP returned error {err.get('code', '?')}: "
            f"{err.get('message', 'unknown error')}. "
            "Proceeding without historical context; recommend caution on novel cases."
        )

    result = mcp_response.get("result", {})
    content = result.get("content", [])

    if not content:
        return (
            "No prior traces found in apex-approve project. "
            "This may be the first observed triage decision."
        )

    # MCP content blocks are typed; we want the text block(s)
    text_blocks = [c.get("text", "") for c in content if c.get("type") == "text"]
    raw_text = "\n".join(text_blocks).strip()

    if not raw_text:
        return "Phoenix MCP returned no readable trace summary."

    # Truncate aggressively to keep the agent's context manageable
    if len(raw_text) > 1500:
        raw_text = raw_text[:1500] + "...[truncated]"

    return raw_text


async def review_past_decisions(
    reason_for_review: str, tool_context: ToolContext
) -> str:
    """Query Phoenix MCP for recent triage traces in the apex-approve project.

    Call this tool when the current expense involves an unfamiliar employee,
    an unverified vendor, or any case where confidence is below 0.7 and you
    want to ground your decision in historical patterns. The tool consults the
    Arize Phoenix observability layer via the Phoenix MCP server and returns
    a summary of recent triage activity.

    Use the returned summary as additional context. Do not over-weight it: the
    historical context is a prior, not a verdict. The current expense's specific
    evidence still leads the decision.

    Args:
      reason_for_review: One short sentence stating why you are reviewing past
        decisions (e.g., "Employee ID emp_99 has no prior history" or "Vendor
        appears similar to a known typosquat pattern"). This is logged for
        observability.
      tool_context: ADK tool context (unused).

    Returns:
      A brief textual summary of recent triage traces from Phoenix, prefixed
      with the reason for review. If Phoenix is unreachable, returns a
      fall-closed message recommending caution.
    """
    if not reason_for_review or len(reason_for_review.strip()) < 10:
        return (
            "REJECTED: reason_for_review missing or too vague. "
            "State explicitly why you want to consult historical patterns "
            "(e.g., 'no employee history' or 'unfamiliar vendor')."
        )

    try:
        # list-traces against the current project, most recent first
        mcp_response = _call_phoenix_mcp(
            tool_name="list-traces",
            arguments={
                "project_identifier": os.environ.get(
                    "PHOENIX_PROJECT_NAME", "apex-approve"
                ),
                "limit": 20,
            },
        )
        summary = _summarize_traces(mcp_response)
        return (
            f"Reason for review: {reason_for_review}\n\n"
            f"Phoenix MCP — recent traces from apex-approve project:\n{summary}"
        )
    except Exception as e:
        return (
            f"Phoenix MCP query failed: {type(e).__name__}. "
            f"Reason for review was: '{reason_for_review[:200]}'. "
            "Proceeding without historical context; recommend defaulting to "
            "clarify for safety."
        )