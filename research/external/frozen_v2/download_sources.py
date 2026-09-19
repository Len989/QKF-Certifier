"""Download the four preregistered holdout blobs and verify Git identities."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def download(output):
    output = Path(output)
    require(not output.exists(), "new holdout source directory required")
    corpus = json.loads((HERE / "CORPUS.json").read_text(encoding="utf-8"))
    pending, identities = {}, {}
    for name, spec in corpus["sources"].items():
        url = (
            "https://raw.githubusercontent.com/"
            + spec["repository"] + "/" + spec["commit"] + "/" + spec["path"]
        )
        with urlopen(url, timeout=45) as response:
            raw = response.read(corpus["budgets"]["source_bytes"] + 1)
        require(len(raw) <= corpus["budgets"]["source_bytes"], "source byte budget: " + name)
        require(git_blob(raw) == spec["blob"], "moved holdout Git blob: " + name)
        raw.decode("utf-8")
        pending[name] = raw
        identities[name] = {
            **spec,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob_verified": True,
        }
    output.mkdir(parents=True)
    for name, raw in pending.items():
        (output / (name + ".java")).write_bytes(raw)
    (output / "IDENTITIES.json").write_text(
        json.dumps(identities, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    download(p.parse_args().output)
