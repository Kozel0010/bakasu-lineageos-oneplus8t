#!/usr/bin/env python3
"""Create a reproducibility report from verified outputs."""
import datetime
import hashlib
import json
import sys
from pathlib import Path

work, dist = map(Path, sys.argv[1:])
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
inputs = json.loads((dist / 'inputs.json').read_text())
verification = json.loads((dist / 'verification.json').read_text())
if inputs['boot']['sha256'] != verification['stock_sha256']:
    raise SystemExit('stock boot mismatch')
release = (work / 'release').read_text().strip()
if not release.endswith('-g' + inputs['kernel_commit'][:12]):
    raise SystemExit('kernel release does not match manifest')
report = {
    'inputs': inputs,
    'verification': verification,
    'kernel_release': release,
    'toolchain': {'version': 'AOSP Clang r596125 / 22.0.2', 'repository': 'https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86', 'commit': '383d35d98a3e1635d2e3a88d866b125d7d20a0c1'},
    'tools': {'mkbootimg_commit': 'd2bb0af5ba6d3198a3e99529c97eda1be0b5a093', 'avb_commit': '761178607206f4cb2af79ed9eec52d8cbd814adb'},
    'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'sha256': {name: sha(dist / name) for name in ['boot-bakasu.img', 'Image', 'stock.config', 'kernel.config', 'kernel-integration.patch']},
    'limitations': ['AVB NONE; unlocked bootloader required', 'kernel release equality does not establish full ABI compatibility', 'this build has not been device tested'],
}
(dist / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
