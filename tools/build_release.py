"""Build a Windows ZIP from committed files only, without local data or secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release tag, e.g. v1.1.0")
    args = parser.parse_args()
    if not re.fullmatch(r"v\d+\.\d+\.\d+", args.version):
        parser.error("Use a version like v1.1.0")
    commit = git("rev-parse", "HEAD").decode().strip()
    names = git("ls-tree", "-rz", "--name-only", commit).decode().split("\0")
    prefix = f"MNE-STT-{args.version}"
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    target = out / f"{prefix}-windows.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in filter(None, names):
            if name.split("/")[0] in ("data", ".venv", ".git", "dist") or Path(name).name.startswith(".env"):
                raise RuntimeError(f"Refusing to package local runtime or secrets file: {name}")
            content = git("show", f"{commit}:{name}")
            if name.endswith((".bat", ".ps1")):
                content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            archive.writestr(f"{prefix}/{name}", content)
        archive.writestr(f"{prefix}/BUILD.json", json.dumps({"version":args.version,"commit":commit},indent=2)+"\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    checksum = target.with_suffix(target.suffix + ".sha256")
    checksum.write_text(f"{digest}  {target.name}\n", encoding="ascii")
    print(target)
    print(checksum)


if __name__ == "__main__":
    main()
