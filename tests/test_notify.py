import importlib.util
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('notify', 'scripts/notify.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.env = {'BUILD_STATUS': 'success', 'BUILD_EXISTS': 'no', 'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_SERVER_URL': 'https://github.com', 'GITHUB_RUN_ID': '12'}
        self.metadata = {'rom': {'filename': 'rom.zip'}, 'boot': {'sha256': 'a' * 64}, 'kernel_commit': 'b' * 40, 'bakasu_commit': 'c' * 40, 'identity': 'd' * 64}

    def test_success_includes_release_and_warning(self):
        text = m.message(self.env, self.metadata)
        self.assertIn('rom.zip', text)
        self.assertIn('not device tested', text)
        self.assertIn('/releases/tag/kebab-', text)

    def test_duplicate_and_failure(self):
        self.env['BUILD_EXISTS'] = 'yes'
        self.assertIn('no new build', m.message(self.env, self.metadata))
        self.env['BUILD_STATUS'] = 'failure'
        self.assertIn('workflow failure', m.message(self.env))
        self.assertIn('/actions/runs/12', m.message(self.env))

    def test_start_without_metadata(self):
        self.env.update(BUILD_STATUS='started', BUILD_DATE='20261120')
        self.assertIn('20261120', m.message(self.env))


if __name__ == '__main__':
    unittest.main()
