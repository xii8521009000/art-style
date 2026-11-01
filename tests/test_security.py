import asyncio
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock,patch

from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app import main


class RequestSecurityTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'APP_URL':'http://testserver','APP_USERNAME':'admin','APP_PASSWORD_HASH':'600000:00000000000000000000000000000000:00'})
        self.env.start()
        self.database=patch.object(main.db,'query',return_value={'token_hash':'exists','attempts':1})
        self.database.start()
        self.client=TestClient(main.app)
        self.client.cookies.set(main.COOKIE,'a'*64)
        self.headers={'X-Artstyle-Request':'1','Origin':'http://testserver'}

    def tearDown(self):
        self.client.close();self.database.stop();self.env.stop()

    def test_missing_custom_header_null_and_cross_site_origins_fail(self):
        for headers in [{},{'Origin':'null','X-Artstyle-Request':'1'},
                        {'Origin':'https://evil.example','X-Artstyle-Request':'1'},
                        {**self.headers,'Sec-Fetch-Site':'same-site'}]:
            response=self.client.post('/api/engine/login',headers=headers)
            self.assertEqual(response.status_code,403)

    def test_unauthenticated_upload_is_rejected_before_raster_or_form_processing(self):
        self.client.cookies.clear()
        with patch.object(main,'prepare_images',new_callable=AsyncMock) as prepare:
            response=self.client.post('/api/library/import',headers=self.headers,files={'files':('bad.webp',b'not a raster','image/webp')},data={'response':'{}'})
        self.assertEqual(response.status_code,401)
        prepare.assert_not_awaited()

    def test_host_poisoning_and_cross_site_get_are_blocked(self):
        self.assertEqual(self.client.get('/api/me',headers={'Host':'evil.example'}).status_code,400)
        self.assertEqual(self.client.get('/api/me',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)

    def test_preview_works_without_cli_and_does_not_execute_embedded_markup(self):
        with patch.object(main.engine,'call',new_callable=AsyncMock) as engine:
            response=self.client.post('/api/library/preview',headers=self.headers,json={'response':'{"character_prompt":"<script>alert(1)</script>"}'})
        self.assertEqual(response.status_code,200)
        self.assertIn('<script>',response.json()['character_prompt'])
        engine.assert_not_awaited()

    def test_multipart_file_count_and_content_type_are_bounded(self):
        self.assertEqual(self.client.post('/api/export-request',headers=self.headers,data={'mode':'style'}).status_code,415)
        response=self.client.post('/api/library/import',headers=self.headers,
            files=[('files',(f'{i}.webp',b'x','image/webp')) for i in range(9)],data={'response':'{}'})
        self.assertEqual(response.status_code,400)

    def test_content_length_cannot_hide_a_larger_stream(self):
        body=(b'x'*9000 for _ in range(2))
        response=self.client.post('/api/login',headers={**self.headers,'Content-Length':'1','Content-Type':'application/json'},content=body)
        self.assertEqual(response.status_code,413)

    def test_no_openapi_and_legacy_experiments_off_by_default(self):
        self.assertEqual(self.client.get('/openapi.json').status_code,404)
        self.assertEqual(self.client.get('/api/experiments/anything/index.html').status_code,404)

    def test_cli_rpc_bridge_has_no_general_operation(self):
        with self.assertRaises(ValueError):asyncio.run(main.engine.call('exec/command',{'command':'anything'}))

    def test_login_attempt_is_reserved_before_hashing_and_excess_attempts_skip_hash(self):
        order=[]
        def database(statement,args=(),one=False):
            order.append('reserve' if statement.startswith('INSERT INTO login_attempts') else 'other')
            return {'attempts':1}
        def expensive(*args):
            order.append('hash');return b'\x01'
        with patch.object(main.db,'query',side_effect=database),patch.object(main.hashlib,'pbkdf2_hmac',side_effect=expensive):
            response=self.client.post('/api/login',headers=self.headers,json={'username':'admin','password':'incorrect'})
        self.assertEqual(response.status_code,401)
        self.assertLess(order.index('reserve'),order.index('hash'))
        with patch.object(main.db,'query',return_value={'attempts':11}),patch.object(main.hashlib,'pbkdf2_hmac') as hashing:
            self.assertEqual(self.client.post('/api/login',headers=self.headers,json={'username':'admin','password':'incorrect'}).status_code,429)
            hashing.assert_not_called()
