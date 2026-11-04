import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import template, util

GIT = shutil.which('git')
ME = ['-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'commit.gpgsign=false']


def sh(cwd, *args):
    return subprocess.run(['git', '-C', cwd, *ME, *args], check=True, capture_output=True, text=True).stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='\n') as f:
        f.write(text)


def tree_bytes(folder):
    out = {}
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != '.git']
        for n in files:
            p = os.path.join(root, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, folder)] = f.read()
    return out


@unittest.skipUnless(GIT, 'needs git')
class Template(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.src = f'{t}/companion'
        write(f'{self.src}/requirements.txt', 'slack-bolt==1.29.0\nPyJWT==2.10.1\ncryptography==44.0.0\n')
        write(f'{self.src}/bot/main.py', 'print("hello")\n')
        self.cfg = {
            'data': f'{t}/data',
            'agents': [{'id': 'sara', 'path': f'{t}/agents/sara'}],
            'companions': [{'name': 'helper', 'agent': 'sara'}],
        }
        self.comp = self.cfg['companions'][0]
        self.co = f'{t}/agents/sara/workspace/companions/helper'
        os.makedirs(f'{self.cfg["data"]}/companions/helper')
        self.seed()
        for patch in (
            mock.patch.object(template, 'SOURCE', self.src),
            mock.patch.object(template, 'version', lambda: 'test'),
            mock.patch.object(template, 'START_TIMEOUT_S', 2),
            mock.patch.object(template, 'SETTLE_S', 0),
            mock.patch.object(template, 'POLL_S', 0.01),
            mock.patch.object(template, 'restart', self.fake_restart),
        ):
            self.enterContext(patch)
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.restarts, self.comes_up_as = [], 'running'

    def seed(self, branch=True):
        shutil.copytree(self.src, self.co)
        sh(self.co, 'init', '-q', '-b', 'main')
        sh(self.co, 'add', '-A')
        sh(self.co, 'commit', '-q', '-m', 'from agentlab seed')
        if branch:
            sh(self.co, 'branch', 'template')

    def fake_restart(self, _cfg, comp):
        self.restarts.append(sh(self.co, 'rev-parse', 'HEAD'))
        state = self.comes_up_as if len(self.restarts) == 1 else 'running'
        write(
            f'{self.tmp.name}/agents/sara/workspace/.companion/{comp["name"]}/status.json',
            json.dumps({'state': state, 'updated': time.time() + 1, 'error': 'boom' if state == 'failed' else ''}),
        )
        return True

    def agent_commits(self, path, text, message):
        write(f'{self.co}/{path}', text)
        sh(self.co, 'commit', '-q', '-am', message)

    def run_update(self):
        return template.update_all(self.cfg, util.Plan(False))['helper']

    def test_up_to_date_is_a_no_op(self):
        before = sh(self.co, 'rev-parse', 'HEAD')
        r = self.run_update()
        self.assertEqual(r['result'], 'up-to-date')
        self.assertEqual(sh(self.co, 'rev-parse', 'HEAD'), before)
        self.assertEqual(self.restarts, [])

    def test_clean_merge_keeps_the_agents_work_and_restarts(self):
        self.agent_commits('bot/main.py', 'print("hello from sara")\n', 'feat: greet')
        write(f'{self.src}/requirements.txt', 'slack-bolt==1.30.0\nPyJWT==2.15.1\ncryptography==50.0.2\n')
        r = self.run_update()
        self.assertEqual(r['result'], 'merged', r)
        self.assertIn('restarted and running', r['detail'])
        with open(f'{self.co}/bot/main.py') as f:
            self.assertEqual(f.read(), 'print("hello from sara")\n')
        with open(f'{self.co}/requirements.txt') as f:
            self.assertIn('slack-bolt==1.30.0', f.read())
        log = sh(self.co, 'log', '-1', '--format=%s%n%an%n%P')
        subject, author, parents = log.splitlines()
        self.assertTrue(subject.startswith('chore: merge agentlab template '))
        self.assertEqual(author, 'agentlab')
        self.assertEqual(len(parents.split()), 2)
        self.assertEqual(len(self.restarts), 1)
        self.assertEqual(self.run_update()['result'], 'up-to-date')

    def test_an_agent_change_identical_to_the_template_merges_cleanly(self):
        self.agent_commits('requirements.txt', 'slack-bolt==1.29.0\nPyJWT==2.15.1\ncryptography==44.0.0\n', 'fix: jwt')
        write(f'{self.src}/requirements.txt', 'slack-bolt==1.30.0\nPyJWT==2.15.1\ncryptography==50.0.2\n')
        r = self.run_update()
        self.assertEqual(r['result'], 'merged', r)
        with open(f'{self.co}/requirements.txt') as f:
            self.assertEqual(f.read(), 'slack-bolt==1.30.0\nPyJWT==2.15.1\ncryptography==50.0.2\n')

    def test_a_file_with_one_shared_and_one_own_change_still_needs_a_person(self):
        self.agent_commits('requirements.txt', 'slack-bolt==1.29.0\nPyJWT==2.15.1\ncryptography==99\n', 'fix: mine')
        write(f'{self.src}/requirements.txt', 'slack-bolt==1.30.0\nPyJWT==2.15.1\ncryptography==50.0.2\n')
        head = sh(self.co, 'rev-parse', 'HEAD')
        r = self.run_update()
        self.assertEqual(r['result'], 'conflict')
        self.assertEqual(sh(self.co, 'rev-parse', 'HEAD'), head)
        self.assertEqual(sh(self.co, 'status', '--porcelain'), '')

    def test_a_conflict_is_aborted_and_leaves_the_checkout_byte_identical(self):
        self.agent_commits('bot/main.py', 'print("mine")\n', 'feat: mine')
        write(f'{self.src}/bot/main.py', 'print("theirs")\n')
        head, files = sh(self.co, 'rev-parse', 'HEAD'), tree_bytes(self.co)
        r = self.run_update()
        self.assertEqual(r['result'], 'conflict')
        self.assertIn('bot/main.py', r['detail'])
        self.assertEqual(sh(self.co, 'rev-parse', 'HEAD'), head)
        self.assertEqual(tree_bytes(self.co), files)
        self.assertEqual(sh(self.co, 'status', '--porcelain'), '')
        self.assertEqual(self.restarts, [])
        self.assertIn('agentlab template test', sh(self.co, 'log', '-1', '--format=%s', 'template'))

    def test_uncommitted_work_is_left_alone(self):
        write(f'{self.co}/bot/main.py', 'print("half done")\n')
        write(f'{self.src}/requirements.txt', 'slack-bolt==1.30.0\nPyJWT==2.15.1\ncryptography==50.0.2\n')
        r = self.run_update()
        self.assertEqual(r['result'], 'skipped')
        self.assertIn('uncommitted', r['detail'])
        with open(f'{self.co}/bot/main.py') as f:
            self.assertEqual(f.read(), 'print("half done")\n')
        sh(self.co, 'commit', '-q', '-am', 'feat: done')
        self.assertEqual(self.run_update()['result'], 'merged')

    def test_a_companion_that_fails_to_start_gets_exactly_that_merge_undone(self):
        self.agent_commits('bot/main.py', 'print("mine")\n', 'feat: mine')
        mine = sh(self.co, 'rev-parse', 'HEAD')
        write(f'{self.src}/requirements.txt', 'broken==0\n')
        self.comes_up_as = 'failed'
        r = self.run_update()
        self.assertEqual(r['result'], 'reverted')
        self.assertIn('boom', r['detail'])
        self.assertEqual(sh(self.co, 'rev-parse', 'HEAD'), mine)
        self.assertEqual(len(self.restarts), 2)

    def test_a_checkout_from_before_the_template_branch_gets_one_at_the_seed(self):
        shutil.rmtree(self.co)
        self.seed(branch=False)
        seed = sh(self.co, 'rev-list', '--max-parents=0', 'HEAD')
        self.agent_commits('bot/main.py', 'print("mine")\n', 'feat: mine')
        write(f'{self.src}/requirements.txt', 'slack-bolt==1.30.0\nPyJWT==2.15.1\ncryptography==44.0.0\n')
        r = self.run_update()
        self.assertEqual(r['result'], 'merged', r)
        self.assertEqual(sh(self.co, 'rev-parse', 'template^'), seed)

    def test_dry_run_reports_without_writing(self):
        write(f'{self.src}/requirements.txt', 'slack-bolt==1.30.0\n')
        refs = sh(self.co, 'for-each-ref')
        objects = sh(self.co, 'count-objects', '-v')
        plan = util.Plan(True)
        r = template.update_all(self.cfg, plan)['helper']
        self.assertEqual(r['result'], 'would-update')
        self.assertEqual(sh(self.co, 'for-each-ref'), refs)
        self.assertEqual(sh(self.co, 'count-objects', '-v'), objects)
        self.assertFalse(os.path.exists(template.state_path(self.cfg)))

    def test_results_are_recorded_for_status_and_the_hub(self):
        write(f'{self.src}/bot/main.py', 'print("theirs")\n')
        self.agent_commits('bot/main.py', 'print("mine")\n', 'feat: mine')
        self.run_update()
        with open(template.state_path(self.cfg)) as f:
            self.assertEqual(json.load(f)['helper']['result'], 'conflict')
        with open(f'{self.cfg["data"]}/companions/helper/template.json') as f:
            self.assertEqual(json.load(f)['result'], 'conflict')
        self.assertTrue(any(line.startswith('helper: template conflict') for line in template.summary(self.cfg)))

    def test_a_symlinked_checkout_is_refused(self):
        real = f'{self.tmp.name}/elsewhere'
        shutil.move(self.co, real)
        os.symlink(real, self.co)
        r = self.run_update()
        self.assertEqual(r['result'], 'skipped')
        self.assertIn('not a plain folder', r['detail'])


if __name__ == '__main__':
    unittest.main()
