# Stage timing over assistant requests

Run on 2026-11-14 15:16:27. Model **qwen3:8b** (real Ollama). Database: in-memory mongomock (no command timing: database time reads 0). 50 requests sent through `services/assistant.run_assistant` (the website's path), 49 answered normally and 1 failed on purpose (a model address that does not answer). Total 9467.9 s.

Request time (successful requests): mean 193160.3 ms, median 157554.6 ms, p95 297140.7 ms.

| Stage | Mean ms | Median ms | p95 ms | Share of all time |
|---|---|---|---|---|
| model inference | 193117.6 | 157543.8 | 297103.0 | 99.98% |
| database queries | 0.0 | 0.0 | 0.0 | 0.0% |
| tool execution (not database) | 10.0 | 7.2 | 31.5 | 0.01% |
| tool execution (including its database queries) | 10.0 | 7.2 | 31.5 | 0.01% |

Slowest of the four compared stages, per request: {'model inference': 49}.

Database time measured: False. An in-memory database emits no command events, so it reads 0 here; run with `--real-db` to measure it.
Queue wait: not applicable to the chat request (it is answered directly); measured in the worker part of a trace when Kafka runs.

## One successful trace

```
Trace analysis-01 (this id is in the logs and in any Kafka event this request caused):
- chat: ok, 304491.8 ms total
    model_ms=304444.0, db_ms=0.0, db_calls=0, tool_ms=12.3, tool_db_ms=0.0, tool_compute_ms=12.3
    2 model call(s), 4276 prompt + 317 completion tokens, context 31.7% full
    tools: search_jobs
    slowest stage: model inference
```

## One failed trace

```
Trace analysis-failed (this id is in the logs and in any Kafka event this request caused):
- chat: model_unreachable, 2828.6 ms total
    model_ms=2826.2, db_ms=0.0, db_calls=0, tool_ms=0.0, tool_db_ms=0.0, tool_compute_ms=0.0
    slowest stage: model inference
```
