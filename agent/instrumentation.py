# Copyright 2025 Google LLC
# Apache-2.0
"""Phoenix tracing: ADK + bare google-genai for tool sub-calls.

Without the explicit GoogleGenAIInstrumentor, sub-LLM calls made from inside
tool bodies (via the bare `google.genai.Client`) don't appear in Phoenix as
nested spans. This file wires both: ADK auto-instrument for the agent loop,
and explicit google-genai instrumentation for sub-calls.

Environment: PHOENIX_API_KEY, PHOENIX_COLLECTOR_ENDPOINT, optional PHOENIX_PROJECT_NAME.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from phoenix.otel import register

_provider: Optional[Any] = None


def setup_tracing() -> Optional[Any]:
    """Returns the tracer provider when Phoenix auth is configured, else None."""
    global _provider
    if _provider is not None:
        return _provider
    if not (os.environ.get("PHOENIX_API_KEY") or "").strip():
        return None

    _provider = register(
        project_name=os.environ.get("PHOENIX_PROJECT_NAME", "gemini-hackathon"),
        batch=False,
        auto_instrument=True,
        verbose=False,
    )

    # Explicitly instrument bare google-genai client so sub-calls inside tool
    # bodies appear as nested spans under the parent tool's execute_tool span.
    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
        GoogleGenAIInstrumentor().instrument(tracer_provider=_provider)
    except Exception:
        # If the instrumentor isn't installed, swallow silently. Auto-instrument
        # still covers the agent loop; we just lose nested sub-call spans.
        pass

    return _provider
