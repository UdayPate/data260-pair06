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

### Which assistant, and for what

I used Claude Code (Anthropic's coding assistant, model Claude Sonnet 5.5) for my part of Lab 2: the AWS deployment (ECR, EKS, LoadBalancers), the assistant memory and consolidation, Redux, the JMeter plans and analysis, token compaction, the end-to-end trace, the guardrails and harness, and the report sections 7 to 14. It wrote and ran most of the commands and scripts; I approved each costly AWS action (creating and deleting the cluster), took the console and browser screenshots, and checked the results. The report text was drafted from real files and logs, and I told it to remove any claim the evidence did not support.

### Incorrect output 1: an EKS node group that never started

- **What went wrong:** The first cluster configuration asked for worker nodes of an instance type that my AWS account's Free plan does not allow. The cluster was created, but the node group never launched any node, so no pod could run.
- **How it was detected:** The node group stayed in a creating state, with no nodes in `kubectl get nodes`. The AWS error said that the account's plan only allows free-tier instance types.
- **How it was fixed:** The node group was changed to `m7i-flex.large` (a type the plan allows) in `k8s/eks/cluster.yaml`. The stuck node group deleted very slowly, so a second node group (`p06-nodes-b`) was created next to it. The problem and the fix are written in `docs/lab2/aws_evidence.txt`.

### Incorrect output 2: the website could not reach the server on AWS

- **What went wrong:** After the stack was restored on a new cluster, the website login showed "Cannot reach the server. Is the backend running on port 9060?", although the API itself answered correctly with `curl`.
- **How it was detected:** I took a screenshot of the login error (`docs/lab2/screenshots/aws_website_login_error.png`). Reading the JavaScript bundle that the pod served showed an old API address: the new nodes had pulled nothing and reused an old image from the cache (`imagePullPolicy: IfNotPresent`), built for a previous load balancer address.
- **How it was fixed:** `imagePullPolicy: Always` was added to the frontend container (live, and in `k8s/overlays/eks/frontend-pull.yaml`), the pods were restarted, and the bundle was read again to confirm the new address. After that, the login and the dashboard worked (screenshot `aws_website_dashboard.png`).

### Incorrect output 3: the assistant's draft claims that the evidence did not support

- **What went wrong:** While drafting the report sections, the assistant wrote some statements that I could not find in any log: that the stack was "idle" during a run, that throughput was "constant", an unverified model name, a figure of "2,500 tokens", and an explanation for a "Data unavailable" message in the console.
- **How it was detected:** I asked for a check of every claim against the saved files; each of these had no source in `docs/lab2/`.
- **How it was fixed:** All five were removed or reworded to what the files show (for example, the model timeout is described as the probable cause, not as a fact). The report states that a claim without a log or screenshot must not be in it.

### Incorrect output 4: the local model's wrong memory decisions (the model under test)

- **What went wrong:** In the consolidation run (`docs/lab2/memory_consolidation.md`), the local model (`qwen3:8b`) paired "Prefers internships over full-time jobs" with "Prefers small companies" as a contradiction, and the code removed a true note. It also left a real contradiction (computer science and data science as the major) unresolved.
- **How it was detected:** The run compares the memory before and after, with 9 checks; one check failed, and reading the decisions showed the false pair. Two earlier runs lost both copies of a duplicate and a newer fact.
- **How it was fixed:** The design was changed so the model only points and the code validates each proposal (a limit on the merge size, newer note wins, only some categories may be dropped, a cap below 40 notes). The remaining errors were not hidden: they are listed in section 8.4 of the report.