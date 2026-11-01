"""Style authority is application policy, not an optional model suggestion."""
STYLE_RULESET_VERSION = '2026-11-01.1'

EN = '''## Reference and style precedence
Any supplied reference image is CONTENT ONLY: identity, appearance, clothing, objects, pose and composition. Ignore the rendering style of every reference image completely. Apply ONLY this written style to stylized proportions, exaggeration, linework, color, shading, simplification, detail density, drawing skill and finish. Restyle reference geometry; never inherit or blend its realism, anatomy ratios, polish or technique. Preserve essential identity cues within this style's own mark/detail budget. Never beautify, refine or complete the drawing beyond the specified skill and finish ceiling. These rules govern HOW; references govern only WHAT.
'''

KO = '''## 참조 이미지와 화풍의 우선순위
참조 이미지는 인물 정체성·외형·의상·사물·포즈·구도 등 내용만을 위한 자료로 사용한다. 모든 참조 이미지의 화풍은 완전히 무시한다. 양식적 비율·만화적 과장·선·채색·명암·생략·묘사 밀도·그림 실력·마감은 오직 아래에 적힌 화풍만 적용한다. 참조 이미지의 형태와 비율을 이 화풍에 맞게 다시 구성하고, 사실성·해부학적 비율·세련됨·그림 기법을 물려받거나 섞지 않는다. 식별에 필요한 특징은 이 화풍의 제한된 형태와 선 안에서 유지한다. 명시된 실력과 완성도의 상한을 넘어 미형화·정교화·완성을 하지 않는다. 어떻게 그릴지는 이 명세가 정하며, 참조 이미지는 무엇을 그릴지만 정한다.
'''

RAW_EN = '''## Drawing skill and finish ceiling
Deliberately use LOW drawing skill. The result must look BADLY DRAWN and casually low-effort, as an untrained person would execute the observed medium. This is a construction and finish ceiling, not a request for low resolution. Do not let a skilled illustrator's cute simplification, polished amateur look, or clean anatomy replace it.'''

RAW_KO = '''## 그림 실력과 마감의 상한
의도적으로 그림을 못 그리는 사람이 관찰된 도구로 급하게 그린 듯, 서툴고 무성의한 조형을 유지한다. 낮은 해상도를 요구하는 것이 아니다. 능숙한 작가의 귀여운 단순화, 세련된 아마추어풍, 정돈된 인체로 교체하지 않는다.'''


def ensure_style_contract(prompt, language='en'):
    if not prompt:
        return prompt
    contract = KO if language == 'ko' else EN
    if prompt.lstrip().startswith(contract.strip()):
        return prompt
    if prompt.lstrip().startswith(('## Reference and style precedence\n', '## 참조 이미지와 화풍의 우선순위\n')):
        # Replace an older policy block instead of stacking policy versions.
        prompt = prompt.lstrip().partition('\n\n')[2]
    return contract.strip() + '\n\n' + prompt.strip()


def compile_style_result(result, mode, language='en'):
    if mode == 'character':
        result['style_prompt'] = None
        result['style_execution'] = None
        result['raw_style_recipe'] = None
        return result
    if result.get('style_execution') == 'raw_awkward':
        recipe = result.get('raw_style_recipe')
        if not isinstance(recipe, str) or not recipe.strip():
            raise ValueError('거친 화풍의 실행 규칙이 비어 있습니다. 다시 분석해 주세요.')
        lock = RAW_KO if language == 'ko' else RAW_EN
        result['style_prompt'] = lock + '\n\n' + recipe.strip()
    result['style_prompt'] = ensure_style_contract(result.get('style_prompt'), language)
    return result
