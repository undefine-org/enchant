#!/usr/bin/env python3
import importlib.util
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

path=Path(__file__).resolve().parents[2]/'examples/scene-renderer/review_server.py'
spec=importlib.util.spec_from_file_location('scene_review_server',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Quiet(module.Handler):
    def log_message(self,*args):pass

class RangeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='bl-review-server-')
        Path(self.temp.name,'film.mp4').write_bytes(b'0123456789')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=self.temp.name))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_address[1]}/film.mp4'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def get(self,value=None,method='GET'):
        return urllib.request.urlopen(urllib.request.Request(self.url,headers={'Range':value} if value else {},method=method))
    def test_full(self):
        with self.get() as response:
            self.assertEqual(response.status,200);self.assertEqual(response.read(),b'0123456789')
            self.assertEqual(response.headers['Accept-Ranges'],'bytes')
    def test_bounded(self):
        with self.get('bytes=2-5') as response:
            self.assertEqual(response.status,206);self.assertEqual(response.read(),b'2345')
            self.assertEqual(response.headers['Content-Range'],'bytes 2-5/10')
    def test_open_end(self):
        with self.get('bytes=7-') as response:self.assertEqual(response.read(),b'789')
    def test_suffix(self):
        with self.get('bytes=-3') as response:self.assertEqual(response.read(),b'789')
    def test_head(self):
        with self.get('bytes=2-5','HEAD') as response:
            self.assertEqual(response.headers['Content-Length'],'4');self.assertEqual(response.read(),b'')
    def test_invalid(self):
        for value in ['bytes=10-','bytes=4-2','bytes=-0','bytes=0-1,4-5','bytes=-']:
            with self.assertRaises(urllib.error.HTTPError) as error:self.get(value)
            self.assertEqual(error.exception.code,416)
            self.assertEqual(error.exception.headers['Content-Range'],'bytes */10')
            error.exception.close()

if __name__=='__main__':unittest.main()
