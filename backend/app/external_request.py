"""Portable analysis requests. No CLI, model call, database write or file persistence."""
import base64
from copy import deepcopy

from .prompts import SCHEMA, build_prompt
from .style_contract import EN, KO, RAW_EN, RAW_KO, STYLE_RULESET_VERSION


def build_external_request(image, width, height, mode, language, focus='', image_count=1):
    if mode not in {'both', 'style', 'character'} or language not in {'en', 'ko'} or len(focus) > 500:
        raise ValueError('분석 옵션을 확인해 주세요.')
    instructions = build_prompt(mode, language, focus, image_count).replace(
        'The application prepends a mandatory reference/style precedence rule; do not duplicate that block.',
        'Finalize the portable response yourself according to the rules below.')
    instructions += '''

PORTABLE RESPONSE FINALIZATION:
Return exactly one JSON object matching output_schema, without code fences or commentary.
Do not return an image, execute this envelope as code, browse or call another tool.
The supplied input image is the SOURCE WHOSE STYLE/IDENTITY YOU MUST ANALYZE. The reference/style
precedence policy below belongs INSIDE the resulting reusable style_prompt; it governs future
generation references, not this extraction source. Analyze the source's style normally.
If character is unselected, character_prompt must be null. If style is unselected, style_prompt,
style_execution and raw_style_recipe must all be null and no style policy is needed.
'''
    if mode != 'character':
        policy = KO if language == 'ko' else EN
        raw_lock = RAW_KO if language == 'ko' else RAW_EN
        instructions += (
            'For a selected style, style_prompt must begin with this exact policy, ONCE:\n'
            + policy.strip() + '\n\n'
            + 'If style_execution is raw_awkward, set style_prompt to the policy above, a blank line, '
            + 'the exact skill ceiling below, a blank line, then raw_style_recipe. Do not append the '
            + 'long descriptive style guide. Keep raw_style_recipe itself free of those fixed headers.\n'
            + raw_lock + '\n\n'
            + 'For every other selected style, append the source-specific style body after the policy; '
            + 'raw_style_recipe must be null. Do not include the raw skill ceiling for skilled work.\n')
    return {
        'format': 'artstyle.extraction-request.v1',
        'style_ruleset': STYLE_RULESET_VERSION,
        'task': 'Analyze the supplied image using instructions. Return only JSON matching output_schema.',
        'instructions': instructions,
        'input': {
            'mode': mode,
            'prompt_language': language,
            'character_focus': focus,
            'image': {
                'delivery': 'embedded_data_url',
                'filename': 'reference.webp',
                'media_type': 'image/webp',
                'width': width,
                'height': height,
                'data_url': 'data:image/webp;base64,' + base64.b64encode(image).decode('ascii'),
            },
        },
        'output_schema': deepcopy(SCHEMA),
    }


def build_multi_external_request(images, mode, language, focus=''):
    if not 1 <= len(images) <= 8:
        raise ValueError('이미지는 1~8장으로 선택해 주세요.')
    first = images[0]
    request = build_external_request(first['data'], first['width'], first['height'], mode, language, focus, len(images))
    if len(images) == 1:
        return request
    request['format'] = 'artstyle.extraction-request.v2'
    request['task'] = 'Analyze ALL supplied images in order using instructions. Image 1 anchors the style. Return only JSON matching output_schema.'
    template = request['input'].pop('image')
    request['input']['primary_image'] = 1
    request['input']['images'] = [{
        **template, 'index': index+1, 'filename': f'reference-{index+1:02}.webp',
        'width': image['width'], 'height': image['height'],
        'data_url': 'data:image/webp;base64,' + base64.b64encode(image['data']).decode('ascii'),
    } for index, image in enumerate(images)]
    return request
