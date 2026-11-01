"""Private Codex sidecar: no database, library volume, shell endpoint or arbitrary RPC."""
import asyncio
import base64
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
from io import BytesIO
import tempfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .codex_runtime import engine
from PIL import Image


@asynccontextmanager
async def lifespan(app):
    if len(os.getenv('ENGINE_TOKEN', '')) < 32:
        raise RuntimeError('ENGINE_TOKEN must be an independent random secret of at least 32 characters')
    yield
    await engine.stop()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def guard(request: Request, call_next):
    if request.url.path != '/health':
        expected = 'Bearer ' + os.getenv('ENGINE_TOKEN', '')
        if len(expected) < 39 or not hmac.compare_digest(request.headers.get('authorization', ''), expected):
            return JSONResponse({'detail':'Unauthorized'},status_code=401)
    # Runner has no host-published port; still bound its own authenticated request stream.
    length = request.headers.get('content-length', '0')
    if not length.isdigit() or int(length) > 43 * 1024 * 1024:
        return JSONResponse({'detail':'Request too large'},status_code=413)
    if request.method == 'POST':
        total, blocks = 0, []
        async for block in request.stream():
            total += len(block)
            if total > 43 * 1024 * 1024:
                return JSONResponse({'detail':'Request too large'},status_code=413)
            blocks.append(block)
        request._body = b''.join(blocks)
    try:
        return await call_next(request)
    except Exception:
        return JSONResponse({'detail':'Codex service unavailable'},status_code=503)


@app.get('/health')
def health():
    return {'status':'ok'}


def public_login(login):
    if not login:
        return None
    result = {key:login[key] for key in ('status','userCode','verificationUrl') if key in login}
    if result.get('verificationUrl') not in {'https://auth.openai.com/codex/device'}:
        result.pop('verificationUrl',None)
    return result


@app.get('/status')
async def status():
    result = await engine.status()
    account = result.get('account')
    return {**result, 'login':public_login(result.get('login')),
            'account':{key:account[key] for key in ('type','email','planType') if key in account} if account else None}


@app.get('/models')
async def models():
    return await engine.models()


@app.post('/login')
async def login():
    if engine.operation_lock.locked():
        raise HTTPException(409,'Busy')
    return public_login(await engine.start_login())


@app.post('/logout')
async def logout():
    if engine.operation_lock.locked():
        raise HTTPException(409,'Busy')
    await engine.call('account/logout')
    engine.login = None
    return {'ok':True}


@app.post('/update')
async def update():
    if engine.operation_lock.locked() or engine.update['status']=='running':
        raise HTTPException(409,'Busy')
    engine.update={'status':'running','message':'Codex CLI 업데이트 중…'}
    asyncio.create_task(engine.run_update())
    return engine.update


class Analysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    images: list[str] = Field(min_length=1,max_length=8)
    mode: str = Field(pattern=r'^(both|style|character)$')
    model: str = Field(max_length=100,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')
    effort: str = Field(pattern=r'^(none|minimal|low|medium|high|xhigh|max|ultra)$')
    language: str = Field(pattern=r'^(en|ko)$')
    focus: str = Field(default='',max_length=500)


@app.post('/analyze')
async def analyze(body: Analysis):
    if engine.operation_lock.locked():
        raise HTTPException(409,'Busy')
    async with engine.operation_lock:
        with tempfile.TemporaryDirectory(prefix='artstyle-incoming-') as directory:
            paths, total = [], 0
            for index, encoded in enumerate(body.images):
                try:
                    decoded=base64.b64decode(encoded,validate=True)
                    total+=len(decoded)
                    if total>30*1024*1024:
                        raise ValueError('too large')
                    # Only actual raster bytes cross the boundary; never accept paths or URLs.
                    with Image.open(BytesIO(decoded)) as raster:
                        if raster.format!='WEBP' or max(raster.size)>3072:
                            raise ValueError('not an optimized WebP')
                        raster.verify()
                except (ValueError,TypeError,OSError,Image.DecompressionBombError):
                    raise HTTPException(400,'Invalid raster data')
                path=Path(directory)/f'{index:02}.webp'
                path.write_bytes(decoded)
                paths.append(path)
            config={'model':body.model,'effort':body.effort,'language':body.language}
            return await engine.analyze(paths,body.mode,config,body.focus)
