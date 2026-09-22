"""PR51 preserves every accepted PR50 file, with one additive registry edit."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "bee1a2ad64668d86054fa91ab4d23bd399bc4789"
EDITABLE = {"research/regression/SUITES.json"}


def audit():
    inventory = {}
    for row in subprocess.check_output(["git", "ls-tree", "-rz", BASE], cwd=ROOT).split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, kind, expected = meta.decode().split()
        name = name.decode()
        if name in EDITABLE:
            continue
        path = ROOT / name
        raw = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        actual_mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        if path.is_symlink() or kind != "blob" or mode != actual_mode or actual != expected:
            raise ValueError("accepted PR50 file changed: " + name)
        inventory[name] = dict(sha256=hashlib.sha256(raw).hexdigest(), mode=mode)
    old = json.loads(
        subprocess.check_output(
            ["git", "show", BASE + ":research/regression/SUITES.json"], cwd=ROOT
        )
    )
    new = json.loads((ROOT / "research/regression/SUITES.json").read_text())
    if not set(old["prior"] + old["new"]) <= set(new["prior"] + new["new"]):
        raise ValueError("accepted suite removed")
    return dict(
        base=BASE,
        preserved_files=len(inventory),
        explicit_edit_exceptions=sorted(EDITABLE),
        inventory_sha256=hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
    )


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
