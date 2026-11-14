### Agent harness (scripted model, production guardrails)

Run on 2026-11-14 00:10:25 with `python -m scripts.agent_harness`. The model is a scripted mock (deterministic); the agent loop, guardrails, validation and tools are the production code. Seed 6. **16 of 16 cases passed.**

| Case | What it covers | Result | Guardrail outcome | Iter. | Tool calls | ms |
|---|---|---|---|---|---|---|
| 01_read_only_search | successful read-only search | PASS | G5 untrusted: search_jobs result wrapped as data, not instructions | 2 | 1 | 2.7 |
| 02_accepted_save | accepted state-changing action | PASS | G4 confirmation: the student approved, saved | 2 | 1 | 1.3 |
| 03_declined_save | declined state-changing action | PASS | G4 confirmation: the student declined, nothing saved | 2 | 1 | 1.1 |
| 04_malformed_arguments_repaired | malformed arguments (and the repaired call) | PASS | G2 schema: rejected the call to 'search_jobs' (malformed_arguments); G5 untrusted: search_jobs result wrapped as data, not instructions | 3 | 2 | 2.1 |
| 05_unknown_tool | unknown tool | PASS | G1 allowlist: rejected the call to 'delete_everything' (unknown_tool); G5 untrusted: search_jobs result wrapped as data, not instructions | 3 | 2 | 2.3 |
| 06_no_match | no-match request | PASS | none needed | 2 | 1 | 1.9 |
| 07_history_follow_up | conversation-history follow-up | PASS | G5 untrusted: search_jobs result wrapped as data, not instructions (x2) | 4 | 2 | 3.4 |
| 08_injection_before_defense | prompt-injection content BEFORE the defense | PASS | G5 injection: instruction-like text found in database content (defense is OFF); G4 confirmation: the student declined, nothing saved | 3 | 2 | 1.8 |
| 09_injection_after_defense | prompt-injection content AFTER the defense | PASS | G5 untrusted: get_job_details result wrapped as data, not instructions; G5 injection: instruction-like text found in database content | 2 | 1 | 1.3 |
| 10_iteration_ceiling | iteration ceiling | PASS | G5 untrusted: search_jobs result wrapped as data, not instructions (x6) | 6 | 6 | 9.6 |
| 11_request_timeout | timeout | PASS | G5 untrusted: search_jobs result wrapped as data, not instructions (x3); G7 timeout: more than 0.12 seconds used, stopped | 3 | 3 | 156.0 |
| 12_recovery_retry | one recovery retry | PASS | G7 retry: search_jobs failed once, tried again; G5 untrusted: search_jobs result wrapped as data, not instructions | 2 | 1 | 1.5 |
| 13_secret_redaction | privacy and secrets (guardrail 6) | PASS | G5 untrusted: search_jobs result wrapped as data, not instructions; G6 secrets: redacted 1 secret(s) from the answer | 2 | 1 | 1.6 |
| 14_other_student_email_hidden | privacy: another student's private data (guardrail 6) | PASS | G5 untrusted: search_jobs result wrapped as data, not instructions; G6 privacy: hid 1 email(s) of other students | 2 | 1 | 1.8 |
| 15_invented_id_blocked | reliable answers (guardrail 8) | PASS | G5 untrusted: search_jobs result wrapped as data, not instructions; G8 reliable answers: ids ['987654'] are in no tool result, answer replaced | 2 | 1 | 1.6 |
| 16_authorization_refused | authorization (guardrail 3) | PASS | G3 authorization: refused (this conversation belongs to another student) | 0 | 0 | 0.1 |

**Reliability before and after the repair path** (4 scripted failure scenarios; the first model reply is bad in each, the second is good):

| Setting | Scenarios recovered | Tool calls executed | Failures detected |
|---|---|---|---|
| Before repair (repair off) | 0 of 4 | 3 | 4 |
| After repair (repair on) | 4 of 4 | 7 | 4 |

These numbers come from scripted failures, so they show that the repair path recovers each kind of failure once. They are not an estimate of how often a real model fails.
