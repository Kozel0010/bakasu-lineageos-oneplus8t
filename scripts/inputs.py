#!/usr/bin/env python3
"""Fail-closed selection and verification of official kebab build inputs."""
import argparse
import hashlib
import io
import json
import re
import sys
import subprocess
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

API = 'https://download.lineageos.org/api/v2/devices/kebab/builds'
KERNEL = 'LineageOS/android_kernel_oneplus_sm8250'
BAKASU = 'cac1e79355ef451539f5c5ba9dc2bda1c64069de'
HEX = re.compile(r'[0-9a-f]{64}\Z')


def select(builds, date=None):
    if date and not re.fullmatch(r'20\d{6}', date):
        raise ValueError('date must be YYYYMMDD')
    found = []
    for b in builds:
        if b.get('type') != 'nightly' or b.get('version') != '24.0':
            continue
        d = b.get('date', '').replace('-', '')
        if date and d != date:
            continue
        expected = f'lineage-24.0-{d}-nightly-kebab-signed.zip'
        files = b.get('files', [])
        def one(name):
            matches = [x for x in files if x.get('filename') == name]
            if len(matches) != 1:
                raise ValueError(f'expected exactly one {name}')
            x = matches[0]
            if not HEX.fullmatch(x.get('sha256', '')) or not isinstance(x.get('size'), int) or x['size'] <= 0:
                raise ValueError(f'invalid digest or size for {name}')
            if not x.get('url', '').startswith('https://mirrorbits.lineageos.org/full/kebab/' + d + '/'):
                raise ValueError(f'unexpected URL for {name}')
            return x
        if not re.fullmatch(r'20\d{6}', d):
            raise ValueError('invalid API date')
        rom = one(expected)
        boot = one('boot.img')
        manifest = one('build-manifest.xml')
        if boot['size'] != 100663296:
            raise ValueError('unsupported boot partition size')
        found.append({'date': d, 'rom': rom, 'boot': boot, 'manifest': manifest})
    if not found:
        raise ValueError('no supported build for requested date')
    found.sort(key=lambda b: b['date'], reverse=True)
    if len({x['date'] for x in found}) != len(found):
        raise ValueError('ambiguous build date')
    return found[0]


def kernel_commit(data):
    root = ET.fromstring(data)
    if root.tag != 'manifest' or root.findall('include') or root.findall('extend-project') or root.findall('remove-project'):
        raise ValueError('unsupported manifest structure')
    projects = [p for p in root.findall('project') if p.get('name') == KERNEL or p.get('path') == 'kernel/oneplus/sm8250']
    if len(projects) != 1:
        raise ValueError('ambiguous kernel project')
    p = projects[0]
    commit = p.get('revision', '')
    if p.get('name') != KERNEL or p.get('path') != 'kernel/oneplus/sm8250' or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('kernel revision is not an exact supported commit')
    defaults = root.findall('default')
    remote = p.get('remote') or (defaults[0].get('remote') if len(defaults) == 1 else None)
    remotes = [r for r in root.findall('remote') if r.get('name') == remote]
    if remote != 'github' or len(remotes) != 1 or remotes[0].get('fetch') != '..':
        raise ValueError('unsupported kernel repository remote')
    return commit


def verify(data, file):
    if len(data) != file['size'] or hashlib.sha256(data).hexdigest() != file['sha256']:
        raise ValueError('input size or SHA-256 mismatch')


def identity(build, commit):
    raw = json.dumps([build['rom']['filename'], build['rom']['sha256'], build['boot']['sha256'], commit, BAKASU], separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def fetch(url):
    print(f'Downloading {url}', file=sys.stderr, flush=True)
    with urllib.request.urlopen(url, timeout=90) as response:
        total = response.headers.get('Content-Length', '?')
        data = io.BytesIO()
        last = time.monotonic()
        while chunk := response.read(1024 * 1024):
            data.write(chunk)
            now = time.monotonic()
            if now - last >= 5:
                print(f'Downloaded {data.tell()}/{total} bytes', file=sys.stderr, flush=True)
                last = now
        print(f'Download complete: {data.tell()} bytes', file=sys.stderr, flush=True)
        return data.getvalue()


def fetch_asset(url):
    # The URL is supplied by the official API and constrained by select().
    with tempfile.TemporaryDirectory(prefix='lineage-download-') as directory:
        subprocess.run(['aria2c', '--max-connection-per-server=16', '--split=16',
                        '--min-split-size=1M', '--file-allocation=none',
                        '--dir', directory, '--out', 'download', url], check=True)
        return (Path(directory) / 'download').read_bytes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    build = select(json.loads(fetch(API)), args.date)
    manifest = fetch_asset(build['manifest']['url'])
    verify(manifest, build['manifest'])
    commit = kernel_commit(manifest)
    boot = fetch_asset(build['boot']['url'])
    verify(boot, build['boot'])
    build.update(kernel_commit=commit, bakasu_commit=BAKASU, identity=identity(build, commit))
    (out / 'build-manifest.xml').write_bytes(manifest)
    (out / 'boot.img').write_bytes(boot)
    (out / 'inputs.json').write_text(json.dumps(build, indent=2) + '\n')
    print(json.dumps(build, indent=2))


if __name__ == '__main__':
    main()
