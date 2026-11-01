import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.library import parse_external_response


class LibraryTests(unittest.TestCase):
    def test_chatbot_full_message_fences_and_minimal_output(self):
        original={'title':'가져온 기록','style_prompt':'Thin lines.','character_prompt':None,'extra':{'data':'preserved'}}
        parsed=parse_external_response('아래 결과입니다.\n```json\n'+json.dumps(original)+'\n```\n완료했습니다.','ko')
        self.assertEqual(parsed['source_json'],original)
        self.assertEqual(parsed['mode'],'style')
        self.assertIn('참조 이미지와 화풍',parsed['result']['style_prompt'])
        self.assertNotIn('extra',parsed['result'])
        self.assertEqual(parse_external_response('Result: '+json.dumps(original)+'\nDone.')['mode'],'style')

    def test_character_mode_and_wrapped_response_preserve_original(self):
        raw={'result':{'character_prompt':'<img src=x onerror=alert(1)> Short hair.'}}
        parsed=parse_external_response(json.dumps(raw))
        self.assertEqual(parsed['mode'],'character')
        self.assertIsNone(parsed['result']['style_prompt'])
        self.assertEqual(parsed['source_json'],raw)
        self.assertIn('<img',parsed['result']['character_prompt'])  # inert text, never sanitized into executable HTML

    def test_raw_style_compilation_and_round_trip(self):
        raw={'style_execution':'raw_awkward','style_prompt':'Discard longer guide.','raw_style_recipe':'Tiny crooked features.'}
        result=parse_external_response(json.dumps(raw))['result']
        self.assertIn('BADLY DRAWN',result['style_prompt'])
        self.assertNotIn('Discard longer guide',result['style_prompt'])
        again=parse_external_response(json.dumps(result))['result']
        self.assertEqual(again['style_prompt'],result['style_prompt'])

    def test_request_object_empty_wrong_types_and_large_or_nonfinite_data_fail(self):
        invalid=[{},[],{'instructions':'request','style_prompt':'Do not import'},
                 {'style_prompt':{'bad':'object'}},{'warnings':[1],'style_prompt':'a'},
                 {'style_prompt':'a','reference_summary':{'consistency':'unknown'}},
                 {'style_execution':'raw_awkward','style_prompt':'missing recipe'}]
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_external_response(json.dumps(value))
        for text in ['x'*(1024*1024+1),'```json\n{}\n```\n```json\n{}\n```',
                     '{"style_prompt":"a","x":NaN}','{"style_prompt":"a","x":1e10000}',
                     '{"style_prompt":"a","x":"\\u0000"}','{"style_prompt":"a","x":"\\ud800"}',
                     '{"style_prompt":"a","x":'+'['*40+'0'+']'*40+'}']:
            with self.assertRaises(ValueError):parse_external_response(text)
