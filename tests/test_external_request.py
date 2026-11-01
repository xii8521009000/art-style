import base64
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.external_request import build_external_request, build_multi_external_request
from app.prompts import build_prompt, SCHEMA
from app.style_contract import EN, KO, RAW_EN, RAW_KO, STYLE_RULESET_VERSION


class ExternalRequestTests(unittest.TestCase):
    def test_embedded_image_round_trips_without_url_or_credentials(self):
        image = b'RIFF\x00\x01WEBP'
        request = json.loads(json.dumps(build_external_request(image, 200, 100, 'both', 'en')))
        self.assertEqual(base64.b64decode(request['input']['image']['data_url'].split(',', 1)[1]), image)
        self.assertEqual(request['input']['image']['filename'], 'reference.webp')
        self.assertEqual(request['style_ruleset'], STYLE_RULESET_VERSION)
        self.assertEqual(request['output_schema'], SCHEMA)
        self.assertNotIn('authorization', request)

    def test_external_finalization_matches_application_policy_for_both_languages(self):
        for language, policy, raw in [('en', EN, RAW_EN), ('ko', KO, RAW_KO)]:
            request = build_external_request(b'image', 1, 1, 'style', language)
            self.assertIn(policy.strip(), request['instructions'])
            self.assertIn(raw, request['instructions'])
            self.assertIn('source-specific style body', request['instructions'])
            self.assertNotIn('application prepends', request['instructions'])
            self.assertIn('not this extraction source', request['instructions'])
            self.assertNotIn('Never invent unseen footwear', request['instructions'])

    def test_character_only_has_no_line_style_rules_or_policy(self):
        request = build_external_request(b'image', 1, 1, 'character', 'ko', '왼쪽 인물')
        self.assertNotIn('LINE FINGERPRINT', request['instructions'])
        self.assertNotIn(EN.strip(), request['instructions'])
        self.assertNotIn(KO.strip(), request['instructions'])
        self.assertEqual(request['input']['character_focus'], '왼쪽 인물')
        self.assertIn('Never invent unseen footwear', request['instructions'])

    def test_line_protocol_reaches_native_and_external_style_paths(self):
        native = build_prompt('both', 'en')
        exported = build_external_request(b'image', 1, 1, 'both', 'en')['instructions']
        for phrase in ['LINE FINGERPRINT', 'Overlap and joins',
                       'Path geometry', 'Width system', 'Tool/workflow hypothesis',
                       'Do not fabricate layer order', '2–4 concise sentences']:
            self.assertIn(phrase, native)
            self.assertIn(phrase, exported)

    def test_schema_is_not_shared_mutable_request_state(self):
        request = build_external_request(b'image', 1, 1, 'both', 'en')
        request['output_schema']['properties']['title']['type'] = 'null'
        self.assertEqual(SCHEMA['properties']['title']['type'], 'string')

    def test_invalid_options_fail_before_building_request(self):
        for mode, language, focus in [('x', 'en', ''), ('both', 'x', ''), ('style', 'en', 'x' * 501)]:
            with self.assertRaises(ValueError):
                build_external_request(b'image', 1, 1, mode, language, focus)

    def test_multiple_images_keep_order_dimensions_and_individual_image_bytes(self):
        images = [{'data': b'first', 'width': 200, 'height': 100}, {'data': b'second', 'width': 30, 'height': 80}]
        request = build_multi_external_request(images, 'style', 'ko')
        self.assertNotIn('image', request['input'])
        self.assertEqual(request['input']['primary_image'], 1)
        self.assertEqual([item['filename'] for item in request['input']['images']], ['reference-01.webp','reference-02.webp'])
        for expected, actual in zip(images, request['input']['images']):
            self.assertEqual(base64.b64decode(actual['data_url'].split(',',1)[1]), expected['data'])
            self.assertEqual(actual['width'], expected['width'])
            self.assertEqual(actual['height'], expected['height'])
        self.assertIn('STYLE CONSENSUS', request['instructions'])
        self.assertIn('STYLE ANCHOR', request['instructions'])
        self.assertIn('reference_summary', request['output_schema']['required'])

    def test_multi_character_mode_cannot_accidentally_analyze_style_or_merge_strangers(self):
        prompt = build_prompt('character', 'en', image_count=3)
        self.assertIn('IDENTITY ACROSS VIEWS', prompt)
        self.assertIn('never a hybrid', prompt)
        self.assertNotIn('STYLE CONSENSUS', prompt)
        self.assertNotIn('LINE FINGERPRINT', prompt)
        self.assertNotIn('IDENTITY ACROSS VIEWS', build_prompt('style','en',image_count=3))

    def test_single_export_remains_compatible_and_invalid_counts_are_rejected(self):
        images = [{'data':b'one','width':20,'height':10}]
        self.assertEqual(build_multi_external_request(images,'both','en'),build_external_request(b'one',20,10,'both','en'))
        for images in ([], images*9):
            with self.assertRaises(ValueError):
                build_multi_external_request(images,'both','en')


if __name__ == '__main__':
    unittest.main()
