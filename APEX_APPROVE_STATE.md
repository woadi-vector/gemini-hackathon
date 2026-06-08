# APEX Approve — Working State
Last updated: Mon Jun 8, 2026

## Where things live
- Repo: github.com/woadi-vector/gemini-hackathon
- Codespace: woadi-vector/gemini-hackathon (name: crispy-meme)
- Phoenix workspace: https://app.phoenix.arize.com/s/jason-wold
- Phoenix project: apex-approve
- Model: gemini-2.5-flash (via GOOGLE_API_KEY)
- Secrets: in Codespaces secrets (GOOGLE_API_KEY, PHOENIX_API_KEY, PHOENIX_COLLECTOR_ENDPOINT)

## Stack confirmed working
- Python 3.12.1 + uv 0.11.19
- google-adk + phoenix.otel + openinference-instrumentation
- Stage 1 viability cleared: hello-world traced agent ran and Phoenix received 1 trace at 4.1s latency

## Code structure understood
- main.py: entry, imports root_agent from <demo>.agent
- instrumentation.py: Phoenix tracing, untouched
- shopping_demo/: reference template (don't touch — read-only template)
  - agent.py: root_agent built from Agent(model, name, instruction, tools=[FunctionTool(func=...)])
  - prompt.py: single string constant passed as `instruction`
  - tools/: async functions with type hints and docstrings, returning text
  
## Status
- [x] Environment up (Codespaces)
- [x] API keys + secrets configured
- [x] uv sync clean
- [x] Hello-world traced
- [x] Reference code read and understood
- [ ] approve_demo/ scaffolded
- [ ] 4 stub tools written
- [ ] expense_triage prompt drafted
- [ ] main.py import switched
- [ ] First fixture expense traced through stubbed loop

## Next pickup
- cd /workspaces/gemini-hackathon
- code .
- Phase 9: cp -r agent/shopping_demo agent/approve_demo, then start editing

## Known issues
- The AQ.Ab8 prefix on the GOOGLE_API_KEY is the newer AI Studio key format — worked for hello-world, watch for auth issues if anything errors out
- main.py prints nothing useful to terminal (consumes events without echoing). Traces still go to Phoenix. Cosmetic.