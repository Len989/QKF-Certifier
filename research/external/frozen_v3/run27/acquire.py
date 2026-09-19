"""Acquire the pinned file frame and runtime identities; never execute candidates.

This is corpus preparation, not a QKF evaluation. It imports no QKF engine.
Outputs must be outside the accepted baseline and are never imported as code.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def gitblob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def fetch(url, ledger):
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "QKF-frozen-v3-registration"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        resolved = response.url
    ledger.append({"url": url, "resolved_url": resolved, "bytes": len(raw),
                   "sha256": sha(raw), "wall_seconds": time.monotonic() - started})
    return raw


def runtime():
    import sysconfig
    java = Path(shutil.which("java")).resolve()
    javac = Path(shutil.which("javac")).resolve()
    java_home = java.parent.parent
    return {
        "schema": "qkf-run27-runtime-v1", "python": sys.version,
        "python_version": platform.python_version(), "executable": sys.executable,
        "python_executable_sha256": sha(Path(sys.executable).read_bytes()),
        "python_build": platform.python_build(), "python_config": sysconfig.get_platform(),
        "java_version": subprocess.check_output([str(java), "-version"], stderr=subprocess.STDOUT, text=True),
        "javac_version": subprocess.check_output([str(javac), "-version"], stderr=subprocess.STDOUT, text=True),
        "java_release": (java_home / "release").read_text(),
        "java_sha256": sha(java.read_bytes()), "javac_sha256": sha(javac.read_bytes()),
        "java_modules_sha256": sha((java_home / "lib/modules").read_bytes()),
        "os_release": Path("/etc/os-release").read_text(), "platform": platform.platform(),
        "machine": platform.machine(), "image_os": os.environ.get("ImageOS"),
        "image_version": os.environ.get("ImageVersion"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
    }


def acquire(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    a = json.loads((HERE / "ACQUISITION.json").read_text())
    ledger, frames = [], []
    (output / "ACQUISITION.json").write_bytes((HERE / "ACQUISITION.json").read_bytes())
    save(output / "runtime.json", runtime())
    for repo in a["repositories"]:
        name, revision = repo["repository"], repo["revision"]
        slug = name.replace("/", "_")
        meta = json.loads(fetch("https://api.github.com/repos/" + name, ledger))
        commit = json.loads(fetch("https://api.github.com/repos/" + name + "/git/commits/" + revision, ledger))
        tree = json.loads(fetch("https://api.github.com/repos/" + name + "/git/trees/" + revision + "?recursive=1", ledger))
        if tree.get("truncated") or tree["sha"] != commit["tree"]["sha"]:
            raise ValueError("incomplete or unbound tree: " + name)
        save(output / "metadata" / (slug + ".tree.json"), tree)
        save(output / "metadata" / (slug + ".commit.json"), commit)
        frame, excluded, licenses = [], [], []
        for entry in tree["tree"]:
            if entry["type"] != "blob":
                continue
            path = PurePosixPath(entry["path"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe source path")
            basename = path.name.lower()
            is_license = len(path.parts) == 1 and basename.startswith(("license", "copying", "notice"))
            if not basename.endswith(".java") and not is_license:
                continue
            reasons = []
            if not is_license:
                if not any(term in basename for term in a["file_rule"]["basename_contains_case_insensitive"]):
                    reasons.append("basename_outside_bit_math")
                if any(part.lower() in a["file_rule"]["excluded_path_segments_case_insensitive"] for part in path.parts[:-1]):
                    reasons.append("excluded_path_segment")
            item = {"path": str(path), "mode": entry["mode"], "git_blob": entry["sha"],
                    "size": entry["size"], "exclusions": reasons}
            if reasons:
                excluded.append(item)
                continue
            if entry["mode"] != "100644" or entry["size"] > 2_000_000:
                raise ValueError("unsupported acquisition resource: " + name + "/" + str(path))
            url = "https://raw.githubusercontent.com/" + name + "/" + revision + "/" + str(path)
            raw = fetch(url, ledger)
            if len(raw) != entry["size"] or gitblob(raw) != entry["sha"]:
                raise ValueError("source blob mismatch")
            destination = output / "sources" / slug / str(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            item.update({"sha256": sha(raw), "source_file": str(destination.relative_to(output)), "url": url})
            (licenses if is_license else frame).append(item)
        frames.append({"repository": name, "repository_id": meta["id"], "fork": meta["fork"],
                       "parent_repository": meta.get("parent", {}).get("full_name"),
                       "revision": revision, "tree": tree["sha"], "licenses": licenses,
                       "frame": frame, "excluded_java": excluded})
    save(output / "FRAME.json", {"schema": "qkf-run27-acquired-frame-v1", "repositories": frames})
    save(output / "acquisition-cost.json", ledger)
    print(json.dumps({"frame_files": sum(len(r["frame"]) for r in frames),
                      "evaluation_executed": False, "output": str(output)}))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: acquire.py NEW_OUTPUT_DIRECTORY")
    acquire(sys.argv[1])
