"""One real Codex vision test using a synthetic fixture, never a user image."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import os
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.engine import engine
from app.images import optimize_image


async def main():
    temporary = tempfile.TemporaryDirectory(prefix='artstyle-vision-')
    target = Path(os.getenv('ARTSTYLE_TEST_OUTPUT', temporary.name))
    target.mkdir(parents=True,exist_ok=True)
    im = Image.new('RGB', (768, 1024), '#faf3de')
    draw = ImageDraw.Draw(im)
    draw.ellipse((177, 90, 591, 565), fill='#9e3f2f', outline='#302f30', width=5)
    draw.rounded_rectangle((235, 650, 533, 1020), 24, fill='#294a6b', outline='#302f30', width=5)
    draw.polygon([(270, 510), (498, 510), (581, 800), (187, 800)], fill='#346b93', outline='#302f30', width=5)
    draw.rectangle((343, 440, 425, 570), fill='#e8b594', outline='#302f30', width=5)
    draw.ellipse((235, 153, 533, 485), fill='#edc4a5', outline='#302f30', width=5)
    draw.polygon([(234, 255), (257, 155), (471, 127), (535, 250), (454, 213), (402, 272), (351, 223), (311, 270)], fill='#9e3f2f', outline='#302f30', width=5)
    for x in (299, 433):
        draw.ellipse((x-20, 302, x+20, 346), fill='#f6f7ed', outline='#302f30', width=4)
        draw.ellipse((x-10, 310, x+10, 337), fill='#598b67', outline='#302f30', width=3)
    draw.line((367, 364, 363, 376, 375, 377), fill='#8e634e', width=3)
    draw.arc((350, 387, 394, 417), 10, 170, fill='#7e4b42', width=3)
    draw.ellipse((491, 207, 537, 253), fill='#d7ad50', outline='#302f30', width=3)
    draw.ellipse((505, 203, 541, 239), fill='#9e3f2f')
    draw.polygon([(260, 558), (345, 547), (384, 624), (423, 547), (508, 558), (455, 683), (313, 683)], fill='#e9e2c9', outline='#302f30', width=4)
    for y in (706, 750):
        draw.ellipse((378,y,390,y+12), fill='#d7ad50', outline='#302f30', width=2)
    raw = BytesIO();im.save(raw, 'PNG')
    data, _, _ = optimize_image(raw.getvalue())
    image_path = target/'synthetic-reference.webp'
    image_path.write_bytes(data)
    try:
        account = await engine.call('account/read', {'refreshToken': False})
        if not account.get('account'):
            raise RuntimeError('The private Codex runner is not authenticated; no API credential fallback is allowed.')
        models = await engine.models()
        model = next((m for m in models if m.get('isDefault')), models[0])
        config = {'model': model['model'], 'effort': 'high', 'language': 'en'}
        print('Running one real Codex image analysis:', model['model'], flush=True)
        result = await engine.analyze([image_path], 'both', config, '')
        (target/'real-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2), encoding='utf-8')
        assert result['style_prompt'] and result['character_prompt']
        print(json.dumps({'title':result['title'],'style_chars':len(result['style_prompt']),'character_chars':len(result['character_prompt']),'warnings':result['warnings']},ensure_ascii=False),flush=True)
    finally:
        await engine.stop()
        temporary.cleanup()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
