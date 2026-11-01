"""Bounded, in-memory preparation shared by analysis and portable requests."""
import asyncio
import hashlib
import re
from pathlib import Path

from fastapi import HTTPException
from .images import optimize_image

MAX_IMAGES = 8
MAX_UPLOAD = 30 * 1024 * 1024
DECODER = asyncio.Semaphore(1)


async def prepare_images(files):
    if not 1 <= len(files) <= MAX_IMAGES:
        raise HTTPException(400, '이미지를 1~8장 선택해 주세요.')
    prepared, total, seen = [], 0, set()
    for file in files:
        data = await file.read(MAX_UPLOAD - total + 1)
        total += len(data)
        if total > MAX_UPLOAD:
            raise HTTPException(413, '전체 이미지의 합계는 최대 30MB입니다.')
        try:
            async with DECODER:
                compressed, width, height = await asyncio.to_thread(optimize_image, data)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        digest = hashlib.sha256(compressed).digest()
        if digest in seen:
            raise HTTPException(400, '동일한 이미지가 중복되었습니다. 중복 이미지를 제거해 주세요.')
        seen.add(digest)
        prepared.append({'data': compressed, 'width': width, 'height': height,
                         'original_bytes': len(data), 'stored_bytes': len(compressed),
                         'filename': re.sub(r'[\x00-\x1f\x7f]', '_', Path((file.filename or 'image').replace('\\', '/')).name)[:200]})
    return prepared


async def close_uploads(files):
    for file in files:
        await file.close()
