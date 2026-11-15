"""
Deploys (or restores) Handshake on the EKS cluster  p06-handshake  (Lab 2, Part 1.4 to 1.6).

    eksctl create cluster -f k8s/eks/cluster.yaml          # the cluster itself, about 15 to 20 minutes
    python k8s/eks/deploy.py                                # everything else, about 10 minutes
    python k8s/eks/deploy.py --no-seed                      # skip the seeding (the database already has data)

Run it from the repo root with Docker running and the AWS CLI signed in. The values of MONGO_PASSWORD and JWT_SECRET come from
the git-ignored .env and are never printed.

Why the order matters: the website image has the gateway's PUBLIC address baked in (VITE_API_URL), and AWS only hands out that
address after the gateway Service exists, and it is a NEW address every time the cluster is created. So the script
  1. points kubectl at the cluster, creates the namespace and the Secret,
  2. applies the overlay k8s/overlays/eks (the website pods wait, their image is not in ECR yet or is the old one),
  3. waits for the two load-balancer addresses (gateway and website),
  4. builds the website image with the gateway address, pushes it to ECR,
  5. puts the website address into CORS_ORIGINS (so the browser may call the API) and restarts the pods that read it,
  6. waits until every pod is Ready, then seeds MongoDB through a temporary kubectl port-forward,
  7. prints the two addresses.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT, REGION, CLUSTER, NAMESPACE = "858444017481", "us-east-1", "p06-handshake", "p06-handshake"
REGISTRY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"
TAG = "1.0.0"
PYTHON_DEPLOYMENTS = ["p06-student", "p06-company", "p06-job", "p06-application", "p06-event", "p06-assistant",
                      "p06-application-worker", "p06-event-worker", "p06-job-worker", "p06-memory-worker"]


def run(command, check=True, **kwargs):
    """Run a command and show it (never a secret: secrets are only ever passed through stdin or a protected file)."""
    print("  $", " ".join(str(part) for part in command))
    return subprocess.run(command, check=check, **kwargs)


def kubectl(*args, **kwargs):
    return run(["kubectl", "-n", NAMESPACE, *args], **kwargs)


def load_balancer_address(service: str, timeout=600) -> str:
    """The public hostname AWS gives a LoadBalancer Service (it shows up a minute or two after the Service is created)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = subprocess.run(["kubectl", "-n", NAMESPACE, "get", "svc", service, "-o", "json"], capture_output=True, text=True)
        if out.returncode == 0:
            ingress = json.loads(out.stdout)["status"].get("loadBalancer", {}).get("ingress", [])
            if ingress and (ingress[0].get("hostname") or ingress[0].get("ip")):
                return ingress[0].get("hostname") or ingress[0]["ip"]
        time.sleep(10)
    sys.exit(f"The load balancer of {service} got no address within {timeout} s.")


def ecr_login():
    """Log Docker in to ECR. The temporary password goes through stdin, not through the command line."""
    password = subprocess.run(["aws", "ecr", "get-login-password", "--region", REGION], capture_output=True, text=True, check=True)
    run(["docker", "login", "--username", "AWS", "--password-stdin", REGISTRY], input=password.stdout.strip(), text=True)


def read_env() -> dict:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def seed(env: dict):
    """The seed code is not inside the service images, so seed through a tunnel to the MongoDB pod (see k8s/README.md)."""
    print("== Seeding MongoDB through a port-forward")
    tunnel = subprocess.Popen(["kubectl", "-n", NAMESPACE, "port-forward", "svc/p06-mongo", "9069:27017"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(8)
        python = ROOT / "venv" / "Scripts" / "python.exe"
        if not python.exists():
            python = ROOT / "backend" / "venv" / "Scripts" / "python.exe"
        child_env = dict(os.environ, MONGO_URL=f"mongodb://{env['MONGO_USER']}:{env['MONGO_PASSWORD']}@localhost:9069/?authSource=admin")
        run([str(python if python.exists() else sys.executable), "-m", "seed.generate_seed", "--reset"], cwd=ROOT / "backend", env=child_env)
    finally:
        tunnel.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-seed", action="store_true", help="do not seed the database")
    args = parser.parse_args()
    env = read_env()

    print("== 1. kubectl -> the cluster, namespace, Secret")
    run(["aws", "eks", "update-kubeconfig", "--name", CLUSTER, "--region", REGION])
    run(["kubectl", "apply", "-f", str(ROOT / "k8s" / "base" / "namespace.yaml")])
    run(["kubectl", "apply", "-f", str(ROOT / "k8s" / "eks" / "storageclass.yaml")])      # default volumes for MongoDB and Kafka
    run([sys.executable, str(ROOT / "k8s" / "create_secret.py")])

    print("== 2. apply the EKS overlay (images from ECR, two load balancers)")
    run(["kubectl", "apply", "-k", str(ROOT / "k8s" / "overlays" / "eks")])

    print("== 3. wait for the two load-balancer addresses")
    gateway, website = load_balancer_address("p06-gateway"), load_balancer_address("p06-frontend")
    api_url, site_url = f"http://{gateway}:9060", f"http://{website}:9061"
    print(f"   API (gateway): {api_url}\n   website:       {site_url}")

    print("== 4. build the website image with the gateway address and push it to ECR")
    image = f"{REGISTRY}/p06-frontend:{TAG}"
    run(["docker", "build", "-t", image, "--build-arg", f"VITE_API_URL={api_url}", str(ROOT / "frontend")])
    ecr_login()
    run(["docker", "push", image])

    print("== 5. CORS_ORIGINS = the website address; restart the pods that read it, and the website")
    patch = json.dumps({"data": {"CORS_ORIGINS": site_url}})
    kubectl("patch", "configmap", "p06-config", "--type", "merge", "-p", patch)
    kubectl("rollout", "restart", *[f"deployment/{name}" for name in PYTHON_DEPLOYMENTS], "deployment/p06-frontend")

    print("== 6. wait until everything is ready")
    for kind, name in [("statefulset", "p06-mongo"), ("statefulset", "p06-kafka"), ("deployment", "p06-gateway"),
                       ("deployment", "p06-frontend")] + [("deployment", n) for n in PYTHON_DEPLOYMENTS]:
        kubectl("rollout", "status", f"{kind}/{name}", "--timeout=600s")
    if not args.no_seed:
        seed(env)

    print(f"\nDone.\n  Website: {site_url}\n  API docs: {api_url}/docs\n  Health:   {api_url}/health")
    return 0


if __name__ == "__main__":
    sys.exit(main())
