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

## Validated fixtures (Day 1)
- exp_001 (clean baseline emp_42 / Staples): routed to clarify (expected approve — stub coherence tool too aggressive on keyword overlap, Day 3 fix)
- exp_002 (HERO CASE emp_17 / Best Buy structuring): routed to flag correctly. The agent reasoned about three prior $480-ish expenses, named the threshold, weighed coherence against structuring, and chose the more serious signal. This is the demo's center.
- exp_003 (Stapels typosquat): routed to clarify correctly. Agent named both spellings and used the word "typosquat" in reasoning. Drafted a specific question to the submitter.

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