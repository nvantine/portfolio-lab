"""Generate user service units; starting them is a separate explicit command."""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535: parser.error("Port must be between 1 and 65535")
    root = Path(__file__).resolve().parent.parent
    executable = shutil.which("uv")
    if not executable: parser.error("Install uv first")
    target = Path.home() / ".config/systemd/user"
    units = {}
    def quoted(path): return '"'+str(path).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')+'"'
    for source in sorted((root / "server").glob("portfolio-lab*")):
        content = source.read_text().replace("%h/Projects/portfolio-lab", quoted(root)).replace("%h/.local/bin/uv", quoted(executable)).replace("127.0.0.1:8000", f"127.0.0.1:{args.port}")
        destination = target / source.name
        if destination.exists() and destination.read_text() != content:
            parser.error(f"Customized unit exists: {destination}. Review it manually before replacing it.")
        units[destination] = content
    target.mkdir(parents=True, exist_ok=True)
    for destination, content in units.items(): destination.write_text(content)
    print("Service files prepared. Run: systemctl --user daemon-reload")
    print("Then: systemctl --user enable --now portfolio-lab.target")


if __name__ == "__main__": main()
