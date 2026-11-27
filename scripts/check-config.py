#!/usr/bin/env python3
"""Reject accidental driver/ABI/security configuration changes."""
import re
import sys
from pathlib import Path


def read_config(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        match = re.fullmatch(r'(CONFIG_\w+)=(.*)', line)
        if match:
            result[match[1]] = match[2]
        else:
            match = re.fullmatch(r'# (CONFIG_\w+) is not set', line)
            if match:
                result[match[1]] = 'n'
    return result


if __name__ == '__main__':
    original, built = map(read_config, sys.argv[1:])
    metadata = {
        'CONFIG_CC_VERSION_TEXT', 'CONFIG_CC_IS_CLANG', 'CONFIG_CLANG_VERSION',
        'CONFIG_GCC_VERSION', 'CONFIG_LD_VERSION', 'CONFIG_LLD_VERSION',
        'CONFIG_LD_IS_LLD', 'CONFIG_LD_IS_BFD', 'CONFIG_AS_IS_LLVM',
        'CONFIG_AS_IS_GNU', 'CONFIG_AS_VERSION',
    }
    differences = []
    for key in sorted(original.keys() | built.keys()):
        if key.startswith('CONFIG_KSU') or key in metadata:
            continue
        if original.get(key, 'n') != built.get(key, 'n'):
            differences.append(f'{key}: {original.get(key, "n")} -> {built.get(key, "n")}')
    if differences:
        raise SystemExit('Unexpected config changes:\n' + '\n'.join(differences))
    print('Original driver, ABI and security configuration preserved.')
