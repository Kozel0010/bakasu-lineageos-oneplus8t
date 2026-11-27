import copy
import hashlib
import importlib.util
import unittest

spec = importlib.util.spec_from_file_location('inputs', 'scripts/inputs.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def file(name, data=b'x'):
    return {'filename': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'url': 'https://mirrorbits.lineageos.org/full/kebab/20261120/' + name}


def build():
    return {'date': '2026-11-20', 'type': 'nightly', 'version': '24.0', 'files': [file('lineage-24.0-20261120-nightly-kebab-signed.zip'), file('boot.img'), file('build-manifest.xml')]}


class InputsTest(unittest.TestCase):
    def setUp(self):
        self.build = build()
        self.build['files'][1]['size'] = 100663296
        self.commit = 'a' * 40
        self.xml = ('<manifest><remote name="github" fetch=".."/><default remote="github"/><project name="LineageOS/android_kernel_oneplus_sm8250" path="kernel/oneplus/sm8250" revision="' + self.commit + '"/></manifest>').encode()

    def test_select(self):
        self.assertEqual(m.select([self.build])['date'], '20261120')
        with self.assertRaises(ValueError):
            m.select([self.build], '20261121')
        with self.assertRaises(ValueError):
            m.select([self.build, self.build])

    def test_manifest(self):
        self.assertEqual(m.kernel_commit(self.xml), self.commit)
        with self.assertRaises(ValueError):
            m.kernel_commit(self.xml.replace(self.commit.encode(), b'lineage-24.0'))
        with self.assertRaises(ValueError):
            m.kernel_commit(self.xml.replace(b'</manifest>', b'<include name="extra.xml"/></manifest>'))

    def test_checksum(self):
        f = file('boot.img')
        m.verify(b'x', f)
        with self.assertRaises(ValueError):
            m.verify(b'y', f)
        with self.assertRaises(ValueError):
            m.verify(b'xx', f)

    def test_identity(self):
        b = m.select([self.build])
        other = copy.deepcopy(b)
        other['boot']['sha256'] = 'f' * 64
        self.assertNotEqual(m.identity(b, self.commit), m.identity(other, self.commit))
        self.assertNotEqual(m.identity(b, self.commit), m.identity(b, 'b' * 40))
        self.assertEqual(m.identity(b, self.commit), m.identity(b, self.commit))


if __name__ == '__main__':
    unittest.main()
