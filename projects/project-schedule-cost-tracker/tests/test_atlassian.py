import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tracker.atlassian import publish
from tracker.core import Task

class Handler(BaseHTTPRequestHandler):
    requests = []
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.requests.append((self.path, data))
        result = {'key':'DEMO-1'} if self.path == '/rest/api/3/issue' else {'id':'123'}
        body = json.dumps(result).encode(); self.send_response(200); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass

class AtlassianTests(unittest.TestCase):
    def test_publishes_issues_and_escaped_decisions(self):
        Handler.requests = []
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            result = publish([Task('A','Design',2,[],100,20,.2)], 'Use <steel>', f'http://127.0.0.1:{server.server_port}', 'test@example.invalid', 'fake', 'DEMO','DOC','Decisions')
            self.assertEqual(result, (['DEMO-1'],'123'))
            self.assertEqual(Handler.requests[0][1]['fields']['summary'], 'Design')
            self.assertIn('Use &lt;steel&gt;', Handler.requests[1][1]['body']['storage']['value'])
        finally:
            server.shutdown(); server.server_close(); thread.join()
