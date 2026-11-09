"""
Copies the local Docker images into the kind cluster, so the pods can start without pulling anything from a registry.

    python k8s/load_images.py                    # the eight p06-* images (tag 1.0.0) plus mongo:7 and apache/kafka:3.9.0
    python k8s/load_images.py --tag 1.0.1 --cluster p06-handshake

Why not simply `kind load docker-image`? With Docker Desktop's image store that command fails ("content digest ... not found")
because the images carry extra build-attestation entries for other platforms. `docker save --platform linux/amd64` writes just
the one image kind needs, and `kind load image-archive` loads that file.
"""
import argparse
import os
import subprocess
import sys
import tempfile

SERVICES = ["student", "company", "job", "application", "event", "assistant", "gateway", "frontend"]
THIRD_PARTY = ["mongo:7", "apache/kafka:3.9.0"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default="1.0.0")
    parser.add_argument("--cluster", default="p06-handshake")
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args()

    images = [f"p06-{name}:{args.tag}" for name in SERVICES] + THIRD_PARTY
    failed = []
    with tempfile.TemporaryDirectory() as folder:
        for image in images:
            archive = os.path.join(folder, "image.tar")
            save = subprocess.run(["docker", "save", "--platform", args.platform, image, "-o", archive],
                                  capture_output=True, text=True)
            if save.returncode != 0:
                print(f"FAILED  {image}: {save.stderr.strip()}")
                failed.append(image)
                continue
            load = subprocess.run(["kind", "load", "image-archive", archive, "--name", args.cluster],
                                  capture_output=True, text=True)
            if load.returncode != 0:
                print(f"FAILED  {image}: {(load.stdout + load.stderr).strip()[-300:]}")
                failed.append(image)
            else:
                print(f"loaded  {image}")
            os.remove(archive)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
