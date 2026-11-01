"""Narrow client for an optional isolated runner. This process has no Codex credentials."""
import asyncio
import os

import httpx


class RemoteEngine:
    def __init__(self):
        self.operation_lock = asyncio.Lock()
        self.update = {'status': 'idle', 'message': ''}
        self.login = None

    async def request(self, path, body=None, timeout=50):
        url = os.getenv('ENGINE_URL', 'http://runner:8001').rstrip('/')
        token = os.getenv('ENGINE_TOKEN', '')
        if len(token) < 32:
            raise RuntimeError('Codex 연동이 설정되지 않았습니다. 외부 JSON 방식은 계속 사용할 수 있습니다.')
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
                response = await client.request('GET' if body is None else 'POST', url + path,
                    headers={'Authorization': 'Bearer ' + token}, json=body)
            if response.status_code != 200:
                raise RuntimeError('Codex 실행 서비스가 요청을 처리하지 못했습니다. 연결 상태를 확인해 주세요.')
            return response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError('Codex 실행 서비스에 연결할 수 없습니다. 외부 JSON 방식은 계속 사용할 수 있습니다.') from exc

    async def call(self, method, params=None):
        # Never provide a general JSON-RPC bridge to the browser or caller.
        if method == 'account/read':
            return {'account': (await self.status()).get('account')}
        if method == 'account/logout':
            return await self.request('/logout', {})
        raise ValueError('허용되지 않은 엔진 작업입니다.')

    async def status(self):
        result = await self.request('/status')
        self.login, self.update = result.get('login'), result['update']
        return result

    async def models(self):
        return await self.request('/models')

    async def start_login(self):
        return await self.request('/login', {})

    async def analyze(self, images, mode, config, focus):
        import base64
        return await self.request('/analyze', {
            'images': [base64.b64encode(path.read_bytes()).decode('ascii') for path in images],
            'mode': mode, 'model': config['model'], 'effort': config['effort'],
            'language': config['language'], 'focus': focus,
        }, timeout=1220)

    async def run_update(self):
        try:
            self.update = await self.request('/update', {})
        except Exception:
            self.update = {'status': 'failed', 'message': '업데이트 서비스 연결을 확인해 주세요.'}

    async def stop(self):
        pass


engine = RemoteEngine()
