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

_Partner fills in: assistant used, one incorrect output, how it was detected, the fix._
