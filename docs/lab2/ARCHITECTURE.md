# Architecture (Pair 06, Lab 2)

Everything below runs from `docker-compose.yml` (the same images go to Kubernetes). Names and ports are the real ones.

## 1. Containers and who talks to whom

```mermaid
flowchart TB
    browser["Browser<br/>React website :9061<br/>p06-frontend"]
    gw["nginx gateway :9060<br/>p06-gateway<br/>routes by URL path"]
    stu["p06-student :9062<br/>/students /auth /media"]
    com["p06-company :9063<br/>/companies<br/>/auth/company/signup"]
    job["p06-job :9064<br/>/jobs /meta"]
    app["p06-application :9065<br/>/applications<br/>/jobs/{id}/apply"]
    evt["p06-event :9066<br/>/events"]
    ai["p06-assistant :9067<br/>/assistant<br/>also checks the other<br/>five services' /health"]
    kafka[("p06-kafka<br/>KRaft broker<br/>:9092 inside, :9068 outside")]
    wa["p06-application-worker"]
    we["p06-event-worker"]
    wj["p06-job-worker"]
    mongo[("p06-mongo<br/>MongoDB p06_handshake<br/>+ GridFS (PDFs, pictures)<br/>:27017 inside, :9069 outside")]
    ollama["Ollama (qwen3:8b)<br/>on the host"]

    browser -->|HTTP| gw
    gw --> stu & com & job & app & evt & ai
    stu ~~~ app
    com ~~~ evt
    job ~~~ ai
    app -->|"application.created,<br/>updated, status_changed"| kafka
    evt -->|"event.registration_created"| kafka
    job -->|"job.created"| kafka
    kafka --> wa & we & wj
    wa & we & wj -.->|"p06.dlq<br/>(failed for good)"| kafka
    stu & com & job & app & evt & ai --> mongo
    wa & we & wj -->|"write, then commit"| mongo
    ai --> ollama
```

## 2. The apply flow (asynchronous, 202)

```mermaid
sequenceDiagram
    participant B as Browser (ApplyBox)
    participant G as Gateway :9060
    participant A as p06-application
    participant M as MongoDB
    participant K as Kafka
    participant W as p06-application-worker

    B->>G: POST /jobs/7/apply (PDF)
    G->>A: same request<br/>+ X-Request-ID (becomes the trace_id)
    A->>M: validate, store the PDF in GridFS
    A->>K: p06.application.created<br/>(key 12:7, event_id, trace_id)<br/>wait until the broker confirms
    A-->>B: 202 Accepted {event_id, trace_id}
    K->>W: deliver the message
    W->>M: insert the application<br/>(unique on student + job)<br/>activity log _id = event_id
    W->>K: commit the offset (only now)
    B->>G: ask again (every 1.5 s, at most 10 times)
    G->>A: ...
    A-->>B: the application is there: "Pending"
```

If the worker is killed between the insert and the commit, Kafka delivers the message again after the restart and the handler finds
the application already there (`duplicate`). Messages that can never work, or still fail after 3 attempts, are copied to `p06.dlq`
before their offset is committed (see `KAFKA_CONTRACT.md`, sections 3, 4 and 7).

## 3. Topics

| Topic | Producer | Consumer |
|---|---|---|
| `p06.application.created` | p06-application (`POST /jobs/{id}/apply`) | p06-application-worker |
| `p06.application.updated` | p06-application (`PUT /applications/{id}/resume`) | p06-application-worker |
| `p06.application.status_changed` | p06-application (`PATCH /applications/{id}/status`) | p06-application-worker |
| `p06.event.registration_created` | p06-event (`POST /events/{id}/register`) | p06-event-worker |
| `p06.job.created` | p06-job (`POST /jobs`) | p06-job-worker |
| `p06.dlq` | the three workers | a person |

## 4. The same system in Kubernetes (namespace `p06-handshake`, manifests in `k8s/`)

```mermaid
flowchart TB
    user["Browser"]
    gw["Service p06-gateway<br/>2 pods (nginx)<br/>NodePort 30060 (kind)<br/>reaches the services<br/>by their DNS names"]
    fe["Service p06-frontend<br/>2 pods<br/>NodePort 30061 (kind)"]
    stu["Service p06-student<br/>2 pods"]
    com["Service p06-company<br/>1 pod"]
    job["Service p06-job<br/>2 pods"]
    app["Service p06-application<br/>2 pods"]
    evt["Service p06-event<br/>1 pod"]
    ai["Service p06-assistant<br/>1 pod"]
    kafka[("StatefulSet p06-kafka<br/>KRaft, volume 2 GiB<br/>Service p06-kafka:9092")]
    wa["Deployment<br/>p06-application-worker"]
    we["Deployment<br/>p06-event-worker"]
    wj["Deployment<br/>p06-job-worker"]
    mongo[("StatefulSet p06-mongo<br/>volume 2 GiB<br/>Service p06-mongo:27017")]

    user --> gw
    user --> fe
    gw --> stu & com & job & app & evt & ai
    stu ~~~ app
    com ~~~ evt
    job ~~~ ai
    app & job & evt -->|"p06-kafka:9092"| kafka
    kafka --> wa & we & wj
    stu & com & job & app & evt & ai --> mongo
    wa & we & wj --> mongo
```

Each box is a Kubernetes Service (a stable DNS name and address that spreads requests over the ready pods behind it) or the workload
behind it. The three workers have no Service because nothing calls them: they read from Kafka. Every service and worker pod also reads the
ConfigMap `p06-config` and the Secret `p06-secrets` (not in git) as environment variables; those links are not drawn, to keep the diagram readable.
