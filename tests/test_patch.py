import subprocess
import tempfile
import unittest
from pathlib import Path


class PatchTest(unittest.TestCase):
    def test_unrelated_source_is_rejected(self):
        patch = Path('patches/kernel-integration.patch').resolve()
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['git', 'init', '-q', d], check=True)
            (Path(d) / 'fs').mkdir()
            (Path(d) / 'fs' / 'exec.c').write_text('incompatible kernel\n')
            result = subprocess.run(['git', '-C', d, 'apply', '--check', str(patch)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
