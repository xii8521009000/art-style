from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.style_contract import ensure_style_contract, compile_style_result, EN, KO
from app.prompts import build_prompt


class StylePolicyTests(unittest.TestCase):
    def test_existing_style_gets_authority_without_losing_body(self):
        old = '## Linework\nUse crude broken contours.'
        new = ensure_style_contract(old)
        self.assertTrue(new.startswith(EN.strip()))
        self.assertTrue(new.endswith(old))
        self.assertIn('Ignore the rendering style of every reference image completely',new)
        self.assertIn('stylized proportions',new)

    def test_read_and_write_do_not_repeat_contract(self):
        once = ensure_style_contract('Barely resolved doodle.')
        self.assertEqual(once,ensure_style_contract(once))

    def test_korean_and_unselected_prompt(self):
        self.assertTrue(ensure_style_contract('거친 선','ko').startswith(KO.strip()))
        self.assertIsNone(ensure_style_contract(None))

    def test_a_heading_alone_cannot_bypass_authority(self):
        self.assertTrue(ensure_style_contract('## Reference and style precedence\nCopy reference style.').startswith(EN.strip()))

    def test_older_policy_is_replaced_without_stacking(self):
        old = '## Reference and style precedence\nOld policy.\n\n## Drawing\nKeep broken contours.'
        updated = ensure_style_contract(old)
        self.assertEqual(updated.count('## Reference and style precedence'),1)
        self.assertNotIn('Old policy',updated)
        self.assertTrue(updated.endswith('Keep broken contours.'))

    def test_character_requirements_survive_style_revision(self):
        prompt = build_prompt('both','en')
        self.assertIn('CHARACTER PROMPT —',prompt)
        self.assertIn('700–1400',prompt)
        self.assertIn('Never invent unseen footwear',prompt)
        self.assertNotIn('Every selected prompt should',prompt)

    def test_style_only_does_not_receive_character_proportion_rules(self):
        self.assertNotIn('Never invent unseen footwear',build_prompt('style','en'))
        self.assertIn('Never invent unseen footwear',build_prompt('character','en'))
        self.assertNotIn('PERCEPTUAL AUDIT',build_prompt('character','en'))

    def test_raw_recipe_sets_skill_ceiling_without_overwriting_finished_styles(self):
        raw = compile_style_result({'style_prompt':'Long descriptive guide.','style_execution':'raw_awkward','raw_style_recipe':'Tiny crooked eyelid scratches. Constant fills.'},'style')
        self.assertIn('BADLY DRAWN',raw['style_prompt'])
        self.assertNotIn('Long descriptive guide',raw['style_prompt'])
        self.assertIn('Tiny crooked eyelid',raw['style_prompt'])
        finished = compile_style_result({'style_prompt':'Confident fine pen.','style_execution':'confident_graphic','raw_style_recipe':None},'style')
        self.assertNotIn('BADLY DRAWN',finished['style_prompt'])
        self.assertTrue(finished['style_prompt'].endswith('Confident fine pen.'))

    def test_character_output_never_gets_a_style_recipe(self):
        result = compile_style_result({'style_prompt':'A style','style_execution':'raw_awkward','raw_style_recipe':'Raw'},'character')
        self.assertIsNone(result['style_prompt'])
        self.assertIsNone(result['raw_style_recipe'])

    def test_raw_classification_cannot_silently_fall_back_to_a_polished_guide(self):
        with self.assertRaises(ValueError):
            compile_style_result({'style_prompt':'Polished generic guide.','style_execution':'raw_awkward','raw_style_recipe':None},'style')


if __name__ == '__main__':
    unittest.main()
