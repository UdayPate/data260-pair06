# AI_USE: Lab 1

Each partner documents assistant use, one incorrect output, how it was detected, and the fix.

## Uday (Part A: platform)

### Which assistant, and for what
I wrote and implemented the Part A code myself. I used Claude (Anthropic) as a tutor to explain programming concepts, help me understand errors, discuss the folder structure and build order, and walk me through the code when I got stuck. I ran the tests, started the servers, and independently verified the application in Swagger UI and the browser, including the MySQL job-search totals, 401/403/404 responses, resume privacy, and role-dependent student views. I also used Claude’s explanations to make sure I understood the implementation well enough to explain it in the recording.

### Incorrect output 1: The seed script could not create the database

- **What went wrong:** When I ran `python -m seed.generate_seed --reset`, the script failed with `Unknown database 'p06_handshake'`. In SQLAlchemy 2.0, `URL.set(database=None)` leaves the existing database value unchanged, so the script still tried to connect to the database before it existed.

- **How I detected it:** I ran the seed script on my computer and read the MySQL error message. The database and seed data had not been created.

- **How I fixed it:** I changed the server-level URL to use `url._replace(database=None)`, which actually removes the database name from the connection URL. After the fix, the script created `p06_handshake` and generated the expected counts: 50 companies, 200 students, 300 jobs, 1,500 applications, and 100 events.


### Incorrect output 2: A test crashed on Windows

- **What went wrong:** Pytest used the byte-string values to create test IDs. This produced IDs that were millions of characters long. On Windows, the IDs were copied into the `PYTEST_CURRENT_TEST` environment variable, which has a 32,767-character limit. As a result, two tests produced errors even though the application code itself was working correctly.

- **How I detected it:** When I ran the test suite on Windows, I saw 87 tests pass and 2 errors instead of normal assertion failures. This showed that the problem was with the test setup rather than the resume-upload code.

- **How I fixed it:** I gave the parametrized cases short names using `ids=[...]`. After that change, the complete test suite passed.

### Incorrect output 3: Scenario jobs were hidden by their deadlines

- **What went wrong:** Three of the six scenario jobs had deadlines in the past. Since the job-search endpoint hides expired jobs by default, some of the jobs created for the demonstrations did not appear in the search results.

- **How I detected it:** I compared the seeded data with the demo searches I planned to use. The search results did not include all of the scenario jobs. After checking the database rows, I found that some of their deadlines had already passed.

- **How I fixed it:** I gave the scenario jobs fixed deadlines in 2027 and assigned them the required skills. I then compared the other 294 jobs and the remaining tables before and after the change to confirm that only the intended scenario data had changed.

### Other corrections I made during review

- The first version of the React session logic signed the user out after any failed request, including cases where the server was temporarily unreachable. I changed it so the session ends only when the API returns an actual 401 response, and I added a test for this behavior.

- `npm audit` reported several advisories. I upgraded the direct dependencies that had available fixes. I did not run `npm audit fix --force` because the remaining advisories were in development-only tools, and forcing major-version upgrades could have broken the build. I documented this as a known limitation in the README.


## Partner (Parts B and C)

### Which assistant, and for what
I used Claude Code (Anthropic's coding assistant, running in VS Code; the commits made with it carry the trailer
"Co-Authored-By: Claude Sonnet 5.5") for Parts B and C. I wrote part of the work myself and used Claude Code for the
rest. I did not keep a line-by-line record of which parts I wrote myself; the commits made with Claude Code
carry that trailer, and the changes made with it are listed below.

What Claude Code did, as the commits and files show: the Part C code (the untrusted-content wrapper in `tools.py`, the
repair path and the no-retry guard in `agent.py`), the unit tests for them, `scripts/run_part_c.py`, running the
experiments and the Part B transcript rerun, the Part B and Part C sections of `METRICS.md` and `README.md`, report
sections 7 to 10 and the Word build script. Every number in `METRICS.md` and in the report comes from those runs and
from the result files in `docs/`. I chose the model for the long experiments (`qwen2.5:1.5b-instruct`, because my
laptop has no GPU and `qwen3:8b` takes minutes per answer), and I asked for the commits and the pushes.

### Incorrect output 1: a failed tool call was counted as "the tool was called"

- **What went wrong:** In the repair path that Claude Code wrote (`_missing_tools_failure` in `agent.py`), the check
  "did the model skip a tool this request needs?" built its list of called tools from every tool record, including
  calls that had been rejected as invalid. In the first gate run with `qwen2.5:1.5b-instruct`, the model sent
  `save_job_or_event({"item_id": 1})` without `item_type`. The tool answered `Error: invalid arguments ... missing
  required argument(s) ['item_type']`. The loop then counted `save_job_or_event` as called, so when the model went on
  to answer in plain text, the loop did not flag a "text answer where a tool was required" and treated the repair as
  having worked, although nothing had been saved.

- **How it was detected:** In the real output of `python -m scripts.run_part_c gate`, the failed save produced one
  `[failure] malformed_arguments` line and a `[repair]` line, and then the model's text reply ended the turn with no
  second failure, even though the check said `save_job_or_event calls = 1, saved items ... change +0`. The same kind of
  situation without a failed call (the next gate run) printed two `[failure] text_without_tool` lines, so the two runs
  disagreed about what counts as a tool call.

- **How it was fixed:** I added `FAILED_CALL_PREFIXES` in `agent.py` and changed the check to count only calls whose
  result does not start with one of those error prefixes (the reliability script uses the same constant). I added the
  unit test `test_a_failed_call_does_not_count_as_calling_the_tool`. The fix is in commit `f818127` and the test in
  commit `04855c1`; the full backend suite passes (405 tests).

### Other corrections made during review

- The first version of the re-prompt only named the error. The first reliability run
  (`docs/part_c_reliability_run1_first_repair_wording.txt`, 16 correct turns before repair, 17 after) showed that the
  small model mostly ignored it. I kept that run in the repository, made the re-prompt end with the exact next step, and
  ran the experiment again (16 before, 20 after).
- A keyword rule in the repair check asked for `search_jobs` on "What are my job preferences?", so a correct answer was
  re-prompted. It showed up in turn 11 of the first reliability run and was fixed with a narrower rule.
- A scripted edit wrote `\b` as a backspace character into a regular expression. `pytest` failed
  (`test_follow_up_words_only_mean_search_after_an_earlier_tool_call`) and I rewrote the line.
- The prompt-injection defense did not reduce the number of successful attacks on either model. It is reported as
  measured (`METRICS.md`, section C2, and report section 9), not adjusted until it looked better.
