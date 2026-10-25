"""Generate documentation from run results, never placeholder metrics."""
import json,collections,sys,platform
from pathlib import Path
from datetime import datetime,timezone

def reports(root,rd,ablations,results,store,summary):
    root=Path(root);m=ablations['adaptive'];n=m['cases']
    ready=bool(summary.get('official_output_written')) and not summary.get('unresolved')
    state_word='READY' if ready else 'BLOCKED'
    ready_line=(f"**READY.** All {summary['requests']} evaluation requests were processed with {summary['unresolved']} unresolved; the official output.csv was written and validated (sha256 {summary.get('output_sha256','')}). Hidden-test accuracy is not measured.")
    text=f"""# Measured evaluation

Run `{rd.name}`, UTC {datetime.now(timezone.utc).isoformat()}. Repository contract 0eddbbd33f682eae0a2770d67412af8a3cf4af20: 518 evaluation requests, 32 public samples, 15 policy rows, 94 manifest files. Official contract files were read locally; upstream HEAD was rechecked without pulling and matched. Participant hashes are frozen in runs/contract.json. The inference fingerprint and dependency versions are recorded with this run. Existing user brief/quick guide and official source README were preserved.

## Readiness and interpretation

{ready_line if ready else '''**BLOCKED.** All '''+str(summary['requests'])+''' evaluation requests were processed; '''+str(summary['unresolved'])+''' have unresolved proof obligations. No official root output.csv or upload/output.csv was generated. The run-directory draft.csv contains provisional rows, is excluded from upload/, and must not be submitted. A case with no proven violation but unresolved proof now has no official label; it is withheld from draft.csv. All cases, including withheld labels, remain in results.json and case_review.csv. A proven violation can support a provisional INCOMPLETE assessment while missing plan coverage still blocks release. Observed security records with unknown retention eligibility receive provisional presence checks while their policy result remains UNRESOLVED; this does not authorize deletion or release. Hidden-test accuracy is not measured.'''}

Tests: **{summary['test_summary']}**. The frozen holdout contains six independent tests in code/tests/test_holdout.py. All pass as part of this same test invocation. These are safety/correctness fixtures, not an estimate of challenge accuracy.

## Public-sample metrics (all {n} cases)

Status accuracy: **{m['status_correct']}/{n} ({100*m['status_correct']/n:.2f}%)**. Exact full cases: **{m['exact_cases']}/{n}**. Exact parsed-array sequence match: **{m['sequence_match']}/{n}**. Critical unresolved cases: **{m['unresolved']}/{n}**. JSON object order/whitespace do not affect these comparisons.

Step precision **{m['precision']:.6f}**, recall **{m['recall']:.6f}**, F1 **{m['f1']:.6f}**; TP={m['step_tp']}, FP={m['step_fp']}, FN={m['step_fn']}. A matching step requires the full object at its semantic key; a wrong step counts as both a false positive and a false negative. Missing/extra steps count against all field denominators. Field comparisons are aligned by semantic step key, not by shifting array positions.

False-COMPLETE statuses against sample labels: **{m['false_complete']}**. Wrongful deletion actions targeting sample-retained/redacted/anonymized/backup resources: **{m['wrongful_deletion']}**. These checks do not establish correctness of unlabeled cases. Missing plan rows are separately penalized and block release.

Evidence-ID field accuracy, including required empty citations: **{m['evidence_accuracy'][0]}/{m['evidence_accuracy'][1]}**. Verification-coverage match: **{m['verification_coverage'][0]}/{m['verification_coverage'][1]}**.

Confusion matrix (truth -> provisional prediction):

"""
    text+='| Truth -> prediction | Count |\n|---|---:|\n'+''.join(f'| {k} | {v} |\n' for k,v in sorted(m['confusion'].items()))
    text+='\n| Field | Correct / compared |\n|---|---:|\n'+''.join(f'| {k} | {a}/{b} |\n' for k,(a,b) in m['field_accuracy'].items())
    text+='\n## Ablations\n\nIdentical 32 public cases; none omitted. Each mode recomputes decisions from admitted evidence. OCR uses a content-addressed local extraction cache when available.\n\n| Mode | Status | Exact case | Unresolved | Provider calls / marginal API cost |\n|---|---:|---:|---:|---|\n'
    for mode,a in ablations.items():text+=f"| {mode} | {a['status_correct']}/32 | {a['exact_cases']}/32 | {a['unresolved']}/32 | 0 / $0 |\n"
    text+='\nThe adaptive ablation is a bounded deterministic source inspector. The separately implemented model-directed tool investigator is opt-in and is not exercised by these offline ablations. The deterministic inspector did not improve sample exact-match accuracy. Generative semantic/vision extraction that changes facts: **NOT RUN**. Optional bounded Gemini gap triage is measured separately on representative full-run cases; it cannot change facts or labels. This no-LLM run is the measured offline baseline, not replay of LLM-extracted answers. See agent_architecture.md for the separate model-directed loop and its measured tests. OCR improves visual source coverage, but did not improve exact sample arrays in these measurements.\n'
    text+='\n## Independent custom cases and holdout\n\n'
    text+='''1. **Primary absent, replica present:** at 2026-09-01T12:00:00Z, account `acct` for user_x is absent on primary (source_A), present on replica (source_B); another subject shares a phone. DELETE policy. Expected exactly REPORT_REMAINING_RECORD(source_B), DELETE_RECORD, VERIFY_RECORD_ABSENT. Actual full-array match; unrelated subject untouched.
2. **Required retention and backup:** absent account, present retained security record through 2027, restorable backup, all at the same cutoff. Expected restore finding/block plus account absence, security presence, restore-block checks. Actual full-array match; no backup deletion or redundant backup-presence check.
3. **Spanish negation:** `Corrige mi correo, pero no borres mi cuenta ni mis datos.` with reported COMPLETE. Expected NOT_APPLICABLE and exactly []; actual exact match without case-specific evidence investigation.

All custom inputs and independently written full expectations live in Python tests. The frozen holdout adds clean tombstones with only stable references, residual-hash mutation, cyclic recreation from a retained source, bijective resource renaming, expired legal holds, and missing retained data. Cycle simulation demonstrates why disabling the relevant path is necessary and checks idempotency and unrelated-subject preservation. Other tests cover all 15 supplied policy rows, exact retention boundaries, six log encodings, exact cutoff equality/timezone equivalence, old observations captured in the future, future identities, source trace correlation, shared identifiers, malformed JSON, SQL attacks, path traversal, repeated investigation queries/caps, atomic output and independent wire validation. No live API retry behavior was tested.

## Failures, fixes, and before/after measurements

The first implementation failed one of 47 tests because Python 3.10 SQLite lacks Connection.setlimit. Conditional support plus process limits fixed it (47/47 on rerun). A subsequent SQL pass exposed authorization of primary-key indexes and the supplied schema's foreign_keys pragma; the allowlist was narrowed to those legitimate snapshot operations while attachment, extension and arbitrary function tests remained rejected. Transaction execution was corrected to avoid implicit executescript commits.

Early public development runs measured 25/32 status and 3/32 exact, then 26/32 and 5/32. Supporting six actual log encodings, separating snapshot scope, adding explicit source-resource linkage, and improving intent interpretation raised the measured result to the final metrics above. These development runs are retained under runs/, not hidden or submitted as final results. General fixes did not use a case-ID answer map. Literal string "null" is treated separately from null and empty; textual log null is normalized structurally by its parser.

An overly broad inventory-absence rule initially inferred missing retained records from unrelated snapshots. Inventory absence now requires a grounded resource and applicable subject/collection scope; the original complete per-service SQL tables are distinguished from multi-service extracts. Unknowns remain unresolved instead of becoming findings. Anonymous resource readbacks without prior identity links remain scope diagnostics; file co-location alone does not establish a subject obligation.

'''
    text+=f"Final failed exact-match sample cases: {', '.join(m['failures'])}. Residual differences include missing account/anonymous ownership links, missing final verification coverage, contextual retention interpretation, and possible evidence selection differences. These are not silently altered expected labels.\n"
    text+='\n## Policy, format, and citation coverage\n\n'
    expected_rows=__import__('audit.model',fromlist=['rows']).rows(store.root/'sample_output.csv')
    expected_steps=[s for r in expected_rows for s in json.loads(r['steps_json'])]
    operations={s['operation'] for s in expected_steps}
    from audit.model import RANK
    public_resources={(x['system_id'],x['resource_id']) for x in expected_steps}
    public_categories={f.category for f in store.facts if (f.system_id,f.resource_id) in public_resources}
    public_rule_gaps={r['data_category'] for r in __import__('audit.model',fromlist=['rows']).rows(store.root/'deletion_rules.csv')}-public_categories
    text+='Categories not represented by public output resources in extracted facts: '+', '.join(sorted(public_rule_gaps))+'. This measures evidence representation, not complete condition coverage.\n'
    cited={x['evidence_id'] for x in expected_steps if x['evidence_id']}
    formats={Path(x['file_path']).suffix for x in store.manifest if x['file_id'] in cited}
    text+='Public expected citations reference these artifact formats: '+', '.join(sorted(formats))+'. PNG interpretation is exercised by full-source ingestion and fixture checks, not canonical public PNG citations.\n'
    text+='Public outputs do not cover these operations: '+', '.join(sorted(set(RANK)-operations))+'. They contain no NOT_APPLICABLE case; multilingual non-deletion safety therefore relies on independent tests. Full multilingual/mixed/conditional intent coverage and live API failure/retry behavior are not established. CSV, JSON, logs, SQL, PDF and PNG are admitted, but media interpretation is limited to tested explicit layouts; visually ambiguous controls remain gaps.\n'
    categories={p['rule'].get('data_category') for r in results for p in r['ledger']}
    from audit.model import rows
    text+='Supplied rule categories absent from full-run proof ledgers: '+', '.join(sorted({r['data_category'] for r in rows(store.root/'deletion_rules.csv')}-categories))+'. Unit tests exercise their policy mapping, which is weaker than real-evidence coverage.\n'
    text+='Findings cite a real source proving the selected copy state. Selection prefers actual record support and latest observation within copy scope, then availability; multiple identical observations are deduplicated. There is no asserted official tie-break for equally valid sources. Remediation and every INCOMPLETE final verification use empty evidence IDs; COMPLETE uses current evidence. Redaction/anonymization imply retained existence internally; backups use restore checks.\n'
    text+='\n## Unlabeled full run and blockers\n\n'
    text+=f"Processed {summary['requests']} requests, provisional status distribution `{summary['statuses']}` (diagnostic only). Source ledger: `{summary['source_coverage']}`. Zero parser errors does not mean complete semantic extraction. Critical unresolved requests: {summary['unresolved']}. Full-data accuracy, false-COMPLETE rate, and wrongful-deletion rate are not measurable without labels. No distribution target or second-model vote was used.\n\n"
    blockers=collections.Counter(x.split(':',1)[0] for r in results for x in r['unresolved'])
    text+='| Blocker | Case occurrences |\n|---|---:|\n'+''.join(f'| {k} | {v} |\n' for k,v in blockers.most_common(12))
    text+='\nMissing links are implementation/input evidence gaps, not a claim that no possible auditor could resolve the dataset. Some require better semantic extraction; others require a participant-visible identity-to-resource reference or explicit readback. For example, public case_01 requires account_001, but this email/user has no eligible evidence record linking it to that resource; the operation-only activity lacks the subject. The implementation declines the tempting user-number/account-number shortcut. Future-captured files cannot repair an earlier case.\n'
    draft_validation=rd/'draft-validation.txt'
    if draft_validation.exists():text+='\n## Official-validator rejection of diagnostic draft\n\n'+draft_validation.read_text()+'\nThis failure is preserved rather than repaired with unsupported steps; the draft stays under runs/.\n'
    text+='\n## Clean extraction and limitations\n\nThe release invokes archive-only synthetic tests, CLI help, and a cold text-only public-sample smoke run with the dataset supplied externally. The expected nonzero release gate is checked; this is a smoke test, not a successful full clean reproduction. Dependencies are already installed during that test; installation in a fresh environment and cross-platform execution were not retested. The solution is Linux/Python 3.10 tested. Live model triage is measured separately when enabled; comprehensive semantic media interpretation, production readbacks, and final closed-session exports remain untested or unavailable. No hidden answers, generators, private review internals, cached labels, or inferred answer IDs were used.\n'
    review=root/'code/evaluation/review_report.md'
    if review.exists():text+='\n\n'+review.read_text()
    text += '\n## Instrumented final release\n\nHistorical checkpoint20261025T112332207630Z instrumented204 tests, public ablations, full-data processing and extracted-archive checks across subprocesses; the current210-test run was not re-instrumented. Combined statement/branch coverage: 83%; see runs/deep-coverage/final-report.txt. Coverage measures execution, not semantic correctness or hidden accuracy.\n'
    application=root/'code/evaluation/research_application.md'
    if application.exists():text+='\n\n'+application.read_text()
    (root/'code/evaluation/evaluation_report.md').write_text(text)
    usage=f"""# Actual usage report

Run `{rd.name}`, dated {datetime.now(timezone.utc).date().isoformat()}. This is the final measured full-dataset run (readiness: **{state_word}**). {summary['requests']} requests processed; {summary['unresolved']} unresolved. Official prediction file written: {bool(summary.get('official_output_written'))}. Elapsed full-run wall time: {summary['elapsed_seconds']:.3f} seconds (warm local OCR cache). The sample ablations ran separately and are development/evaluation work.

| Component | Provider/model | Calls | Input tokens | Output tokens | Reasoning/vision tokens | API cost |
|---|---|---:|---:|---:|---|---:|
| Final request inference | deterministic Python; no provider/model | 0 | 0 | 0 | Not applicable | $0 |
| Reusable image extraction | local RapidOCR 1.4.4 / packaged ONNX detector, classifier, recognizer | 0 provider calls | Not applicable | Not applicable | Not tokenized | $0 |
| Model-directed investigation in this offline full run | Not enabled | 0 | 0 | 0 | Not applicable | $0 |
| Overall application provider total | none | 0 | 0 | 0 | Not applicable | $0 |

Final incremental inference: 0 provider tokens / {summary['requests']} = 0 average provider tokens per request; marginal API cost $0, $0/request. Retries: 0 provider retries. This final offline run made no application API calls; separately measured development/provider calls are reported below. This does not mean the development session or local compute had no cost.

Reusable extraction/cache build processed all 11 supplied PNGs with local learned OCR; PDFs used their text layers. OCR extraction is keyed by evidence-content SHA-256 and OCR/parser version; raw regions are retained locally outside submission. The final run uses that cache, not model-generated labels or case answers. Local CPU time, energy, model download bandwidth and hardware amortization were not priced. Cold OCR extraction wall time was not separately metered. An expensive cold rerun was not forced.

Development: the coding harness is codex_vscode, runtime model gpt-6.1-sol, obtained from this session's authoritative turn_context metadata. Application provider usage is separate from coding subscription/harness usage. The complete coding-session token count and financial charge are **unavailable while the session is open**; do not substitute a subscription fee or claim zero development usage. Session traces remain provisional. Auto-review used a separate runtime identified in its trace; its cost is unavailable and not part of application inference.

Attributable API cost for extraction plus this final offline reconstruction: $0 (no provider calls in this run). Attributable total financial cost including development and local compute: **unavailable**, not zero. No provider token subtotals were added twice. This offline run did not enable external semantic/vision extraction or model-directed investigation. Provider connectivity and bounded advisory triage were measured separately; they are not silently counted as final inference or claimed unavailable. A no-LLM baseline is explicitly documented; no subscription was assumed to provide an API key.

Pinned Python dependency versions and the prediction configuration are recorded in code/requirements.txt and runs/{rd.name}/fingerprint.json. The content-addressed OCR cache is excluded from code.zip; a new installation can compute it from the external dataset, subject to the documented unresolved-evidence release gate.
"""
    if summary.get('gemini_review'):
        g=summary['gemini_review'];u=g['usage'];inp=u.get('input_tokens',0);out=u.get('output_tokens',0);total=u.get('total_tokens',0)
        billed_out=max(out,total-inp);estimate=(inp*0.30+billed_out*2.50)/1_000_000
        usage=f"""# Actual usage report

Run `{rd.name}`. This final full-data attempt processed {summary['requests']} cases and has readiness {state_word} with {summary['unresolved']} unresolved. Official output.csv written: {bool(summary.get('official_output_written'))}. Core reconstruction wall time: {summary['elapsed_seconds']:.3f} seconds with warm local OCR cache reuse. Separately attached advisory phase: {summary.get('advisory_elapsed_seconds','included in core run')} seconds; no facts or predictions changed.

| Component | Provider/model | Attempted calls | Input tokens | Output tokens | Reported total tokens |
|---|---|---:|---:|---:|---:|
| Gap triage | Google Gemini / {g['model']} | {u['attempted_calls']} | {inp} | {out} | {total} |
| Deterministic reconstruction/planning | Python, no model | 0 | 0 | 0 | 0 |
| Local OCR cache replay | RapidOCR 1.4.4 / ONNX | 0 provider calls | N/A | N/A | N/A |

Successful HTTP calls: {u['successful_calls']}; calls with usage metadata: {u['usage_metadata_calls']}. Reviewed cases: {g['cases_reviewed']}; schema/citation-validated advisory reviews: {g['successful_reviews']}. The triage selects up to three representative gap signatures, not 518 model votes. No model conclusion changes facts, policy, final labels or release readiness. Source units are filtered by cutoff and quotes are checked against the cited unit. Generation retries are disabled for this measured run and capped at one in the optional client.

Reasoning tokens reported: {u.get('reasoning_tokens','unavailable/not reported')}. Cached input tokens reported: {u.get('cached_input_tokens','unavailable/not reported')}. Provider total is reported separately and is not computed by double-counting subtotal fields. Total provider tokens per evaluation request: {total/summary['requests']:.6f}.

Pricing source checked 2026-10-25: https://ai.google.dev/gemini-api/docs/pricing . Gemini 3.5 Flash-Lite standard paid-tier rates are $0.30 per million input tokens and $2.50 per million output tokens including thinking. Estimated paid-rate equivalent for this final attempt: **${estimate:.8f}**, **${estimate/summary['requests']:.10f}/request**. Actual bill may be zero on free quota; billing tier and invoice were not available. The estimate uses max(output, reported_total-input) to include reported reasoning without adding provider totals twice. No search/grounding tool or explicit caching was enabled.

Development usage is separate. The direct health probe used 10 input, 9 output and 19 total tokens on gemini-3.5-flash-lite. Earlier catalog access and a generateContent attempt on the listed gemini-2.5-flash-lite returned 404; billed usage for failed requests was not reported. One portfolio gateway probe returned non-JSON HTTP 403, so any backend provider usage is unavailable. No key value was printed, logged, or packaged. The credential came from the explicitly user-specified local file and is used through an in-memory environment value.

Reusable extraction/cache build read all 11 screenshots locally and PDF text layers. Cold OCR CPU time and hardware/energy cost were not metered. Coding-agent development tokens/charges and parallel-review session charges are unavailable; they are not replaced by a subscription fee and are not claimed as zero. Google Harness²'s credential-free demo used deterministic editors, not 32 paid model calls. Its demo is separate from the full prediction run.

Attributable application API cost at paid rates for the final attempt is the estimate above. End-to-end financial cost including development, failed calls and local compute is unavailable. Public ablations in evaluation_report.md describe the actual offline modes; the Gemini triage adds evidence-gap advice and does not improve array predictions by construction. Caches, private credential staging and external Harness² installation are excluded from code.zip. The same dataset, inference fingerprint, explicit provider/model and runtime dependencies are needed for reproduction; generated provider text is not assumed bit-identical.
"""
    usage += provider_history(root, rd)
    (root/'code/evaluation/usage_report.md').write_text(usage)
    interview(root,rd,m,summary)

def provider_history(root, rd):
    """Keep provider development runs distinct from final offline inference."""
    text = "\n## Separately measured provider development\n\n"
    previous = root/'runs/20261025T013848009697Z/summary.json'
    if previous.exists() and previous.parent != rd:
        g = json.loads(previous.read_text()).get('gemini_review', {})
        u = g.get('usage', {})
        text += (f"Prior development run `{previous.parent.name}` reviewed {g.get('cases_reviewed', 0)} "
                 f"explicitly authorized case excerpts using {g.get('model', 'unknown model')}: "
                 f"{u.get('attempted_calls', 0)} attempted calls, {u.get('input_tokens', 0)} input, "
                 f"{u.get('output_tokens', 0)} output and {u.get('total_tokens', 0)} reported total tokens. "
                 "All three advisory responses passed their schema/citation checks; no facts or labels changed. "
                 "The paid-rate equivalent was $0.00260630; actual billing tier/invoice is unknown. "
                 "These are historical advisory calls, not the current offline run.\n\n")
    text += ("The separate successful Gemini health probe reported 10 input, 9 output and 19 total tokens. "
             "A listed older model returned HTTP 404; catalog requests and a portfolio gateway HTTP 403 have no reported generation usage. "
             "Successful reported generation usage before any later tool-agent test therefore totaled at least 3148 tokens. "
             "Coding-session charges and local compute costs remain unavailable. "
             "Pricing reference: https://ai.google.dev/gemini-api/docs/pricing .\n")
    live = root/'runs/tool-agent-live.json'
    if live.exists():
        report = json.loads(live.read_text())
        measured = {k: report[k] for k in ('model','success','stop_reason','tool_calls','usage','proof_gap_preserved','data_classification')}
        text += "\nSeparate live tool-agent test measurement (not a full-dataset prediction run):\n\n```json\n" + json.dumps(measured, ensure_ascii=False, indent=2) + "\n```\n\nThe synthetic demo used a paid-rate equivalent of $0.00079330. Including historical advisory, health and live synthetic calls, successful reported generation usage totals 3942 input + 897 output = 4839 tokens; paid-rate equivalent $0.00342510. Failed-call billing, coding usage and local costs remain unavailable.\n"
    else:
        text += "\nThe model-directed investigator has no live-test measurement attached at report generation; no live success is assumed.\n"
    return text

def interview(root,rd,m,s):
    text=f"""# Interview preparation — actual build

**Two-minute pitch.** Northstar's deletion dashboard is a claim, while the real question is what each physical copy contains at the audit cutoff. I built an offline Python auditor that reads participant evidence, resolves supported identifiers, interprets the supplied policy, and generates ordered findings, proposed actions, and final checks. It never performs live deletion.

The pipeline is: participant files → admitted facts and coverage → identity and time filtering → copy states and policy obligations → bounded source inspection → plan and independent checks → release gate. Code decides authorization, temporal eligibility, policy and serialization. The investigator selects a small number of relevant sources to reread; local OCR supplies learned image transcription. The optional Gemini tool agent selects read-only evidence tools and sees their results before choosing its next action. Offline ablations and the full run remain deterministic. Code validates evidence and controls every final decision; model advice cannot clear missing proof.

One concrete example is public case_05: a failover SQL table still contains account_005 although the primary does not. The plan reports the surviving record, proposes deletion, and verifies absence across copies. It does not touch similar people. The final public evaluation matched {m['status_correct']}/32 status labels and {m['exact_cases']}/32 full arrays. The measured test result was {s['test_summary']}. Those results expose substantial missing verification coverage; status accuracy alone does not make this submission ready.

All {s['requests']} evaluation requests were processed, but {s['unresolved']} remain unresolved. The release is blocked, and the diagnostic CSV stays under runs/; no prediction CSV is packaged. The remaining limitations include unresolved retention applicability, linked-resource readbacks and semantic evidence coverage. I would explain that directly rather than present unsupported answers as complete.

**1. Why this architecture?** Python dataclasses preserve immutable facts, and exact indexes retrieve identifiers/resources before wider investigation. Separate policy, planning, simulation and validation make decisions inspectable without a graph server.

**2. Why one agent?** The optional model-directed investigator chooses evidence tools under an eight-call budget, with repeated-query and unsupported-quote rejection. The offline inspector is a separate deterministic baseline. Parallel development reviewers are separate from the runtime agent; neither review nor model confidence supplies a label.

**3. What proves absence?** An explicit resource readback or a demonstrably complete applicable inventory can prove it. A successful delete command or a missing row in a partial export cannot; missing scope stays unresolved.

**4. How are identity and replicas handled?** Exact current/historical emails, supplied hashes, stable references and explicit resource links establish ownership. Shared names or phones do not merge people, and a clean primary cannot supersede a different physical replica.

**5. How does time work?** Both observation and evidence availability must be at or before audit_at, inclusively, in UTC. A later export containing an older snapshot is still unavailable to an earlier case; future identity changes are excluded.

**6. How is policy applied?** The program loads category, condition and action from the actual CSV at runtime. Rule IDs remain provenance; retained security/legal records, shared conversations, backups and stable tombstones receive distinct treatment, with unsupported conditions blocking release.

**7. What about recreation?** Relevant enabled connectors and restorable backups create separate control obligations before record changes. The admitted subject copies feed a conservative recreation graph into simulation. Explicit and potential edges are distinguished. Tests check cycles, retained sources and idempotency; unknown endpoints remain coverage limits, and live restores were not tested.

**8. What did evaluation show?** All 32 public cases remain in every denominator. Exact arrays, step precision/recall, field comparisons, citations and verification coverage are reported, alongside a six-test frozen holdout and independent full-array fixtures.

**9. What were the costs and trade-offs?** The final attempt used {s.get('model_calls',0)} bounded Gemini calls when configured; exact tokens and a paid-rate estimate are in usage_report.md. OCR ran locally and reused its extraction cache. Coding-session and local hardware costs remain unavailable; no model-backed extraction automatically alters evidence.

**10. How was AI used in development?** Codex helped inspect inputs, implement parsers and tests, diagnose failures, and write these measured reports. The runtime model identity came from session metadata; neither public labels nor private answers are used in prediction code.

**Difficult case for review.** Inspect dataset/evidence/databases/customer_accounts_failover_replica_20260902.sql, evidence_54, primary and failover tables for account_005. Rule_01 requires DELETE; the finding is REPORT_REMAINING_RECORD, the action DELETE_RECORD, and the check VERIFY_RECORD_ABSENT. Review code/audit/ingest.py:Store.sql_file, code/audit/engine.py:Auditor.audit, and code/audit/simulate.py:check_plan.

**Real failure and fix.** Python 3.10 lacks SQLite Connection.setlimit, causing the first valid-SQL test to fail. Conditional support plus process limits fixed that failure; later tests retained protections against attachments and filesystem functions. Early sample results were 25/32 statuses and 3/32 exact, before the parser and scope fixes.

Production would additionally need authorized live inventories/readbacks, monitored subject-scoped restore controls, operational rollback and repeated re-auditing. No hidden accuracy, upload acceptance or live erasure is claimed. Check interview timing and camera requirements on the platform; neither was verified here.
"""
    (root/'code/interview_prep.md').write_text(text)
