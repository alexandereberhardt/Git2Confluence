# _system/passten/publisher.py
import json
import urllib.request

AUTO_GENERATED_MARKER = '<!-- passten-auto-generated -->'

class ConfluencePublisher:
    def __init__(self, mcp_url: str = 'http://localhost:8001/mcp'):
        self.mcp_url = mcp_url
        self._session_id = None
        self._request_id = 0

    def _mcp_call(self, tool: str, arguments: dict) -> dict:
        self._request_id += 1
        payload = json.dumps({
            'jsonrpc': '2.0',
            'id': self._request_id,
            'method': 'tools/call',
            'params': {'name': tool, 'arguments': arguments},
        }).encode()
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        }
        if self._session_id:
            headers['mcp-session-id'] = self._session_id
        req = urllib.request.Request(self.mcp_url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            self._session_id = resp.headers.get('mcp-session-id', self._session_id)
            body = resp.read().decode()
            if body.startswith('event:') or body.startswith('data:'):
                for line in body.splitlines():
                    if line.startswith('data:'):
                        data = json.loads(line[5:].strip())
                        if 'result' in data:
                            content = data['result'].get('content', [])
                            if content and content[0].get('type') == 'text':
                                return self._parse_text(content[0]['text'])
                            return data['result']
                return {}
            data = json.loads(body)
            if 'result' in data:
                content = data['result'].get('content', [])
                if content and content[0].get('type') == 'text':
                    return self._parse_text(content[0]['text'])
                return data['result']
            return data

    @staticmethod
    def _parse_text(text: str) -> dict:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {'raw': text}

    def _initialize(self):
        payload = json.dumps({
            'jsonrpc': '2.0', 'id': 0, 'method': 'initialize',
            'params': {
                'protocolVersion': '2025-03-26',
                'capabilities': {},
                'clientInfo': {'name': 'passten-generator', 'version': '1.0'},
            },
        }).encode()
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        req = urllib.request.Request(self.mcp_url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            self._session_id = resp.headers.get('mcp-session-id')

    def create_page(self, space_key: str, parent_id: str, title: str, body: str) -> dict:
        return self._mcp_call(tool='create_page', arguments={
            'space_key': space_key,
            'parent_id': parent_id,
            'title': title,
            'body': body,
        })

    def update_page(self, page_id: str, title: str, body: str) -> dict:
        return self._mcp_call(tool='update_page', arguments={
            'page_id': page_id,
            'title': title,
            'body': body,
        })

    def find_page(self, space_key: str, title: str) -> dict | None:
        result = self._mcp_call(tool='search_content', arguments={'query': title, 'space_key': space_key, 'limit': 5})
        results = result.get('results', [])
        for r in results:
            if r.get('title') == title:
                return r
        return None

    def upsert_page(self, space_key: str, parent_id: str, title: str, body: str) -> dict:
        existing = self.find_page(space_key, title)
        if existing:
            return self.update_page(page_id=existing['id'], title=title, body=body)
        return self.create_page(space_key=space_key, parent_id=parent_id, title=title, body=body)
