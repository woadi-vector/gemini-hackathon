# APEX Approve

> An agentic AP clerk for small-business expense triage, built on Gemini, Google ADK, and Arize Phoenix. Three LLM-as-a-Judge evals (Pro grading Flash) catch the moment when the agent reasons well but reaches the wrong conclusion.

**Built for:** Google Cloud Rapid Agent Hackathon — Arize track
**License:** Apache 2.0
**Status:** Submission-ready

---

## What it does

APEX Approve looks at expense submissions — vendor, memo, receipt text, employee history — and routes each one to one of three outcomes:

- **`approve`** — clearly legitimate
- **`clarify`** — there's a specific ambiguity only the submitter can resolve
- **`flag`** — something looks wrong; surface to human reviewer

Humans make rejection decisions. The agent never auto-rejects. *System flags, humans decide.*

## Why it's interesting

Most agent demos lead with success theater. The interesting question for production AI isn't "does it work when it works?" — it's "how do you know when it doesn't?"

APEX Approve makes that question answerable. Three LLM-as-a-Judge evals run on every triage decision: **routing correctness** (binary), **tool selection quality** (binary), and **reasoning specificity** (graded EXCELLENT/GOOD/FAIR/POOR). Gemini 2.5 Pro grades Gemini 2.5 Flash — a transparent quality asymmetry where the more capable model judges the production model.

The hero artifact: a fixture (`exp_005`) where the agent gathers all five tools' worth of evidence, including a Phoenix MCP query of its own historical traces, reasons in clean specific language — and still routes wrong. Both binary evals catch it. The reasoning eval scores EXCELLENT because the language *is* anchored. Surface quality ≠ correctness, and only the eval pipeline tells you the difference.

## Architecture

agent_run [apex_approve_agent — Gemini 2.5 Flash on Vertex]
└── call_llm (planner)
 ├── execute_tool verify_vendor
│   └── AsyncGenerateContent (Gemini sub-call)
├── execute_tool check_receipt_coherence
│   └── AsyncGenerateContent (Gemini sub-call)
     ├── execute_tool check_employee_pattern (deterministic — by design)
├── execute_tool review_past_decisions
│   └── subprocess: @arizeai/phoenix-mcp → list-traces
└── execute_tool draft_clarification
└── AsyncGenerateContent (Gemini sub-call)

Every span — including the nested Gemini sub-calls and the Phoenix MCP subprocess invocation — is captured by Phoenix Cloud via OpenInference instrumentation.

**Required tech, all invoked at runtime:**

- **Gemini** — Gemini 2.5 Flash powers the agent; Gemini 2.5 Pro grades it
- **Google Cloud Agent Builder** — code-first ADK path, deployable to Cloud Run / Agent Runtime
- **Arize Phoenix MCP** — `@arizeai/phoenix-mcp` invoked as a subprocess via JSON-RPC over stdio; the agent calls `list-traces` mid-triage to consult its own history

## The Phoenix MCP integration

The `review_past_decisions` tool spawns `@arizeai/phoenix-mcp@latest` via `npx`, completes the MCP initialize handshake, calls the `list-traces` tool against the `apex-approve` Phoenix project, and returns a summary the agent uses as additional context.

The agent is prompted to call this tool when any of these is true:
- The employee has no prior history (new hire)
- The vendor is unfamiliar or returns a typosquat signal
- Initial confidence is below 0.70
- Two tool results conflict

This is the *self-review loop*: before the agent flags or clarifies, it consults Phoenix to ground its judgment in historical patterns rather than priors.

**Important honest note:** consulting Phoenix doesn't automatically make the agent smarter. On `exp_005`, the agent reviews past history and still routes wrong. The eval pipeline catches it. Observability gives the agent *access* to its history; the eval gives *you* visibility into how the agent uses it.

## Evals

Three classifiers, all built on `arize-phoenix-evals 3.0`:

| Eval | Type | Rubric |
|---|---|---|
| `routing_correctness` | binary | PASS if route matches ground truth; FAIL otherwise. `approve` vs `clarify` is FAIL. |
| `tool_selection_quality` | binary | PASS if required tools were called AND forbidden tools were not. |
| `reasoning_specificity` | graded | EXCELLENT/GOOD/FAIR/POOR. Critical caveat: reasoning that misses what the agent SHOULD have caught cannot earn higher than FAIR, regardless of specificity. |

All three run in parallel per fixture via `asyncio.gather`. Pro is the judge; Flash is the agent. Every score is persisted to Phoenix Cloud as a queryable trace alongside the original agent run.

## Quickstart

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (for `npx @arizeai/phoenix-mcp`)
- Vertex AI access on a billed GCP project
- Phoenix Cloud account ([app.phoenix.arize.com](https://app.phoenix.arize.com))

### Setup

```bash
git clone https://github.com/woadi-vector/gemini-hackathon
cd gemini-hackathon
cp .env.example .env
```

Edit `.env`:
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=your-gcp-project
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
PHOENIX_API_KEY=your-phoenix-api-key
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/your-workspace
PHOENIX_PROJECT_NAME=apex-approve

Authenticate Vertex:

```bash
gcloud auth application-default login --no-launch-browser
```

Install dependencies:

```bash
uv sync
```

### Run the agent on a single fixture

```bash
uv run python fixtures/run_fixtures.py exp_002
```

### Run the full eval pipeline

```bash
uv run python evals/run_evals.py
```

This runs all five fixtures through the agent and grades each with all three evals in parallel. Takes 3–7 minutes depending on Phoenix MCP latency. Scores persist to Phoenix Cloud automatically.

## Fixtures

Five validated fixtures with structured ground truth:

| ID | Description | Expected route |
|---|---|---|
| `exp_001` | Clean Staples baseline | `approve` |
| `exp_002` | Hero case — emp_17 structuring pattern at Best Buy | `flag` |
| `exp_003` | Typosquat — "Stapels" one letter off Staples | `clarify` |
| `exp_004` | Memo/receipt mismatch — weekend liquor with "client lunch" memo | `clarify` |
| `exp_005` | New hire + new vendor — no history, clean memo, modest amount | `clarify` |

`exp_005` is the hero failure artifact: the agent gathers evidence, consults Phoenix, reasons in anchored language, and still approves. The eval catches it.

## Project structure

agent/
├── main.py                                # ADK CLI entry
├── instrumentation.py                     # Phoenix register + GoogleGenAIInstrumentor
└── approve_demo/
├── agent.py                           # Agent + 5 tool registration
├── prompt.py                          # System instruction (anti-flattery anchoring)
└── tools/
├── verify_vendor.py               # Gemini sub-call (fuzzy match)
├── check_employee_pattern.py      # Deterministic (structuring detection)
├── check_receipt_coherence.py     # Gemini sub-call (semantic comparison)
├── draft_clarification.py         # Gemini sub-call (tailored questions)
└── review_past_decisions.py       # Phoenix MCP — subprocess + JSON-RPC stdio
fixtures/
├── expenses.json                          # 5 validated fixtures
└── run_fixtures.py                        # Batch runner
evals/
├── eval_routing.py
├── eval_tool_selection.py
├── eval_reasoning.py
└── run_evals.py                           # Unified runner — asyncio.gather parallel

## What we learned

The thing observability is supposed to catch isn't agents that fail loudly. It's agents that succeed surface-confidently while missing the underlying signal.

A tool upgrade can look like an improvement on every dimension except one — and that one only shows up because the eval pipeline runs on every change. Adding a Phoenix MCP self-review loop gives the agent more context but doesn't automatically translate to better answers. Both of those statements are visible in the eval scores. Neither would be visible without the eval pipeline.

Surface quality ≠ correctness. The eval architecture is the artifact that lets you tell the difference.

## License

Apache 2.0. See [LICENSE](./LICENSE).

## Built by

[Vector Research Labs, LLC](https://www.vectorresearchlabs.com) — SDVOSB building closed-loop autonomic regulation technology. APEX Approve is an exploratory deployment of the broader APEX platform's eval-driven agent architecture into the small-business AP triage domain.