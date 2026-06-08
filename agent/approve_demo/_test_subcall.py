"""Throwaway test: does a direct Gemini call work inside our environment?"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from google import genai
from google.genai import types

from instrumentation import setup_tracing


async def main():
    setup_tracing()
    client = genai.Client(
        vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "1",
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )

    response = await client.aio.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        contents="Does the memo 'office supplies' match the receipt 'STAPLES PENS NOTEBOOK'? Answer yes or no with one sentence of reasoning.",
    )

    print("---RESPONSE---")
    print(response.text)
    print("---END---")


if __name__ == "__main__":
    asyncio.run(main())