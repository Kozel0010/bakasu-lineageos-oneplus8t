import hashlib
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('repack', 'scripts/repack.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def image():
    data = bytearray(4096 * 4)
    data[:8] = b'ANDROID!'
    struct.pack_into('<10I', data, 8, 4, 0, 3, 0, 0, 0, 0, 4096, 2, 0)
    struct.pack_into('<IQIIQ', data, 1632, 0, 0, 1660, 2, 0)
    parts = (b'kern', b'ram', b'', b'', b'dt')
    data[4096:4100] = parts[0]
    data[8192:8195] = parts[1]
    data[12288:12290] = parts[4]
    h = hashlib.sha1()
    for part in parts:
        h.update(part)
        h.update(struct.pack('<I', len(part)))
    data[576:596] = h.digest()
    return data


class BootTest(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'boot.img'
            p.write_bytes(data)
            return m.parse_boot(p)

    def test_components_and_header(self):
        data = image()
        _, header, parts = self.parse(data)
        self.assertEqual(parts['kernel'], b'kern')
        self.assertEqual(parts['ramdisk'], b'ram')
        self.assertEqual(parts['dtb'], b'dt')
        changed = image()
        changed[64] ^= 1
        self.assertNotEqual(header, self.parse(changed)[1])

    def test_rejects_component_corruption(self):
        data = image()
        data[8192] ^= 1
        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_unsupported_header(self):
        data = image()
        struct.pack_into('<I', data, 40, 3)
        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_truncation(self):
        with self.assertRaises(ValueError):
            self.parse(image()[:12289])


if __name__ == '__main__':
    unittest.main()
