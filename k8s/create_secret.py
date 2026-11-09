"""
Creates (or updates) the Kubernetes Secret  p06-secrets  from the git-ignored root .env file.

    python k8s/create_secret.py                 # uses the current kubectl context, namespace p06-handshake
    python k8s/create_secret.py --context kind-p06-handshake

Why a script: the manifests in git must not contain passwords (Lab 2, Part 1.3). The three values
(MONGO_USER, MONGO_PASSWORD, JWT_SECRET) are read from .env, written to a temporary file that only you can read, handed to
`kubectl create secret --from-env-file`, and the temporary file is deleted. The values are never printed and never put on a
command line (where other programs could see them).
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

KEYS = ("MONGO_USER", "MONGO_PASSWORD", "JWT_SECRET")
ROOT = Path(__file__).resolve().parents[1]


def read_env(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", default="p06-handshake")
    parser.add_argument("--context", default=None, help="kubectl context (default: the current one)")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"{env_path} not found: copy .env.example to .env and fill it in first.")
        return 1
    values = read_env(env_path)
    missing = [key for key in KEYS if not values.get(key)]
    if missing:
        print("These keys are missing or empty in .env: " + ", ".join(missing))
        return 1

    kubectl = ["kubectl"] + (["--context", args.context] if args.context else [])
    fd, temp_name = tempfile.mkstemp(prefix="p06-secret-", suffix=".env")      # created readable by the owner only
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for key in KEYS:
                handle.write(f"{key}={values[key]}\n")
        create = subprocess.run(kubectl + ["-n", args.namespace, "create", "secret", "generic", "p06-secrets",
                                           f"--from-env-file={temp_name}", "--dry-run=client", "-o", "yaml"],
                                capture_output=True, text=True)
        if create.returncode != 0:
            print(create.stderr.strip())
            return create.returncode
        # `apply` creates the Secret or updates it if it exists; the YAML goes in through stdin, never through a file or argument.
        apply = subprocess.run(kubectl + ["apply", "-f", "-"], input=create.stdout, capture_output=True, text=True)
        print((apply.stdout + apply.stderr).strip())
        return apply.returncode
    finally:
        os.remove(temp_name)


if __name__ == "__main__":
    sys.exit(main())
