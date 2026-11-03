"""HTTP regression coverage for private Markdown and running-server identity."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        local = root / '.local'
        (local / 'reading').mkdir(parents=True)
        (root / 'dist').mkdir()
        cls.article_id = 'a' * 20
        item = {'id': cls.article_id, 'fingerprint': 'current'}
        for name, value in {
            'catalog': {cls.article_id: item},
            'editorial': {cls.article_id: {'fingerprint': 'current', 'selected': True}},
            'readings': {cls.article_id: {'fingerprint': 'current', 'status': 'verified'}},
        }.items():
            (local / (name + '.json')).write_text(json.dumps(value))
        cls.body = '# 原文\n\n私人伴读内容。\n'.encode()
        (local / 'reading' / (cls.article_id + '.md')).write_bytes(cls.body)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        script = '''import sys, pathlib, news, upgrade
news.ROOT=pathlib.Path(sys.argv[1]); news.LOCAL=news.ROOT/'.local'
upgrade.READING=news.LOCAL/'reading'
news.server_revision=lambda:'fixture-revision'
news.serve(int(sys.argv[2]))
'''
        cls.process = subprocess.Popen([sys.executable, '-c', script, str(root), str(cls.port)],
                                       cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(100):
            try:
                cls.opener.open(cls.base + '/api/health', timeout=1).close()
                return
            except (urllib.error.URLError, OSError):
                if cls.process.poll() is not None:
                    break
                time.sleep(.03)
        cls.process.terminate(); cls.process.wait(timeout=5); cls.temp.cleanup()
        raise RuntimeError('Preview fixture did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate(); cls.process.wait(timeout=5); cls.temp.cleanup()

    def test_health_identifies_running_download_capability(self):
        with self.opener.open(self.base + '/api/health') as response:
            data = json.load(response)
        self.assertEqual(data, {'app': 'ianyu-ai-news', 'revision': 'fixture-revision', 'markdownDownload': True})

    def test_verified_markdown_is_attachment_with_exact_bytes(self):
        with self.opener.open(self.base + '/api/reading/' + self.article_id + '.md') as response:
            self.assertEqual(response.read(), self.body)
            self.assertEqual(response.headers.get_content_type(), 'text/markdown')
            self.assertIn('attachment;', response.headers['Content-Disposition'])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_unavailable_and_cross_origin_requests_return_http_errors(self):
        path = '/api/reading/' + self.article_id + '.md'
        cases = [(path, {'Origin': 'https://example.com'}, 403),
                 (path, {'Host': 'example.com'}, 403),
                 ('/api/reading/' + 'b' * 20 + '.md', {}, 404),
                 ('/.local/reading/' + self.article_id + '.md', {}, 404)]
        for target, headers, status in cases:
            with self.subTest(target=target, headers=headers):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.opener.open(urllib.request.Request(self.base + target, headers=headers))
                self.assertEqual(caught.exception.code, status)
