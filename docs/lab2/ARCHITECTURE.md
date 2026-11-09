# Architecture (Pair 06, Lab 2)

Everything below runs from `docker-compose.yml` (the same images go to Kubernetes). Names and ports are the real ones.

## 1. Containers and who talks to whom

```mermaid
flowchart LR
    browser["Browser<br/>React website<br/>:9061 p06-frontend"]
    gw["nginx gateway<br/>:9060 p06-gateway<br/>routes by path"]

    subgraph apis["FastAPI services (one codebase, six entry points)"]
        stu["p06-student :9062"]
        com["p06-company :9063"]
        job["p06-job :9064"]
        app["p06-application :9065"]
        evt["p06-event :9066"]
        ai["p06-assistant :9067"]
    end

    subgraph workers["Kafka workers (no port)"]
        wa["p06-application-worker"]
        we["p06-event-worker"]
        wj["p06-job-worker"]
    end

    kafka[("p06-kafka<br/>KRaft broker :9092 / :9068")]
    mongo[("p06-mongo<br/>MongoDB p06_handshake<br/>+ GridFS (PDFs, pictures)<br/>:27017 / :9069")]
    ollama["Ollama (qwen3:8b)<br/>on the host"]

    browser -->|"HTTP"| gw
    gw -->|"/students, /auth/student..."| stu
    gw -->|"/companies, /auth/company..."| com
    gw -->|"/jobs..."| job
    gw -->|"/jobs/{id}/apply, /applications..."| app
    gw -->|"/events..."| evt
    gw -->|"/assistant"| ai

    stu & com & job & app & evt & ai --> mongo
    ai -.->|"/health of the others"| gw
    ai --> ollama

    app -->|"application.created / updated / status_changed"| kafka
    evt -->|"event.registration_created"| kafka
    job -->|"job.created"| kafka

    kafka --> wa & we & wj
    wa & we & wj -->|"write, then commit"| mongo
    wa & we & wj -.->|"failed for good"| kafka
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

    B->>G: POST /jobs/7/apply (PDF)  X-Request-ID = trace_id
    G->>A: same request
    A->>M: validate, store the PDF in GridFS
    A->>K: p06.application.created (key 12:7, event_id, trace_id) and wait for the broker to confirm
    A-->>B: 202 Accepted {event_id, trace_id}
    K->>W: deliver the message
    W->>M: insert the application (unique on student+job); activity log _id = event_id
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
flowchart LR
    user["Browser"] -->|"localhost:9061 (kind) / LoadBalancer (AWS)"| fe["Service p06-frontend<br/>2 pods"]
    user -->|"localhost:9060 (kind) / LoadBalancer (AWS)"| gw["Service p06-gateway<br/>2 pods (nginx)"]
    gw -->|"DNS name p06-student"| stu["Service p06-student<br/>2 pods"]
    gw -->|"p06-company"| com["Service p06-company<br/>1 pod"]
    gw -->|"p06-job"| job["Service p06-job<br/>2 pods"]
    gw -->|"p06-application"| app["Service p06-application<br/>2 pods"]
    gw -->|"p06-event"| evt["Service p06-event<br/>1 pod"]
    gw -->|"p06-assistant"| ai["Service p06-assistant<br/>1 pod"]
    stu & com & job & app & evt & ai -->|"p06-mongo:27017"| mongo[("StatefulSet p06-mongo<br/>volume 2 GiB")]
    app & job & evt & ai -->|"p06-kafka:9092"| kafka[("StatefulSet p06-kafka<br/>KRaft, volume 2 GiB")]
    kafka --> wa["Deployment p06-application-worker"] & we["p06-event-worker"] & wj["p06-job-worker"]
    wa & we & wj --> mongo
    secret["Secret p06-secrets<br/>(not in git)"] -.-> mongo & stu & com & job & app & evt & ai & wa & we & wj
    cm["ConfigMap p06-config"] -.-> stu & job & app & evt & ai & wa & we & wj
```

Each box is a Kubernetes Service (a stable DNS name and address that spreads requests over the ready pods behind it) or the workload
behind it. The three workers have no Service because nothing calls them: they read from Kafka.
