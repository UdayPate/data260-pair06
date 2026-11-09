# Kubernetes (Pair 06, Lab 2, Part 1.3)

Everything of the platform in one namespace, **`p06-handshake`**; every resource name starts with `p06-`.

```
k8s/
  base/                  the manifests (one file per component) + kustomization.yaml
  overlays/local/        the kind version: the gateway and the website as NodePort Services
  kind-config.yaml       the local cluster (kind), maps localhost:9060 and :9061 into it
  secret.example.yaml    TEMPLATE of the Secret (placeholders only; never applied)
  create_secret.py       creates the real Secret p06-secrets from the git-ignored root .env
  load_images.py         copies the local Docker images into the kind cluster
```

## What is deployed

| Kind | Name | Replicas | Notes |
|---|---|---|---|
| Namespace | `p06-handshake` | | |
| ConfigMap | `p06-config` | | database name, CORS origins, Kafka address, Ollama address (nothing secret) |
| Secret | `p06-secrets` | | `MONGO_USER`, `MONGO_PASSWORD`, `JWT_SECRET`; **not in git**, made by `create_secret.py` |
| StatefulSet + Service | `p06-mongo` (27017) | 1 | MongoDB 7, 2 GiB volume, password from the Secret |
| StatefulSet + Service | `p06-kafka` (9092) | 1 | Kafka 3.9 in KRaft mode (no ZooKeeper), 2 GiB volume |
| Deployment + Service | `p06-student` 9062, `p06-job` 9064, `p06-application` 9065 | 2 each | |
| Deployment + Service | `p06-company` 9063, `p06-event` 9066, `p06-assistant` 9067 | 1 each | |
| Deployment (no Service) | `p06-application-worker`, `p06-event-worker`, `p06-job-worker` | 1 each | the Kafka consumers; can go up to 3 (the partitions) |
| Deployment + Service | `p06-gateway` 9060, `p06-frontend` 9061 | 2 each | the front door and the website |

**How the pods find each other (service discovery).** Every Service name is a DNS name inside the namespace. The gateway's
`nginx.conf` says `proxy_pass http://p06-job:9064`; Kubernetes resolves `p06-job` to the Service's address and spreads the requests over
the ready pods behind it. The services reach MongoDB at `p06-mongo:27017` and Kafka at `p06-kafka:9092` the same way. The
connection string is built inside the pod from the Secret: `mongodb://$(MONGO_USER):$(MONGO_PASSWORD)@p06-mongo:27017/?authSource=admin`.

**Health.** `startupProbe` and `livenessProbe` call `/health` (the process is alive; a failure restarts the pod). `readinessProbe` calls
`/health/ready` (MongoDB answers; a failure removes the pod from the Service). A worker has no web address, so its liveness probe
checks that its heartbeat file is fresh. There is no start-order setting: a pod that starts before MongoDB or Kafka is simply
not ready (or restarts once) until they are up.

**Scaling.** Replica counts are in the manifests and `resources` (requests and limits) are on every container, so the scheduler knows what
fits. To scale by hand: `kubectl -n p06-handshake scale deployment/p06-job --replicas=4`. (An autoscaler is not configured.)

## Run it locally on kind (Kubernetes in Docker)

Needs Docker Desktop with the eight images built (`docker compose build`) and `kind` (Windows: `winget install Kubernetes.kind`).
`kubectl` comes with Docker Desktop. Stop the Compose stack first (`docker compose stop`): it uses the same ports 9060 and 9061.

```powershell
# 1. the cluster (Kubernetes 1.34 is pinned on purpose, see kind-config.yaml)
kind create cluster --config k8s/kind-config.yaml            # context kind-p06-handshake
# 2. the images into the cluster
python k8s/load_images.py
# 3. the namespace, then the Secret (read from .env, never printed), then everything else
kubectl apply -f k8s/base/namespace.yaml
python k8s/create_secret.py
kubectl apply -k k8s/overlays/local
# 4. wait until every pod is 1/1 Running (about one minute)
kubectl -n p06-handshake get pods
# 5. fill the database (once), through a temporary tunnel to the MongoDB pod
kubectl -n p06-handshake port-forward svc/p06-mongo 9069:27017      # leave it running, open a second window:
cd backend; .\venv\Scripts\Activate.ps1                              # MONGO_URL=mongodb://<user>:<password>@localhost:9069/?authSource=admin
python -m seed.generate_seed --reset                                 # then stop the port-forward with Ctrl+C
# 6. use it: the website is http://localhost:9061 and the API (through the gateway) is http://localhost:9060
curl.exe http://localhost:9060/health
```
Stop it: `kind delete cluster --name p06-handshake` (this also deletes the data), then `docker compose start`.

Handy commands: `kubectl -n p06-handshake get pods,svc,pvc`, `kubectl -n p06-handshake logs deploy/p06-application-worker`,
`kubectl -n p06-handshake describe pod <name>`, `kubectl -n p06-handshake exec p06-kafka-0 -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server p06-kafka:9092 --list`.

## For the AWS deployment (EKS) — notes for the partner

* Push the eight images to ECR and change the `image:` lines (a kustomize `images:` entry in a new `overlays/eks/` does it without editing `base/`).
  `imagePullPolicy` is `IfNotPresent`; with a real registry the tag `1.0.0` is pulled normally.
* Make an `overlays/eks/` that turns `p06-gateway` and `p06-frontend` into `type: LoadBalancer` (see `overlays/local/nodeports.yaml` for the shape).
* **The website image has the API address baked in** (`VITE_API_URL`, a build argument of `frontend/Dockerfile`; `PUBLIC_API_URL` in
  `docker-compose.yml` and `.env.example` is the same build argument under another name: Compose passes it on as `VITE_API_URL`). Build it with the
  gateway's public address (`docker build --build-arg VITE_API_URL=http://<gateway-load-balancer>`), and put the website's public address
  into `CORS_ORIGINS` in `p06-config`. The load balancer address is only known after the Services exist, so create the gateway Service
  first, then build the website image.
* MongoDB and Kafka use PersistentVolumeClaims with the cluster's default StorageClass. On EKS that needs the EBS CSI driver add-on.
* `OLLAMA_URL` points at `host.docker.internal`, which only exists on a developer machine. In AWS the assistant needs a reachable
  Ollama address (or it answers with its "model unavailable" message); the other services do not depend on it.
* Create the Secret on the cluster with `python k8s/create_secret.py` (kubectl pointing at EKS) or with your own secret mechanism.
* **Seeding the database: there is no seed Job.** On EKS it works the same way as on kind (step 5 above): open a tunnel to the MongoDB pod
  with `kubectl -n p06-handshake port-forward svc/p06-mongo 9069:27017` (kubectl pointing at EKS), then run `python -m seed.generate_seed --reset`
  from `backend/` on your machine with `MONGO_URL=mongodb://<user>:<password>@localhost:9069/?authSource=admin`. The seed code is not
  inside the service images, so a Kubernetes Job would need its own image; the tunnel does not.
* **Node sizing.** The requests in the manifests add up to about 1 CPU and 2 GiB of memory for the 18 pods (computed from the manifests: 12 Python pods
  at 50m / 96Mi, 4 nginx pods at 25m / 32Mi, MongoDB 100m / 256Mi, Kafka 200m / 512Mi). The limits add up to about 9 CPUs and 6.75 GiB, but the pods
  do not use that much; the whole set ran on kind inside a Docker Desktop VM with 12 CPUs and 7.9 GB. Choose nodes that leave at least 1 CPU and 2 GiB
  free for these pods on top of what the cluster's own components use.
