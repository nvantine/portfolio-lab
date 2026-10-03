"""Operator image build helper; cached mode uses only uv's locked dependencies."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", action="store_true", help="Reuse local uv cache, offline; requires dependencies already synced")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if not args.cached:
        subprocess.run(["docker", "build", "-f", "workers/Dockerfile", "-t", "portfolio-lab-worker:0.2", "."], cwd=root, check=True)
        return
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    # Fresh directory prevents unknown files being copied into the image.
    with tempfile.TemporaryDirectory(prefix="image-build-", dir=artifacts) as directory:
        build = Path(directory)
        packages = build / "packages"
        subprocess.run(["uv", "pip", "sync", "--offline", "--python", sys.executable, "--target", str(packages), "requirements.txt"], cwd=root, check=True)
        source = (root / "workers/Dockerfile").read_text()
        source = source.replace("RUN uv pip install --system --no-cache -r requirements.txt", "COPY --from=packages / /usr/local/lib/python3.13/site-packages/")
        recipe = build / "Dockerfile"
        recipe.write_text(source)
        subprocess.run(["docker", "build", "-f", str(recipe), "--build-context", "packages=" + str(packages), "-t", "portfolio-lab-worker:0.2", "."], cwd=root, check=True)


if __name__ == "__main__":
    main()
