"""Enforce authentication and byte limits before a request reaches form parsing."""
import os
from urllib.parse import urlsplit

from fastapi import Request
from starlette.responses import JSONResponse

WRITE = {'POST', 'PUT', 'PATCH', 'DELETE'}
UPLOAD_PATHS = {'/api/jobs', '/api/export-request', '/api/library/import'}
MAX_BODY = 31 * 1024 * 1024


class RequestGuard:
    def __init__(self, app, authorize):
        self.app, self.authorize = app, authorize

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path, method = scope['path'], scope['method']
        origin = os.getenv('APP_URL', 'http://localhost:61920').rstrip('/')
        expected_host = urlsplit(origin).netloc.lower()

        async def reject(code, message):
            await JSONResponse({'detail': message}, status_code=code)(scope, receive, send)

        if path != '/api/health' and request.headers.get('host', '').lower() != expected_host:
            return await reject(400, '허용되지 않은 호스트입니다.')
        if path.startswith('/api/') and path!='/api/health' and request.headers.get('sec-fetch-site') in {'cross-site','same-site'}:
            return await reject(403, '다른 사이트에서 보낸 요청입니다.')
        if method in WRITE:
            supplied_origin = request.headers.get('origin')
            if supplied_origin is not None and supplied_origin.rstrip('/') != origin:
                return await reject(403, '허용되지 않은 요청 출처입니다.')
            if request.headers.get('sec-fetch-site') not in (None, 'same-origin', 'none'):
                return await reject(403, '다른 사이트에서 보낸 변경 요청입니다.')
            # A non-simple header blocks cross-origin form submissions even if Origin is missing.
            if request.headers.get('x-artstyle-request') != '1':
                return await reject(403, '요청 확인 헤더가 필요합니다.')
        if path.startswith('/api/') and path not in {'/api/login', '/api/health'}:
            token = await self.authorize(request)
            if not token:
                return await reject(401, '로그인이 필요합니다.')
            scope.setdefault('state', {})['auth_token'] = token
        if method in WRITE:
            content_type = request.headers.get('content-type', '').split(';', 1)[0].lower()
            if path in UPLOAD_PATHS and content_type != 'multipart/form-data':
                return await reject(415, '이미지는 multipart/form-data로 보내 주세요.')
            limit = MAX_BODY if path in UPLOAD_PATHS else 2*1024*1024 if path=='/api/library/preview' else 16*1024
            try:
                declared = int(request.headers.get('content-length', '0'))
            except ValueError:
                return await reject(400, '잘못된 요청 크기입니다.')
            if declared < 0 or declared > limit:
                return await reject(413, '요청 크기가 허용 범위를 넘었습니다.')
            # Count streamed bytes too: Content-Length is controlled by the client.
            chunks, size = [], 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                block = message.get('body', b'')
                size += len(block)
                if size > limit:
                    return await reject(413, '요청 크기가 허용 범위를 넘었습니다.')
                chunks.append(block)
                if not message.get('more_body'):
                    break
            body = b''.join(chunks)
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                return await receive()
        else:
            bounded_receive = receive

        async def protected_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'), (b'referrer-policy', b'same-origin'),
                ])
            await send(message)
        await self.app(scope, bounded_receive, protected_send)
