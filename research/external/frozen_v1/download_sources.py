"""Retrieve immutable public originals; never accept a moved tag or wrong blob."""
import argparse
from pathlib import Path
from urllib.request import urlopen

from research.external.frozen_v1.experiment import HERE, check_blob, load, require, save


def download(output):
    corpus = load(HERE / 'CORPUS.json')
    require(not output.exists(), 'new source directory required')
    pending, identities = {}, {}
    for name, identity in corpus['sources'].items():
        url = ('https://raw.githubusercontent.com/' + identity['repository'] + '/' +
               identity['commit'] + '/' + identity['path'])
        with urlopen(url, timeout=30) as response:
            raw = response.read(corpus['budget']['source_bytes_limit'] + 1)
        identities[name] = check_blob(raw, identity)
        raw.decode('utf-8')
        pending[name] = raw
    output.mkdir(parents=True)
    for name, raw in pending.items():
        (output / (name + '.java')).write_bytes(raw)
    save(output / 'IDENTITIES.json', identities)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    download(parser.parse_args().output)
