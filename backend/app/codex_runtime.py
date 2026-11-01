import asyncio
import json
import os
from pathlib import Path
import tempfile

from .prompts import SCHEMA, build_prompt
from .style_contract import compile_style_result


def codex_env():
    return {k: v for k, v in os.environ.items() if k in {
        'PATH', 'HOME', 'CODEX_HOME', 'LANG', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'TMPDIR', 'SYSTEMROOT'}}


class CodexEngine:
    def __init__(self):
        self.process = None
        self.pending = {}
        self.counter = 0
        self.start_lock = asyncio.Lock()
        self.operation_lock = asyncio.Lock()
        self.login = None
        self.update = {'status': 'idle', 'message': ''}
        self.reader_task = None

    async def start(self):
        async with self.start_lock:
            if self.process and self.process.returncode is None:
                return
            self.process = await asyncio.create_subprocess_exec(
                'codex', 'app-server', '-c', 'cli_auth_credentials_store="file"',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=codex_env())
            self.reader_task = asyncio.create_task(self.read())
            await self.call('initialize', {'clientInfo': {'name': 'artstyle', 'title': 'Art Style', 'version': '1.0.0'}}, start=False)
            self.process.stdin.write(b'{"method":"initialized"}\n')
            await self.process.stdin.drain()

    async def read(self):
        process = self.process
        try:
            async for line in process.stdout:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                future = self.pending.get(msg.get('id'))
                if future and not future.done():
                    if 'error' in msg:
                        future.set_exception(RuntimeError(msg['error'].get('message', 'Codex 요청 실패')))
                    else:
                        future.set_result(msg.get('result', {}))
                elif msg.get('method') == 'account/login/completed':
                    self.login = {**(self.login or {}), **msg.get('params', {}), 'status': 'completed' if msg['params'].get('success') else 'failed'}
        finally:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(RuntimeError('Codex 연결이 종료되었습니다. 다시 시도해 주세요.'))

    async def call(self, method, params=None, start=True):
        if start:
            await self.start()
        self.counter += 1
        request_id = self.counter
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            self.process.stdin.write((json.dumps({'id': request_id, 'method': method, 'params': params or {}}) + '\n').encode())
            await self.process.stdin.drain()
            return await asyncio.wait_for(future, timeout=45)
        finally:
            self.pending.pop(request_id, None)

    async def stop(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    async def models(self):
        result, data, cursor = {}, [], None
        for _ in range(10):
            result = await self.call('model/list', {'limit': 100, 'cursor': cursor, 'includeHidden': False})
            data += [m for m in result.get('data', []) if 'image' in m.get('inputModalities', ['text', 'image'])]
            cursor = result.get('nextCursor')
            if not cursor:
                break
        return data

    async def version(self):
        p = await asyncio.create_subprocess_exec('codex', '--version', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await p.communicate()
        return out.decode().strip()

    async def status(self):
        result = await self.call('account/read', {'refreshToken': False})
        return {'account': result.get('account'), 'version': await self.version(), 'login': self.login,
                'update': self.update, 'busy': self.operation_lock.locked()}

    async def start_login(self):
        if self.login and self.login.get('status') == 'pending':
            await self.call('account/login/cancel', {'loginId': self.login['loginId']})
        self.login = {**await self.call('account/login/start', {'type': 'chatgptDeviceCode'}), 'status': 'pending'}
        return self.login

    async def analyze(self, image, mode, config, focus):
        images = [Path(image)] if isinstance(image, (str, Path)) else [Path(path) for path in image]
        if not 1 <= len(images) <= 8:
            raise ValueError('이미지는 1~8장으로 선택해 주세요.')
        with tempfile.TemporaryDirectory(prefix='artstyle-') as directory:
            root = Path(directory)
            (root / 'schema.json').write_text(json.dumps(SCHEMA), encoding='utf-8')
            # Isolate analysis from the application's source, secrets and other uploads.
            references = []
            for index, source in enumerate(images):
                target = root / (f'reference-{index+1:02}.webp' if len(images) > 1 else 'reference.webp')
                target.write_bytes(source.read_bytes())
                references.extend(['--image', str(target)])
            args = ['codex', 'exec', '--ignore-user-config', '--ignore-rules', '--skip-git-repo-check', '--ephemeral',
                    '--sandbox', 'read-only', '-c', 'approval_policy="never"', '-c', 'web_search="disabled"',
                    '-c', 'cli_auth_credentials_store="file"', '-c', f'model_reasoning_effort="{config["effort"]}"',
                    '--disable', 'shell_tool', '--disable', 'unified_exec', '--disable', 'apps',
                    '--disable', 'multi_agent', '--disable', 'image_generation', '--disable', 'browser_use',
                    '--disable', 'computer_use', '--disable', 'plugins',
                    '--model', config['model'], *references,
                    '--output-schema', str(root / 'schema.json'), '--output-last-message', str(root / 'answer.json'),
                    '--cd', directory, '--color', 'never', '-']
            proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=codex_env())
            try:
                _, err = await asyncio.wait_for(proc.communicate(build_prompt(mode, config['language'], focus, len(images)).encode()), 1200)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                proc.kill()
                await proc.wait()
                raise
            if proc.returncode != 0 or not (root / 'answer.json').exists():
                raise RuntimeError('Codex 분석을 완료하지 못했습니다. 계정 연결과 모델 설정을 확인해 주세요.')
            result = json.loads((root / 'answer.json').read_text(encoding='utf-8'))
            if not isinstance(result, dict) or not isinstance(result.get('warnings'), list):
                raise RuntimeError('Codex 응답 형식이 올바르지 않습니다.')
            for field, required in [('style_prompt', mode in ('both', 'style')), ('character_prompt', mode in ('both', 'character'))]:
                value = result.get(field)
                if value is not None and not isinstance(value, str):
                    raise RuntimeError('Codex 프롬프트 형식이 올바르지 않습니다.')
                if not required:
                    result[field] = None
            result = compile_style_result(result, mode, config['language'])
            if mode in ('style', 'both') and not result.get('style_prompt'):
                raise RuntimeError('화풍 프롬프트가 비어 있습니다. 다시 분석해 주세요.')
            return result

    async def run_update(self):
        async with self.operation_lock:
            self.update = {'status': 'running', 'message': 'Codex CLI 업데이트 중…'}
            await self.stop()
            try:
                p = await asyncio.create_subprocess_exec('npm', 'install', '--prefix', '/opt/codex', '@openai/codex@latest',
                    '--cache', '/tmp/npm-cache', '--ignore-scripts', '--no-audit', '--no-fund', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=codex_env())
                try:
                    out, _ = await asyncio.wait_for(p.communicate(), 300)
                except asyncio.TimeoutError:
                    p.kill()
                    await p.wait()
                    raise RuntimeError('업데이트 제한 시간을 초과했습니다.')
                if p.returncode:
                    raise RuntimeError('Codex 업데이트를 완료하지 못했습니다.')
                self.update = {'status': 'completed', 'message': await self.version()}
            except Exception as exc:
                self.update = {'status': 'failed', 'message': 'Codex 업데이트 연결을 확인해 주세요.'}
            finally:
                await self.start()


engine = CodexEngine()
