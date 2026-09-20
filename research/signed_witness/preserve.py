"""Current-tree preservation, separate from archived acceptance measurements."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE = "c1fecbffeb4f9e155b1e6e8e863eed31f1b5eaad"
LIVE = ".github/workflows/signed-source-reduction.yml"
ADDED = {".github/workflows/signed-concrete-witness.yml", "research/unified/v5.py"} | {
    "research/signed_witness/" + name for name in (
        "__init__.py", "common.py", "producer.py", "checker.py", "experiment.py",
        "test_witness.py", "preserve.py", "README_RU.md")}


def main():
    old, inventory = set(), {}
    for entry in filter(None, subprocess.check_output(["git", "ls-tree", "-rz", BASE]).split(b"\0")):
        meta, raw_name = entry.split(b"\t", 1)
        mode, kind, expected = meta.decode().split(); name = raw_name.decode(); old.add(name)
        if name == LIVE:
            continue
        p = Path(name); raw = p.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        actual_mode = "100755" if p.stat().st_mode & 0o111 else "100644"
        if p.is_symlink() or kind != "blob" or expected != actual or mode != actual_mode:
            raise ValueError("accepted file changed: " + name)
        inventory[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "mode": mode}
    current = set(subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")) - {""}
    if not old <= current or current - old != ADDED:
        raise ValueError("unexpected added/deleted path")
    print(json.dumps({"base_tree": BASE, "preserved_files": len(inventory), "changed_live_harness": LIVE,
                      "added_files": sorted(ADDED), "inventory_sha256": hashlib.sha256(
                          json.dumps(inventory, sort_keys=True).encode()).hexdigest()}, sort_keys=True))


if __name__ == "__main__": main()
