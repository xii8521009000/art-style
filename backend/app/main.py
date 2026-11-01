import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
from typing import Annotated
import secrets
import uuid

from fastapi import FastAPI, Request, Response, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb
from starlette.formparsers import MultiPartParser
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError

from . import db
from .engine import engine
from .external_request import build_multi_external_request
from .uploads import prepare_images, close_uploads, MAX_UPLOAD
from .library import parse_external_response
from .security import RequestGuard
from .style_contract import ensure_style_contract, STYLE_RULESET_VERSION

DATA = Path(os.getenv('DATA_DIR', '/data'))
COOKIE = 'artstyle_session'
SECURE = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
# Starlette normally spools raw uploads to disk after 1 MB. Keep accepted uploads
# in memory so only the optimized WebP ever reaches persistent storage.
MultiPartParser.spool_max_size = MAX_UPLOAD + 1024 * 1024


def cookie(response, token):
    response.set_cookie(COOKIE, token, max_age=60 * 60 * 24 * 400, httponly=True, secure=SECURE, samesite='strict', path='/')


async def session_token(request):
    token = request.cookies.get(COOKIE, '')
    if len(token) != 64:
        return None
    found = await asyncio.to_thread(db.query, 'SELECT token_hash FROM sessions WHERE token_hash=%s',
        (hashlib.sha256(token.encode()).hexdigest(),), one=True)
    return token if found else None


async def authenticated(request: Request, response: Response):
    token = getattr(request.state, 'auth_token', None) or await session_token(request)
    if not token:
        raise HTTPException(401, '로그인이 필요합니다.')
    cookie(response, token)
    return token


def settings():
    return db.query('SELECT value FROM settings WHERE id=1', one=True)['value']


def get_job(job_id):
    try:
        job_id = uuid.UUID(str(job_id))
    except ValueError:
        raise HTTPException(404, '기록을 찾을 수 없습니다.')
    row = db.query('SELECT j.*, i.filename, i.original_bytes, i.stored_bytes, i.width, i.height FROM jobs j JOIN images i ON i.id=j.image_id WHERE j.id=%s', (job_id,), one=True)
    if not row:
        raise HTTPException(404, '기록을 찾을 수 없습니다.')
    row['has_source_json'] = row.pop('source_json', None) is not None
    row['style_prompt'] = ensure_style_contract(row.get('style_prompt'), row['engine'].get('language', 'en'))
    row['images'] = [{key: value for key, value in image.items() if key != 'stored_name'} for image in job_images(job_id)]
    row['image_count'] = len(row['images'])
    row['total_original_bytes'] = sum(image['original_bytes'] for image in row['images'])
    row['total_stored_bytes'] = sum(image['stored_bytes'] for image in row['images'])
    return row


def job_images(job_id):
    return db.query('SELECT i.*,ji.position FROM job_images ji JOIN images i ON i.id=ji.image_id WHERE ji.job_id=%s ORDER BY ji.position', (job_id,))


async def validate_engine(config):
    status = await engine.call('account/read', {'refreshToken': False})
    if not status.get('account'):
        raise HTTPException(409, '설정에서 Codex에 먼저 로그인해 주세요.')
    models = await engine.models()
    if not models:
        raise HTTPException(409, '사용 가능한 이미지 분석 모델이 없습니다.')
    if not config.get('model'):
        m = next((m for m in models if m.get('isDefault')), models[0])
        config['model'] = m['model']
        supported = [x['reasoningEffort'] for x in m['supportedReasoningEfforts']]
        if config.get('effort') not in supported:
            config['effort'] = m['defaultReasoningEffort']
        db.query('UPDATE settings SET value=%s WHERE id=1', (Jsonb(config),))
    model = next((m for m in models if m['model'] == config['model']), None)
    if not model or config['effort'] not in [e['reasoningEffort'] for e in model['supportedReasoningEfforts']]:
        raise HTTPException(409, '설정에서 사용 가능한 모델과 추론 정도를 선택해 주세요.')
    return config


async def worker():
    while True:
        try:
            if engine.update['status'] == 'running':
                with suppress(Exception):
                    await engine.status()
                if engine.update['status'] == 'running':
                    await asyncio.sleep(2)
                    continue
            async with engine.operation_lock:
                row = db.query("UPDATE jobs SET status='running' WHERE id=(SELECT id FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *", one=True)
                if row:
                    images = job_images(row['id'])
                    try:
                        result = await engine.analyze([DATA / image['stored_name'] for image in images], row['mode'], row['engine'], row['focus'])
                        db.query("UPDATE jobs SET status='completed',title=%s,style_prompt=%s,character_prompt=%s,warnings=%s,reference_summary=%s,source_json=%s,engine=engine || %s,finished_at=now() WHERE id=%s",
                            (str(result.get('title') or row['title'])[:200], result.get('style_prompt'), result.get('character_prompt'), Jsonb(result['warnings']),
                             Jsonb(result.get('reference_summary')), Jsonb(result), Jsonb({'style_execution': result.get('style_execution')}), row['id']))
                    except Exception as exc:
                        db.query("UPDATE jobs SET status='failed',error=%s,finished_at=now() WHERE id=%s", ('분석을 완료하지 못했습니다. 설정에서 Codex 연결과 모델을 확인해 주세요.', row['id']))
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app):
    DATA.mkdir(parents=True, exist_ok=True)
    db.initialize()
    # Clean interrupted uploads that never acquired a database reference.
    names = {x['stored_name'] for x in db.query('SELECT stored_name FROM images')}
    for path in DATA.glob('*.webp'):
        if path.name not in names:
            path.unlink(missing_ok=True)
    task = asyncio.create_task(worker())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await engine.stop()


class BoundedRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def bounded(request):
            if request.method in ('POST','PUT','PATCH') and request.headers.get('content-type','').startswith('multipart/form-data'):
                await request.form(max_files=8, max_fields=8, max_part_size=1024*1024)
            return await original(request)
        return bounded


app = FastAPI(title='Art Style', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.router.route_class = BoundedRoute
app.add_middleware(RequestGuard, authorize=session_token)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse({'detail':'입력값의 형식과 길이를 확인해 주세요.'},status_code=422)


@app.get('/api/health')
def health():
    db.query('SELECT 1')
    return {'status': 'ok'}


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=300)


@app.post('/api/login')
async def login(body: Login, request: Request, response: Response):
    address = request.client.host if request.client else 'unknown'
    db.query("DELETE FROM login_attempts WHERE started_at < now() - interval '15 minutes'")
    attempt = db.query('INSERT INTO login_attempts VALUES(%s,1,now()) ON CONFLICT(address) DO UPDATE SET attempts=login_attempts.attempts+1 RETURNING attempts', (address,), one=True)
    if attempt['attempts'] > 10:
        raise HTTPException(429, '로그인 시도가 많습니다. 15분 후 다시 시도해 주세요.')
    configured = os.environ['APP_PASSWORD_HASH'].split(':')
    try:
        iterations, salt, expected = int(configured[0]), bytes.fromhex(configured[1]), configured[2]
        actual = await asyncio.to_thread(hashlib.pbkdf2_hmac, 'sha256', body.password.encode(), salt, iterations)
        valid = hmac.compare_digest(actual.hex(), expected) and hmac.compare_digest(body.username.encode(), os.getenv('APP_USERNAME', 'admin').encode())
    except (ValueError, IndexError):
        raise HTTPException(503, '서버 접속 암호 설정을 확인해 주세요.')
    if not valid:
        raise HTTPException(401, '아이디 또는 비밀번호를 확인해 주세요.')
    db.query('DELETE FROM login_attempts WHERE address=%s', (address,))
    token = secrets.token_urlsafe(48)
    db.query('INSERT INTO sessions(token_hash) VALUES(%s)', (hashlib.sha256(token.encode()).hexdigest(),))
    cookie(response, token)
    return {'username': body.username}


@app.get('/api/me')
def me(token=Depends(authenticated)):
    return {'username': os.getenv('APP_USERNAME', 'admin')}


@app.post('/api/logout')
def logout(response: Response, token=Depends(authenticated)):
    db.query('DELETE FROM sessions WHERE token_hash=%s', (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE, path='/')
    return {'ok': True}


@app.get('/api/settings')
async def read_settings(token=Depends(authenticated)):
    try:
        status = await engine.status()
        models = await engine.models()
        return {'settings': settings(), 'models': models, 'available':True, **status}
    except Exception as exc:
        return {'settings': settings(), 'models': [], 'account': None, 'available':False, 'message':'Codex 실행기를 켜면 자동 분석을 사용할 수 있습니다. JSON 방식은 연결 없이 사용할 수 있습니다.', 'update': engine.update}


class EngineSettings(BaseModel):
    model: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$')
    effort: str = Field(pattern=r'^(none|minimal|low|medium|high|xhigh|max|ultra)$')
    language: str = Field(pattern=r'^(en|ko)$')


@app.put('/api/settings')
async def save_settings(body: EngineSettings, token=Depends(authenticated)):
    config = body.model_dump()
    await validate_engine(config)
    db.query('UPDATE settings SET value=%s WHERE id=1', (Jsonb(config),))
    return config


@app.post('/api/engine/login')
async def engine_login(token=Depends(authenticated)):
    if engine.operation_lock.locked():
        raise HTTPException(409, '분석 또는 업데이트가 끝난 후 로그인해 주세요.')
    try:
        return await engine.start_login()
    except Exception as exc:
        raise HTTPException(502, 'Codex 연결을 시작하지 못했습니다. 실행기 상태를 확인해 주세요.')


@app.post('/api/engine/logout')
async def engine_logout(token=Depends(authenticated)):
    if engine.operation_lock.locked() or db.query("SELECT id FROM jobs WHERE status='queued' LIMIT 1"):
        raise HTTPException(409, '분석이 모두 끝난 후 로그아웃해 주세요.')
    await engine.call('account/logout')
    engine.login = None
    return {'ok': True}


@app.post('/api/engine/update')
async def engine_update(token=Depends(authenticated)):
    if engine.operation_lock.locked() or engine.update['status'] == 'running':
        raise HTTPException(409, '분석 또는 업데이트가 끝난 후 다시 시도해 주세요.')
    engine.update = {'status': 'running', 'message': '업데이트를 시작합니다…'}
    asyncio.create_task(engine.run_update())
    return engine.update


def store_job(prepared, mode, focus, config, result=None, source_json=None):
    destinations = []
    job_id, image_ids = uuid.uuid4(), [uuid.uuid4() for _ in prepared]
    title = (result or {}).get('title') or Path(prepared[0]['filename']).stem
    if result is None and len(prepared)>1:
        title = f'{title} 외 {len(prepared)-1}장'
    config = {**config,'reference_count':len(prepared)}
    try:
        with db.connect() as conn:
            for item, image_id in zip(prepared, image_ids):
                destination = DATA / f'{image_id}.webp'
                destinations.append(destination)
                destination.write_bytes(item['data'])
                conn.execute('INSERT INTO images(id,filename,stored_name,original_bytes,stored_bytes,width,height) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    (image_id,item['filename'],destination.name,item['original_bytes'],item['stored_bytes'],item['width'],item['height']))
            conn.execute("INSERT INTO jobs(id,image_id,title,mode,focus,engine,status,style_prompt,character_prompt,warnings,reference_summary,source_json,finished_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN now() ELSE NULL END)",
                (job_id,image_ids[0],title[:200],mode,focus,Jsonb(config),'completed' if result else 'queued',
                 (result or {}).get('style_prompt'),(result or {}).get('character_prompt'),Jsonb((result or {}).get('warnings',[])),
                 Jsonb((result or {}).get('reference_summary')),Jsonb(source_json),bool(result)))
            for position,image_id in enumerate(image_ids):
                conn.execute('INSERT INTO job_images(job_id,image_id,position) VALUES(%s,%s,%s)',(job_id,image_id,position))
    except Exception:
        for destination in destinations:
            destination.unlink(missing_ok=True)
        raise
    return get_job(job_id)


@app.post('/api/jobs', status_code=201)
async def upload(file: Annotated[UploadFile | None, File()] = None, mode: str = Form('both'),
                 focus: str = Form(''), files: Annotated[list[UploadFile] | None, File()] = None,
                 token=Depends(authenticated)):
    sources = ([file] if file else []) + (files or [])
    try:
        if mode not in ('both','style','character') or len(focus)>500:
            raise HTTPException(400,'분석 옵션을 확인해 주세요.')
        config = {**await validate_engine(settings()),'style_ruleset':STYLE_RULESET_VERSION,'source':'codex'}
        if len(db.query("SELECT id FROM jobs WHERE status IN ('queued','running')"))>=20:
            raise HTTPException(429,'대기 중인 분석이 많습니다. 잠시 후 다시 시도해 주세요.')
        return store_job(await prepare_images(sources),mode,focus,config)
    finally:
        await close_uploads(sources)


class PreviewResponse(BaseModel):
    response: str = Field(max_length=1024*1024)
    language: str = Field(default='en',pattern=r'^(en|ko)$')


@app.post('/api/library/preview')
def preview_import(body: PreviewResponse, token=Depends(authenticated)):
    try:
        parsed=parse_external_response(body.response,body.language)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {'mode':parsed['mode'],**parsed['result']}


@app.post('/api/library/import', status_code=201)
async def import_response(response: str = Form(...), language: str = Form('en'), title: str = Form(''),
                          files: Annotated[list[UploadFile] | None, File()] = None, token=Depends(authenticated)):
    sources=files or []
    try:
        if language not in ('en','ko') or len(title)>200:
            raise HTTPException(400,'저장 옵션을 확인해 주세요.')
        try:
            parsed=parse_external_response(response,language)
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        if title.strip():
            parsed['result']['title']=title.strip()
        prepared=await prepare_images(sources)
        config={'source':'external-json','model':'외부 JSON','effort':'none','language':language,
                'style_ruleset':STYLE_RULESET_VERSION,'style_execution':parsed['result'].get('style_execution')}
        return store_job(prepared,parsed['mode'],'',config,parsed['result'],parsed['source_json'])
    finally:
        await close_uploads(sources)


@app.post('/api/export-request')
async def export_upload(file: Annotated[UploadFile | None, File()] = None, mode: str = Form('both'),
                        language: str = Form('en'), focus: str = Form(''),
                        files: Annotated[list[UploadFile] | None, File()] = None, token=Depends(authenticated)):
    """Prepare in memory without Codex, queue entries or saved files."""
    sources = ([file] if file else []) + (files or [])
    try:
        if mode not in ('both', 'style', 'character') or language not in ('en', 'ko') or len(focus) > 500:
            raise HTTPException(400, '분석 옵션을 확인해 주세요.')
        prepared = await prepare_images(sources)
        return build_multi_external_request(prepared, mode, language, focus)
    finally:
        await close_uploads(sources)


class ExportOptions(BaseModel):
    mode: str = Field(pattern=r'^(both|style|character)$')
    language: str = Field(pattern=r'^(en|ko)$')
    focus: str = Field(default='', max_length=500)


@app.post('/api/jobs/{job_id}/export-request')
def export_saved(job_id: str, body: ExportOptions, token=Depends(authenticated)):
    row = get_job(job_id)
    images = [{**image, 'data': (DATA / image['stored_name']).read_bytes()} for image in job_images(row['id'])]
    return build_multi_external_request(images, body.mode, body.language, body.focus)


@app.get('/api/jobs')
def history(search: str = '', offset: int = 0, token=Depends(authenticated)):
    search, offset = search[:200], max(offset, 0)
    pattern = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    where = ' WHERE j.title ILIKE %s OR EXISTS(SELECT 1 FROM job_images ji JOIN images search_image ON search_image.id=ji.image_id WHERE ji.job_id=j.id AND search_image.filename ILIKE %s)'
    rows = db.query("SELECT j.id,j.title,j.mode,j.status,j.error,j.created_at,j.finished_at,i.filename,i.stored_bytes,i.width,i.height,j.engine->>'source' AS source,(SELECT count(*) FROM job_images ji WHERE ji.job_id=j.id) AS image_count FROM jobs j JOIN images i ON i.id=j.image_id" + where + ' ORDER BY j.created_at DESC LIMIT 24 OFFSET %s', (pattern, pattern, offset))
    count = db.query('SELECT count(*) AS count FROM jobs j JOIN images i ON i.id=j.image_id' + where, (pattern, pattern), one=True)['count']
    return {'items': rows, 'total': count}


@app.get('/api/jobs/{job_id}')
def detail(job_id: str, token=Depends(authenticated)):
    return get_job(job_id)


@app.get('/api/experiments/{experiment}/{asset:path}')
def experiment_asset(experiment: str, asset: str, token=Depends(authenticated)):
    """Read-only private regression artifacts; never serve outside their own directory."""
    if os.getenv('ENABLE_EXPERIMENTS')!='true':
        raise HTTPException(404, '검증 자료를 찾을 수 없습니다.')
    root = (DATA / 'experiments').resolve()
    candidate = (root / experiment / asset).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise HTTPException(404, '검증 자료를 찾을 수 없습니다.')
    if candidate.suffix.lower() not in {'.html', '.png', '.webp', '.jpg', '.md', '.json', '.txt'}:
        raise HTTPException(404, '검증 자료를 찾을 수 없습니다.')
    return FileResponse(candidate, headers={'Cache-Control': 'private, no-store'})


@app.get('/api/jobs/{job_id}/image')
def image(job_id: str, index: int = 0, download: bool = False, token=Depends(authenticated)):
    row = get_job(job_id)
    images = job_images(row['id'])
    if not 0 <= index < len(images):
        raise HTTPException(404, '이미지를 찾을 수 없습니다.')
    stored = images[index]
    return FileResponse(DATA / stored['stored_name'], media_type='image/webp', filename=f'reference-{index+1:02}.webp' if download else None)


@app.post('/api/jobs/{job_id}/retry', status_code=201)
async def retry(job_id: str, token=Depends(authenticated)):
    row = get_job(job_id)
    if row['status'] in ('queued', 'running'):
        raise HTTPException(409, '이미 분석 중입니다.')
    if len(db.query("SELECT id FROM jobs WHERE status IN ('queued','running')")) >= 20:
        raise HTTPException(429, '대기 중인 분석이 많습니다.')
    config = {**await validate_engine(settings()), 'style_ruleset': STYLE_RULESET_VERSION, 'reference_count': row['image_count']}
    new_id = uuid.uuid4()
    with db.connect() as conn:
        conn.execute('INSERT INTO jobs(id,image_id,title,mode,focus,engine) VALUES(%s,%s,%s,%s,%s,%s)',
            (new_id, row['image_id'], row['title'], row['mode'], row['focus'], Jsonb(config)))
        conn.execute('INSERT INTO job_images(job_id,image_id,position) SELECT %s,image_id,position FROM job_images WHERE job_id=%s', (new_id,row['id']))
    return get_job(new_id)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@app.patch('/api/jobs/{job_id}')
def rename(job_id: str, body: Rename, token=Depends(authenticated)):
    row = get_job(job_id)
    db.query('UPDATE jobs SET title=%s WHERE id=%s', (body.title, row['id']))
    return get_job(job_id)


@app.delete('/api/jobs/{job_id}')
def delete(job_id: str, token=Depends(authenticated)):
    row = get_job(job_id)
    removed = []
    with db.connect() as conn:
        locked = conn.execute('SELECT status FROM jobs WHERE id=%s FOR UPDATE', (row['id'],)).fetchone()
        if locked and locked['status'] in ('queued', 'running'):
            raise HTTPException(409, '분석이 끝난 후 삭제할 수 있습니다.')
        conn.execute('DELETE FROM jobs WHERE id=%s', (row['id'],))
        for image in row['images']:
            orphan = conn.execute('DELETE FROM images WHERE id=%s AND NOT EXISTS(SELECT 1 FROM job_images WHERE image_id=%s) AND NOT EXISTS(SELECT 1 FROM jobs WHERE image_id=%s) RETURNING stored_name', (image['id'],image['id'],image['id'])).fetchone()
            if orphan:
                removed.append(orphan['stored_name'])
    for name in removed:
        (DATA / name).unlink(missing_ok=True)
    return {'ok': True}


@app.get('/api/jobs/{job_id}/response.json')
def download_response(job_id: str, token=Depends(authenticated)):
    row=get_job(job_id)
    source=db.query('SELECT source_json FROM jobs WHERE id=%s',(row['id'],),one=True)['source_json']
    if source is None:
        source={key:row.get(key) for key in ('title','style_prompt','character_prompt','warnings','reference_summary')}
        # Legacy rows contain the compiled prompt but no separate raw recipe. Preserve that
        # complete prompt on re-import instead of declaring a recipe that was never stored.
        source.update({'style_execution':None,'raw_style_recipe':None})
    return JSONResponse(source,headers={'Content-Disposition':'attachment; filename="artstyle-response.json"'})
