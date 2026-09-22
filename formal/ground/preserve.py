"""PR50 is additive to accepted PR49, with two explicit CI/registry edits."""

import hashlib
import json
import subprocess
from pathlib import Path

BASE = "55942faaeb253f19b849e9a52ea99cfd4b240a77"
EDITABLE = {"research/regression/SUITES.json", ".github/workflows/direct-emission.yml"}


def audit():
    inventory = {}
    for row in subprocess.check_output(["git", "ls-tree", "-rz", BASE]).split(b"\0"):
        if not row:
            continue
        meta, raw = row.split(b"\t", 1)
        mode, kind, expected = meta.decode().split()
        name = raw.decode()
        if name in EDITABLE:
            continue
        path = Path(name)
        data = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        actual_mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        if path.is_symlink() or kind != "blob" or mode != actual_mode or blob != expected:
            raise ValueError("accepted PR49 file changed: " + name)
        inventory[name] = {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}
    old = json.loads(
        subprocess.check_output(["git", "show", BASE + ":research/regression/SUITES.json"])
    )
    now = json.loads(Path("research/regression/SUITES.json").read_text())
    if not set(old["new"] + old["prior"]) <= set(now["new"] + now["prior"]):
        raise ValueError("accepted regression suite removed")
    return {
        "base": BASE,
        "preserved_files": len(inventory),
        "explicit_edit_exceptions": sorted(EDITABLE),
        "inventory_sha256": hashlib.sha256(
            json.dumps(inventory, sort_keys=True).encode()
        ).hexdigest(),
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
