"""External chatbot output is bounded inert data, never code, markup or a remote file."""
import json
import math
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .style_contract import compile_style_result

MAX_RESPONSE = 1024 * 1024


class Comparison(BaseModel):
    model_config = ConfigDict(extra='ignore',strict=True)
    consistency: str = Field(pattern=r'^(consistent|mixed|insufficient)$')
    common_traits: list[str] = Field(default_factory=list,max_length=30)
    differences: list[str] = Field(default_factory=list,max_length=30)
    conflicts: list[str] = Field(default_factory=list,max_length=30)


class ExternalResult(BaseModel):
    model_config = ConfigDict(extra='ignore',strict=True)
    title: str = Field(default='가져온 프롬프트',max_length=200)
    style_prompt: str | None = Field(default=None,max_length=200_000)
    character_prompt: str | None = Field(default=None,max_length=200_000)
    style_execution: str | None = Field(default=None,pattern=r'^(raw_awkward|controlled_sparse|confident_graphic|painterly)$')
    raw_style_recipe: str | None = Field(default=None,max_length=100_000)
    warnings: list[str] = Field(default_factory=list,max_length=50)
    reference_summary: Comparison | None = None


def parse_external_response(raw, language='en'):
    try:
        size=len(raw.encode('utf-8')) if isinstance(raw,str) else MAX_RESPONSE+1
    except UnicodeError as exc:
        raise ValueError('UTF-8로 표현할 수 있는 응답을 붙여 넣어 주세요.') from exc
    if size>MAX_RESPONSE:
        raise ValueError('JSON 응답은 최대 1MB입니다.')
    text=raw.strip().lstrip('\ufeff')
    # Accept the chatbot's complete message when it contains one fenced JSON block.
    fences=re.findall(r'```(?:json)?\s*([\s\S]*?)```',text,re.IGNORECASE)
    if fences:
        if len(fences)!=1:
            raise ValueError('분석 응답 JSON 블록 하나만 붙여 넣어 주세요.')
        text=fences[0].strip()
    try:
        def invalid_constant(value):
            raise ValueError('Invalid JSON number')
        try:
            original=json.loads(text,parse_constant=invalid_constant)
        except ValueError:
            # Some chatbots add a short introduction/outro outside the JSON object.
            start=text.find('{')
            if start<0:
                raise
            original,end=json.JSONDecoder(parse_constant=invalid_constant).raw_decode(text[start:])
            if '{' in text[start+end:]:
                raise ValueError('Multiple JSON objects')
    except (ValueError,RecursionError) as exc:
        raise ValueError('올바른 JSON 응답을 붙여 넣어 주세요. json 코드 블록도 사용할 수 있습니다.') from exc
    if not isinstance(original,dict):
        raise ValueError('응답은 JSON 객체여야 합니다.')
    def check(value,depth=0):
        if depth>32 or isinstance(value,float) and not math.isfinite(value):
            raise ValueError('응답의 중첩이나 숫자 형식을 확인해 주세요.')
        if isinstance(value,dict):
            for key,child in value.items():
                check(key,depth+1);check(child,depth+1)
        elif isinstance(value,list):
            for child in value: check(child,depth+1)
        elif isinstance(value,str):
            if '\x00' in value:
                raise ValueError('응답에 저장할 수 없는 제어 문자가 있습니다.')
            try:value.encode('utf-8')
            except UnicodeError as exc:raise ValueError('UTF-8로 표현할 수 없는 문자가 있습니다.') from exc
    check(original)
    candidate=original.get('result',original)
    if not isinstance(candidate,dict) or 'instructions' in candidate or str(candidate.get('format','')).startswith('artstyle.extraction-request'):
        raise ValueError('요청문이 아닌 챗봇의 분석 결과 JSON을 붙여 넣어 주세요.')
    try:
        result=ExternalResult.model_validate(candidate).model_dump()
    except ValidationError as exc:
        # Pydantic's normal errors echo rejected input. Do not reflect private/malicious payloads.
        fields=', '.join(sorted({str(error['loc'][0]) for error in exc.errors()}))
        raise ValueError('응답 필드의 형식이나 길이를 확인해 주세요: '+fields) from exc
    for field in ('style_prompt','character_prompt','raw_style_recipe'):
        if isinstance(result[field],str):
            result[field]=result[field].strip() or None
    style=bool(result['style_prompt'] or result['style_execution']=='raw_awkward' and result['raw_style_recipe'])
    character=bool(result['character_prompt'])
    if not style and not character:
        raise ValueError('style_prompt 또는 character_prompt에 프롬프트가 있어야 합니다.')
    mode='both' if style and character else 'style' if style else 'character'
    result=compile_style_result(result,mode,language)
    return {'mode':mode,'result':result,'source_json':original}
