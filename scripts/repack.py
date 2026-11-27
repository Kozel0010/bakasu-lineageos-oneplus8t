#!/usr/bin/env python3
"""Repack with AOSP tools, then verify unchanged boot-v2 components."""
import hashlib
import json
import shlex
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_boot(path):
    data = Path(path).read_bytes()
    if data[:8] != b'ANDROID!':
        raise ValueError('Not an Android boot image')
    fields = struct.unpack_from('<10I', data, 8)
    kernel_size, _, ramdisk_size, _, second_size, _, _, page, version, _ = fields
    if version != 2 or page != 4096:
        raise ValueError(f'Expected boot header v2, page size 4096: {version}, {page}')
    recovery_size, recovery_offset, header_size, dtb_size, _ = struct.unpack_from('<IQIIQ', data, 1632)
    if header_size != 1660:
        raise ValueError(f'Unexpected header size {header_size}')
    align = lambda size: (size + page - 1) // page * page
    offset = page
    sections = {}
    for name, size in [('kernel', kernel_size), ('ramdisk', ramdisk_size), ('second', second_size)]:
        sections[name] = data[offset:offset + size]
        if len(sections[name]) != size:
            raise ValueError(f'Truncated {name}')
        offset += align(size)
    if recovery_size and recovery_offset != offset:
        raise ValueError('Unexpected recovery DTBO offset')
    sections['recovery_dtbo'] = data[offset:offset + recovery_size]
    offset += align(recovery_size)
    sections['dtb'] = data[offset:offset + dtb_size]
    if len(sections['dtb']) != dtb_size:
        raise ValueError('Truncated DTB')
    # Header id covers all v2 component bytes and lengths, including zero
    # lengths for absent second-stage and recovery DTBO components.
    sha = hashlib.sha1()
    for name in ('kernel', 'ramdisk', 'second', 'recovery_dtbo', 'dtb'):
        sha.update(sections[name])
        sha.update(struct.pack('<I', len(sections[name])))
    if data[576:596] != sha.digest():
        raise ValueError('Boot header SHA-1 does not match components')
    # Exclude only kernel_size, SHA-1 id and recovery_dtbo_offset from the
    # comparison. Everything else (addresses, cmdline, OS level, DTB) must match.
    metadata = data[0:8] + data[12:576] + data[608:1636] + data[1644:1660]
    return data, metadata, sections


def main():
    root, work, dist = (Path(p).resolve() for p in sys.argv[1:])
    lock = json.loads((root / 'build-lock.json').read_text())
    stock = root / 'boot.img'
    old_data, old_metadata, old_sections = parse_boot(stock)
    if digest(old_data) != lock['stock_boot_sha256']:
        raise ValueError('Wrong stock boot image')
    if len(old_data) != lock['partition_size']:
        raise ValueError('Stock boot partition size mismatch')
    image = dist / 'Image'
    arm64 = image.read_bytes()
    if arm64[56:60] != b'ARM\x64':
        raise ValueError('Expected an uncompressed arm64 Image')
    unpack = work / 'unpacked-stock'
    args_text = subprocess.check_output([
        sys.executable, str(work / 'mkbootimg/unpack_bootimg.py'),
        '--boot_img', str(stock), '--out', str(unpack), '--format', 'mkbootimg',
    ], text=True)
    args = shlex.split(args_text)
    index = args.index('--kernel')
    args[index + 1] = str(image)
    output = dist / 'boot-ksunext.img'
    subprocess.run([
        sys.executable, str(work / 'mkbootimg/mkbootimg.py'),
        *args, '--output', str(output),
    ], check=True)
    # The Lineage signing key is unavailable. Supply a fresh, explicitly
    # unsigned AVB footer with the correct hash and original partition size.
    avbtool = str(work / 'avb/avbtool.py')
    subprocess.run([
        sys.executable, avbtool, 'add_hash_footer', '--image', str(output),
        '--partition_name', 'boot', '--partition_size', str(lock['partition_size']),
        '--algorithm', 'NONE', '--salt', '00' * 32,
    ], check=True)
    new_data, new_metadata, new_sections = parse_boot(output)
    if new_metadata != old_metadata:
        raise ValueError('Boot header metadata unexpectedly changed')
    for name in ('ramdisk', 'second', 'recovery_dtbo', 'dtb'):
        if old_sections[name] != new_sections[name]:
            raise ValueError(f'{name} changed')
    if new_sections['kernel'] != arm64:
        raise ValueError('Packaged kernel differs from built Image')
    if new_sections['kernel'] == old_sections['kernel']:
        raise ValueError('Kernel was not replaced')
    if len(new_data) != lock['partition_size']:
        raise ValueError('Output partition size mismatch')
    info = subprocess.check_output([
        sys.executable, avbtool, 'info_image', '--image', str(output),
    ], text=True)
    if [line.split(':', 1)[1].strip() for line in info.splitlines() if line.startswith('Algorithm:')] != ['NONE']:
        raise ValueError('Expected AVB algorithm NONE')
    (dist / 'avb-info.txt').write_text(info)
    # avbtool resolves a named hash descriptor as <partition>.img.
    # Verify the generated output through an isolated boot.img alias.
    with tempfile.TemporaryDirectory(prefix='avb-verify-', dir=work) as verify_dir:
        verify_image = Path(verify_dir) / 'boot.img'
        verify_image.symlink_to(output)
        subprocess.run([
            sys.executable, avbtool, 'verify_image', '--image', str(verify_image),
        ], check=True)
    report = {
        'stock_sha256': digest(old_data), 'output_sha256': digest(new_data),
        'stock_header_hex': old_data[:1660].hex(),
        'stock_kernel_sha256': digest(old_sections['kernel']),
        'partition_size': len(new_data), 'header_version': 2,
        'avb_algorithm': 'NONE', 'requires_unlocked_bootloader': True,
        'preserved': {name: digest(new_sections[name]) for name in
                      ('ramdisk', 'second', 'recovery_dtbo', 'dtb')},
        'kernel_sha256': digest(new_sections['kernel']),
        'boot_tested': False,
    }
    (dist / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
