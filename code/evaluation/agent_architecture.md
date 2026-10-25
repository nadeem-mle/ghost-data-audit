# Agent architecture and requirements assessment

HackerRank's published Orchestrate instructions ask participants to build and submit an AI agent, test its output against the challenge requirements, and include source with setup/run instructions. They permit the participant's choice of AI tools, models, framework and language. The published page does not establish a minimum number of tool calls, a required agent framework, or a guarantee that any particular architecture passes review. Source: [HackerRank Orchestrate](https://help.hackerrank.com/articles/3728112689-hackerrank-orchestrate), checked 2026-10-25.

The original runtime was mostly a deterministic evidence auditor with a fixed source-inspection path and optional three-case Gemini advice. That made its model-directed agent behavior limited. This is an architectural assessment, not a published disqualification decision. Anthropic's useful distinction is that an agent lets the model direct its process and tool choices, while a workflow follows predefined paths. Source: [Building effective agents](https://www.anthropic.com/research/building-effective-agents).

## Implemented separation

The deterministic core parses participant evidence, admits facts with provenance and time, resolves supported identities, applies the supplied policy, constructs a conservative recreation graph, plans actions and validates output. It remains the reproducible offline baseline.

The optional tool investigator uses an observe → model selects a typed tool → application validates arguments and executes a read-only lookup → model observes the result → follow-up or finish loop. The model chooses the next investigation action rather than receiving a fixed batch of evidence once. There is one bounded runtime investigator, not a swarm. Parallel coding reviewers are development assistance and are not runtime reasoning or votes on labels.

Application code controls the approved evidence corpus, subject/resource scope and cutoff, repeated-query detection, the eight-tool-call budget, transport limits and exact-source support. Evidence text is untrusted data. The model has no shell, filesystem traversal, network navigation, credential access, public answer retrieval, arbitrary SQL execution, live deletion or final-label tool. Invalid or unsupported tool calls stop safely. Unknown evidence remains unknown.

A candidate observation must cite an admitted source unit and an exact supporting quote. This establishes a grounded observation only; it is not sufficient by itself to establish identity, retention applicability, absence or policy compliance. No confidence score or model instruction overrides those deterministic gates. The agent cannot create a participant resource ID or clear a missing-proof blocker by assertion.

## How to assess the result

Use the loop's own test suite and retained traces to verify model-selected tool calls, follow-up after observations, scope/cutoff filtering, unsupported citations, repeated queries, budgets, malformed model replies and prompt-injection resistance. A separate live synthetic test, when recorded in `runs/tool-agent-live.json`, tests provider transport plus model-directed execution without exporting additional challenge cases. Mocked tests establish control behavior; a live synthetic trace establishes a bounded successful interaction. Neither measures all 518 challenge decisions or hidden-test ranking.

The full release's summary remains authoritative for whether this optional loop was enabled in that run. Offline public ablations are not silently described as generative-agent runs. Prior approved Gemini reviews are historical advisory measurements and are reported separately in usage_report.md.

## Submission consequence

Adding model-directed tools makes the agent component concrete and reviewable. It does not establish upload acceptance, a top rank, complete semantic extraction, or missing source facts. An official prediction file remains blocked whenever ownership, retention, copy coverage or other proof obligations are unresolved. The code ZIP and documentation can be reviewed now; a complete compliant submission also requires the validated prediction CSV and finalized authentic session exports.

## Runnable commands and measured live test

```bash
# GEMINI_API_KEY must already be set securely.
.venv/bin/python code/agent_demo.py --model gemini-3.5-flash-lite
.venv/bin/python code/main.py --dataset dataset --agent-model gemini-3.5-flash-lite --agent-case case_01 --run-dir runs/agent-case
```

The first command sends only locally authored synthetic records. The measured
2026-10-25 execution selected two evidence tools and finished after three model
calls: 1,561 input + 130 output = 1,691 reported tokens. Missing proof remained
unresolved. The trace is runs/tool-agent-live.json (development artifact).
The second command is opt-in and sends actual scoped challenge evidence to Google;
it was not executed in this phase. Earlier approval covered three excerpts,
which were already reviewed in the historical advisory phase.

The agent searches admitted facts rather than performing unrestricted new
extraction. Its findings do not change accepted facts or final CSV labels.
This is a concrete model-directed investigation capability with a conservative
acceptance boundary; it cannot repair absent input evidence. The 90-second
budget is checked between calls; one pending call may last its transport timeout.
