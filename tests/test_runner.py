import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock,patch

from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app import runner


class RunnerBoundaryTests(unittest.TestCase):
    def test_unauthenticated_requests_cannot_start_login_or_read_account(self):
        with patch.dict(os.environ,{'ENGINE_TOKEN':'t'*64}),TestClient(runner.app) as client:
            for path in ('/status','/models'):
                self.assertEqual(client.get(path).status_code,401)
            self.assertEqual(client.post('/login').status_code,401)
            self.assertEqual(client.get('/health').status_code,200)

    def test_paths_urls_and_option_injection_do_not_reach_codex(self):
        headers={'Authorization':'Bearer '+'t'*64}
        payload={'images':['../../auth.json'],'mode':'style','model':'test-model','effort':'high','language':'en'}
        with patch.dict(os.environ,{'ENGINE_TOKEN':'t'*64}),patch.object(runner.engine,'analyze',new_callable=AsyncMock) as analyze,TestClient(runner.app) as client:
            self.assertEqual(client.post('/analyze',headers=headers,json=payload).status_code,400)
            payload['model']='--disable-sandbox'
            self.assertEqual(client.post('/analyze',headers=headers,json=payload).status_code,422)
            self.assertEqual(client.post('/rpc',headers=headers,json={'method':'exec'}).status_code,404)
            analyze.assert_not_awaited()

    def test_login_response_never_exposes_cache_fields(self):
        value=runner.public_login({'status':'pending','userCode':'EXAMPLE','verificationUrl':'https://auth.openai.com/codex/device','loginId':'private','access_token':'private'})
        self.assertNotIn('access_token',value)
        self.assertNotIn('loginId',value)
