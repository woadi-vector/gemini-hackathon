# APEX Approve — Working State
Last updated: Mon Jun 8, 2026 — end of Day 1

## Where things live
- Repo: github.com/woadi-vector/gemini-hackathon
- Codespace: woadi-vector/gemini-hackathon (name: crispy-meme)
- Phoenix workspace: https://app.phoenix.arize.com/s/jason-wold
- Phoenix project: apex-approve
- Model: gemini-2.5-flash via Vertex AI
- GCP project: apex-approve (project number 618384338123)
- Auth: gcloud application-default credentials (jmanw4@gmail.com)
- Secrets: in Codespaces secrets (PHOENIX_API_KEY, PHOENIX_COLLECTOR_ENDPOINT, GOOGLE_API_KEY [unused now])

## Stack working
- Python 3.12.1 + uv
- google-adk + phoenix.otel + openinference-instrumentation
- Vertex AI (gemini-2.5-flash) — no rate limit issues on $300 credit
- 4 tools registered, all called by agent at least once
- Phoenix traces every call cleanly with planner + tool spans

## Validated fixtures (Day 1 — 5 cases)
- exp_001 (clean baseline): routed clarify, expected approve. Stub coherence too aggressive. Day 3 fix.
- exp_002 (HERO CASE — structuring): routed flag correctly. Demo center.
- exp_003 (typosquat): routed clarify correctly. Agent named both spellings.
- exp_004 (memo/receipt mismatch, liquor store as 'client lunch'): routed clarify, expected flag. Agent caught all the signals but was conservative. Day 3 prompt tune: push toward flag when combination of signals is strong.
- exp_005 (no employee history, no known vendor): routed clarify correctly. Uncertainty-asks-a-question principle held perfectly.

3 exact-match, 2 conservative-but-defensible. Both misses lean toward asking-the-human rather than auto-deciding. Frame as strength in demo.

## Status
- [x] Codespace + Vertex environment
- [x] approve_demo/ scaffolded
- [x] 4 stub tools with meaningful logic
- [x] expense_triage prompt with anti-flattery + never-auto-reject + system-flags-humans-decide
- [x] main.py wired to apex_approve agent
- [x] Phoenix tracing live
- [x] 3 fixture expenses + batch runner script
- [x] Hero demo case validated
- [ ] Day 2: real planner stress test, more fixtures (5-7 total), output schema fix
- [ ] Day 3: replace stubs with real Gemini sub-calls
- [ ] Day 4: Phoenix LLM-as-a-Judge evals
- [ ] Day 5: UI + demo video
- [ ] Day 6: submit (Thu Jun 11, target 12 PM CDT)

## Known issues / Day 2 work
- AGENT OUTPUT SCHEMA DRIFT: model uses 'route' sometimes, 'outcome' other times; field names vary by run. Day 2 fix: tighten prompt to require exact field names, or use ADK structured output config to enforce JSON schema at API level.
- STUB COHERENCE TOO AGGRESSIVE: check_receipt_coherence fires "low keyword overlap" on legitimately coherent expenses. Day 3 fix: replace keyword overlap with Gemini semantic comparison sub-call.
- "Could not infer collector endpoint protocol" warning: cosmetic; doesn't break tracing.
- main.py event printer is naive (function_call parts skipped). Cosmetic.

## Demo plan (preserved)
- Beat 1 (0:00–0:30): clerk's queue with several expenses
- Beat 2 (0:30–1:30): click emp_17 hero case, show planner choosing tools, show Phoenix trace tree, show structuring catch
- Beat 3 (1:30–2:30): Phoenix LLM-as-a-Judge evals scoring the agent's reasoning — Phoenix as the judge of the agent's judgment

## Next session pickup
- cd /workspaces/gemini-hackathon
- gcloud auth application-default