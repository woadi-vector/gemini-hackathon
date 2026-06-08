# APEX Approve — Working State
Last updated: Mon Jun 8, 2026 — end of Day 1 (lol)

## Where things live
- Repo: github.com/woadi-vector/gemini-hackathon
- Codespace: woadi-vector/gemini-hackathon (crispy-meme)
- Phoenix workspace: https://app.phoenix.arize.com/s/jason-wold
- Phoenix project: apex-approve
- Model: gemini-2.5-flash (agent) + gemini-2.5-pro (judge) via Vertex AI
- GCP project: apex-approve (project number 618384338123)
- Auth: gcloud application-default credentials (jmanw4@gmail.com)
- Vertex spend so far: well under $1 across all runs

## Stack
- Python 3.12 + uv
- google-adk + phoenix.otel + openinference-instrumentation (with explicit GoogleGenAIInstrumentor for nested sub-call spans)
- arize-phoenix 15.2.0 + arize-phoenix-evals 3.0.0
- Vertex AI for both agent and judge

## What works
- ADK agent with 4 registered tools, 3 of which use Gemini sub-calls
- Three-level nested Phoenix traces (planner → tool → sub-LLM)
- 5 validated fixtures with expected_route and expected_tools ground truth
- Batch fixture runner (fixtures/run_fixtures.py)
- Three Phoenix LLM-as-a-Judge evals (routing, tool selection, reasoning specificity)
- Unified eval runner that runs all three evals in parallel per fixture
- Pro as judge, Flash as agent (honest asymmetry)
- All evals persist scores to Phoenix Cloud as queryable traces
- Tool upgrade demonstrably catches regressions (exp_005)

## Tool status
- verify_vendor: GEMINI SUB-CALL (fuzzy matching against known list)
- check_receipt_coherence: GEMINI SUB-CALL (semantic comparison)
- draft_clarification: GEMINI SUB-CALL (tailored question generation)
- check_employee_pattern: DELIBERATE STUB (structuring detection logic is the hero case driver — Gemini upgrade would weaken the demo)

## Latest eval results (5 fixtures, all 3 evals)
- exp_001 (Staples baseline): PASS / PASS / GOOD
- exp_002 (HERO — emp_17 structuring): PASS / PASS / EXCELLENT
- exp_003 (Stapels typosquat): PASS / PASS / EXCELLENT
- exp_004 (liquor "client lunch" mismatch): PASS / PASS / EXCELLENT
- exp_005 (no history, no known vendor): FAIL / FAIL / EXCELLENT  ← consistent regression case
- Aggregates: routing 0.80, tool_selection 0.80, reasoning 0.93

## The demo's hero artifact
exp_005 fails both binary evals because the agent skipped check_employee_pattern after the verify_vendor upgrade. Phoenix's eval caught it. Without observability, this regression would be invisible until a real expense slipped through. Reasoning eval scored EXCELLENT despite the wrong answer — surface quality ≠ correctness.

## Day 5 (Tue Jun 9) targets
- Phoenix dashboard exploration — make sure scored runs render cleanly in Tracing view for screenshot capture
- README writeup (Apache 2.0 license, eval architecture diagram)
- Demo script outline
- Lovable UI (separate project pointing at Cloud Run endpoint)
- Cloud Run deployment

## Day 6 (Wed Jun 10) targets
- Polish UI
- Record demo video (target under 3 min)
- Final testing

## Day 7 (Thu Jun 11) submit
- Devpost submission by 12:00 PM CDT (4-hour buffer before 4 PM deadline)

## Known issues (deferred)
- check_employee_pattern still deterministic stub by design
- "Could not infer collector endpoint protocol" warning (cosmetic)
- main.py event printer skips function_call parts (cosmetic)
- Reasoning eval consistently scores exp_005 high despite wrong answer — demo talking point, not a bug

## Next session pickup
1. cd /workspaces/gemini-hackathon
2. gcloud auth application-default login --no-launch-browser  (only if Vertex creds expired)
3. uv run python evals/run_evals.py  (smoke test full pipeline still works)
4. Then start Day 5 polish work