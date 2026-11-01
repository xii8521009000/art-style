"""Run inside the backend container. Uses a disposable DB, never production data.

The Codex response is stubbed here; real vision is tested separately by tools/test_analysis.py.
"""
import asyncio
import base64
from contextlib import suppress
from io import BytesIO
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit
import uuid

import psycopg
from psycopg import sql
from PIL import Image
from starlette.datastructures import UploadFile


async def verify():
    original_url = os.environ['DATABASE_URL']
    name = 'artstyle_qa_' + uuid.uuid4().hex
    parts = urlsplit(original_url)
    test_url = urlunsplit(parts._replace(path='/' + name))
    admin = psycopg.connect(os.getenv('ADMIN_DATABASE_URL',original_url), autocommit=True)
    with psycopg.connect(original_url) as owner:
        username=owner.execute('SELECT current_user').fetchone()[0]
    admin.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name),sql.Identifier(username)))
    task = None
    try:
        with tempfile.TemporaryDirectory(prefix='artstyle-storage-qa-') as temporary:
            os.environ['DATABASE_URL'] = test_url
            os.environ['DATA_DIR'] = temporary
            from app import db, main
            db.initialize()

            async def validate(config):
                return {'model': 'test-model', 'effort': 'high', 'language': 'en'}

            async def inference(*args):
                paths = args[0]
                assert isinstance(paths, list) and paths
                return {'title': '저장 검증', 'style_prompt': 'Portable rendering specification.',
                        'character_prompt': 'Portable identity specification.', 'warnings': ['합성 테스트'],
                        'reference_summary': {'consistency':'mixed','common_traits':['공통 선'],'differences':['2번의 차이'],'conflicts':[]} if len(paths)>1 else None}

            main.validate_engine = validate
            main.engine.analyze = inference
            image = Image.new('RGB', (180, 120), '#d5a675')
            exif = Image.Exif();exif[270] = 'PRIVATE TEST METADATA'
            raw = BytesIO();image.save(raw, 'JPEG', exif=exif)
            # Export must work without validating or calling Codex, and persist nothing.
            saved_validate, saved_analyze = main.validate_engine, main.engine.analyze
            async def no_codex(*args):
                raise AssertionError('Export attempted to use Codex')
            main.validate_engine = no_codex
            main.engine.analyze = no_codex
            source = UploadFile(BytesIO(raw.getvalue()), filename='original.jpg')
            exported = await main.export_upload(source, 'both', 'ko', '왼쪽 인물', token='qa')
            assert source.file.closed
            optimized = base64.b64decode(exported['input']['image']['data_url'].split(',', 1)[1])
            assert not Image.open(BytesIO(optimized)).getexif()
            assert exported['input']['character_focus'] == '왼쪽 인물'
            assert not list(Path(temporary).iterdir())
            assert db.query('SELECT count(*) AS n FROM images',one=True)['n'] == 0
            assert main.history(search='',offset=0,token='qa')['total'] == 0
            main.validate_engine, main.engine.analyze = saved_validate, saved_analyze
            first = await main.upload(file=UploadFile(BytesIO(raw.getvalue()), filename='original.jpg'),mode='both',focus='',token='qa')
            # Simulate a legacy row with no relation table entry; startup backfills once.
            db.query('DELETE FROM job_images WHERE job_id=%s',(first['id'],))
            db.initialize(); db.initialize()
            assert main.get_job(first['id'])['image_count'] == 1
            files = list(Path(temporary).iterdir())
            assert len(files) == 1 and files[0].suffix == '.webp'
            assert not Image.open(files[0]).getexif()
            assert first['original_bytes'] == len(raw.getvalue())
            task = asyncio.create_task(main.worker())

            async def completed(job_id):
                for _ in range(100):
                    row = main.get_job(job_id)
                    if row['status'] == 'completed':
                        return row
                    assert row['status'] != 'failed', row.get('error')
                    await asyncio.sleep(.1)
                raise AssertionError('Queue did not complete')

            row = await completed(first['id'])
            assert row['style_prompt'] and row['character_prompt']
            assert main.history(search='저장',offset=0,token='qa')['total'] == 1
            assert Path(main.image(str(row['id']),token='qa').path).exists()
            main.validate_engine, main.engine.analyze = no_codex, no_codex
            saved_export = main.export_saved(str(row['id']), main.ExportOptions(mode='style',language='en'),token='qa')
            assert base64.b64decode(saved_export['input']['image']['data_url'].split(',',1)[1]) == files[0].read_bytes()
            assert main.history(search='',offset=0,token='qa')['total'] == 1
            assert len(list(Path(temporary).iterdir())) == 1
            main.validate_engine, main.engine.analyze = saved_validate, saved_analyze
            main.rename(str(row['id']),main.Rename(title='수정한 제목'),token='qa')
            assert main.history(search='수정한',offset=0,token='qa')['total'] == 1
            second = await main.retry(str(row['id']),token='qa')
            await completed(second['id'])
            assert second['image_id'] == row['image_id']
            main.delete(str(row['id']),token='qa')
            assert files[0].exists(), 'Shared image was deleted prematurely'
            assert main.history(search='',offset=0,token='qa')['total'] == 1
            main.delete(str(second['id']),token='qa')
            assert not list(Path(temporary).iterdir())
            assert main.history(search='',offset=0,token='qa')['total'] == 0
            # Exercise one grouped record with ordered sources and a shared retry.
            second_raw = BytesIO(); Image.new('RGB',(90,160),'#5980a0').save(second_raw,'JPEG')
            def sources():
                return [UploadFile(BytesIO(raw.getvalue()),filename='anchor.jpg'),
                        UploadFile(BytesIO(second_raw.getvalue()),filename='secondary-view.jpg')]
            grouped = await main.upload(files=sources(),mode='style',focus='',token='qa')
            grouped = await completed(grouped['id'])
            assert grouped['image_count'] == 2 and grouped['engine']['reference_count'] == 2
            assert [item['filename'] for item in grouped['images']] == ['anchor.jpg','secondary-view.jpg']
            assert grouped['reference_summary']['consistency'] == 'mixed'
            assert len(list(Path(temporary).glob('*.webp'))) == 2
            assert main.history(search='secondary-view',offset=0,token='qa')['total'] == 1
            second_path = Path(main.image(str(grouped['id']),index=1,token='qa').path)
            assert Image.open(second_path).size == (90,160)
            main.validate_engine, main.engine.analyze = no_codex, no_codex
            portable = main.export_saved(str(grouped['id']),main.ExportOptions(mode='both',language='ko'),token='qa')
            assert len(portable['input']['images']) == 2
            assert base64.b64decode(portable['input']['images'][1]['data_url'].split(',',1)[1]) == second_path.read_bytes()
            transient = await main.export_upload(files=sources(),mode='both',language='en',focus='',token='qa')
            assert len(transient['input']['images']) == 2 and len(list(Path(temporary).glob('*.webp'))) == 2
            main.validate_engine, main.engine.analyze = saved_validate, saved_analyze
            copied = await main.retry(str(grouped['id']),token='qa')
            await completed(copied['id'])
            db.initialize()
            assert [item['id'] for item in main.get_job(copied['id'])['images']] == [item['id'] for item in grouped['images']]
            main.delete(str(grouped['id']),token='qa')
            assert len(list(Path(temporary).glob('*.webp'))) == 2
            main.delete(str(copied['id']),token='qa')
            assert not list(Path(temporary).iterdir())
            # A later bad file/duplicate must leave no partial image or job behind.
            from fastapi import HTTPException
            for bad_sources in [sources()+[UploadFile(BytesIO(b'bad'),filename='bad.jpg')],
                                [UploadFile(BytesIO(raw.getvalue()),filename='one.jpg'),UploadFile(BytesIO(raw.getvalue()),filename='duplicate.jpg')],
                                sources()*5]:
                try:
                    await main.upload(files=bad_sources,mode='style',focus='',token='qa')
                except HTTPException as exc:
                    assert exc.status_code == 400
                else:
                    raise AssertionError('Invalid grouped upload was accepted')
                assert all(item.file.closed for item in bad_sources)
                assert not list(Path(temporary).iterdir())
                assert main.history(search='',offset=0,token='qa')['total'] == 0
            from app import uploads
            limit = uploads.MAX_UPLOAD
            uploads.MAX_UPLOAD = len(raw.getvalue()) + len(second_raw.getvalue()) - 1
            try:
                await main.export_upload(files=sources(),mode='both',language='en',focus='',token='qa')
            except HTTPException as exc:
                assert exc.status_code == 413
            else:
                raise AssertionError('Combined byte budget was not enforced')
            finally:
                uploads.MAX_UPLOAD = limit
            # Import is a completed library entry, with the original JSON preserved, no CLI.
            import json
            original={'title':'오프라인 기록','style_prompt':'Fine flat contours.','character_prompt':None,
                      'warnings':['외부 응답'],'extra_metadata':{'url':'https://invalid.example/do-not-fetch'}}
            main.validate_engine,main.engine.analyze=no_codex,no_codex
            imported=await main.import_response(response='결과입니다.\n```json\n'+json.dumps(original)+'\n```',
                language='ko',title='가져온 두 장',files=sources(),token='qa')
            assert imported['status']=='completed' and imported['image_count']==2
            assert imported['engine']['source']=='external-json' and imported['has_source_json']
            assert '참조 이미지와 화풍' in imported['style_prompt']
            assert json.loads(main.download_response(str(imported['id']),token='qa').body)==original
            assert main.download_response(str(imported['id']),token='qa').headers['content-disposition']=='attachment; filename="artstyle-response.json"'
            assert not db.query("SELECT id FROM jobs WHERE status IN ('queued','running')")
            assert 'filename=' in main.image(str(imported['id']),index=1,download=True,token='qa').headers['content-disposition']
            main.delete(str(imported['id']),token='qa')
            assert not list(Path(temporary).iterdir())
            main.validate_engine,main.engine.analyze=saved_validate,saved_analyze
            # Test the actual resolver with existing files, independent of proxy normalization.
            from fastapi import HTTPException
            os.environ['ENABLE_EXPERIMENTS']='true'
            outside = Path(temporary) / 'outside.txt'
            outside.write_text('must not escape the experiment root',encoding='utf-8')
            inside = Path(temporary) / 'experiments' / 'qa' / 'inside.txt'
            inside.parent.mkdir(parents=True)
            inside.write_text('allowed artifact',encoding='utf-8')
            assert Path(main.experiment_asset('qa','inside.txt',token='qa').path) == inside
            try:
                main.experiment_asset('..','outside.txt',token='qa')
            except HTTPException as exc:
                assert exc.status_code == 404
            else:
                raise AssertionError('Experiment traversal escaped its root')
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            task = None
            print('PASS: offline JSON/image import and original JSON download without CLI, legacy migration, ordered multi-image storage/queue/export/search/retry/shared deletion, atomic rejection, byte limit, metadata privacy and path confinement')
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        os.environ['DATABASE_URL'] = original_url
        assert name.startswith('artstyle_qa_') and len(name) == len('artstyle_qa_') + 32
        admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        admin.close()


if __name__ == '__main__':
    asyncio.run(verify())
