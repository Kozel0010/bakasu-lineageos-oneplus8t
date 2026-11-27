#!/usr/bin/env python3
import datetime
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
i = json.loads((p / 'inputs.json').read_text())
v = json.loads((p / 'verification.json').read_text())
report = json.loads((p / 'report.json').read_text())
if v['stock_sha256'] != i['boot']['sha256'] or v['avb_algorithm'] != 'NONE' or not v['requires_unlocked_bootloader']:
    raise SystemExit('inconsistent verification report')
print(f'''# OnePlus 8T / kebab — BakaSU

- ROM: `{i['rom']['filename']}`
- Stock boot SHA-256: `{i['boot']['sha256']}`
- Kernel commit: `{i['kernel_commit']}`
- BakaSU commit: `{i['bakasu_commit']}`
- Kernel release: `{report['kernel_release']}`
- Toolchain: AOSP Clang r596125 / 22.0.2 (Git `383d35d98a3e1635d2e3a88d866b125d7d20a0c1`)
- Build report time: {datetime.datetime.now(datetime.timezone.utc).isoformat()}
''')
