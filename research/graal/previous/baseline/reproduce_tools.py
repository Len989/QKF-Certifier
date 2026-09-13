"""Optional pinned Linux x86_64 JVM/ECJ installation; no solver is installed."""
import argparse, hashlib, json, platform, subprocess, sys, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent


def download(url, dest, expected):
    if not dest.exists():
        temporary = dest.with_suffix(dest.suffix + '.part')
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('xb') as out:
            while chunk := response.read(1024*1024):
                out.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
            raise ValueError('Download checksum: ' + url)
        temporary.rename(dest)
    if hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
        raise ValueError('Cached checksum: ' + str(dest))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--directory', type=Path, default=ROOT.parent / 'qkf_graal_tools'); a = p.parse_args()
    if platform.system() != 'Linux' or platform.machine() not in {'x86_64','AMD64'}:
        raise SystemExit('Pinned package is for Linux x86_64; record a new environment on other platforms')
    directory = a.directory.resolve(); directory.mkdir(parents=True, exist_ok=True)
    dest = directory / 'jdk'
    if dest.exists():
        raise SystemExit('Refusing to replace existing installation: ' + str(dest))
    cache = directory / 'downloads'; cache.mkdir(exist_ok=True)
    info = json.loads((ROOT / 'source/JDK_INSTALL.json').read_text())['install'][0]['download_info']
    wheel = cache / info['url'].rsplit('/', 1)[1]
    download(info['url'], wheel, info['archive_info']['hashes']['sha256'])
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index', '--target', str(dest), str(wheel)], check=True)
    native = json.loads((ROOT / 'native/MANIFEST.json').read_text())
    download(native['compiler_url'], directory / 'ecj-3.42.0.jar', native['compiler_sha256'])
    print(json.dumps(dict(status='installed', QKF_JAVA_RUNTIME=str(dest / 'jdk4py/java-runtime'))))
