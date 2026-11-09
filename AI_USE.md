# AI_USE: Lab 2

Each partner documents assistant use, one incorrect output (at least), how it was detected, and the fix. The Lab 1 sections above are unchanged.

## Uday (Lab 2: Docker, Docker Compose, Kubernetes manifests, Kafka, MongoDB migration)

### Which assistant, and for what

I used Claude Code (Anthropic's coding assistant, model Claude Sonnet 5.5) mainly as a tutor and debugging assistant for my part of Lab 2. I asked it to explain Docker, Docker Compose, Kubernetes manifests, Kafka, MongoDB migration, health checks, and failure-handling concepts. I also used it when I was unsure how to begin, encountered an error, or needed help understanding why something was not working.

I wrote and implemented the code and configuration files myself, including the Dockerfiles, Docker Compose configuration, MongoDB migration, Kafka components, and Kubernetes manifests. I ran the commands and tests on my own machine, reviewed the output and failures, took the screenshots, and decided how to fix the problems. I also ran every `git add`, `git commit`, and `git push` myself. Claude Code was instructed not to commit or push changes.

### Incorrect output 1: my real `.env` was overwritten

- **What went wrong:** While I was validating `docker-compose.yml`, Claude Code suggested using a `printf ... > .env` command to create a temporary environment file. The command did not check whether `.env` already existed, so my existing file was overwritten. My original file contained my MongoDB password and JWT secret.

- **How I detected it:** When I recreated the stack with `docker compose up -d`, it used values that I had not originally chosen, including a new JWT secret. The MongoDB container was also recreated while its data volume was preserved. Because the existing data still used the old password, this helped confirm that the `.env` file had been replaced.

- **How it was fixed:** I restored `MONGO_USER` and `MONGO_PASSWORD` from the values I had saved from phase 3. The old JWT secret could not be recovered, so I generated a new random secret. This required users to sign in again, but no database data was lost. Afterward, I made sure that `.env` was not overwritten and that credentials were read without being printed.

### Incorrect output 2: the Demo 2 script printed PASS too early

- **What went wrong:** In phase 5, the Kafka failure Demo 2 script printed `result: PASS` before the restarted worker had actually reprocessed the message. The script accepted any `event=duplicate` line in the worker log after the worker was killed. However, that line belonged to an earlier demo rather than the message being tested.

- **How I detected it:** I reviewed the saved output from a complete run. During the “after the restart” section, the consumer group still showed LAG 1 for the relevant partition. The `duplicate` line for the event being tested appeared later in the log, during Demo 3a. This showed that the worker had behaved correctly, but the test script had reported PASS too early.

- **How it was fixed:** I changed the demo so it waits up to 60 seconds for the restarted worker to log `event=duplicate` for the specific event ID being tested and for the consumer group to show LAG 0 on the relevant partition. The script now prints PASS only after both conditions are satisfied; otherwise, it prints FAIL. I also filtered the displayed worker log to the specific event ID. After the fix, I ran the full demo again and confirmed that the duplicate log and LAG 0 appeared before the PASS message. The saved output is in `docs/lab2/kafka_demos_output.txt`, and the explanation is in `RUN_LOG.txt` under section 5.10.

## Partner (Lab 2)

*To be written by the partner. This section is intentionally left empty here.*