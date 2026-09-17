"""English examples must keep the same decisions and authorization behavior."""
import ast
import copy
import json
import re
import sys
import unittest
from pathlib import Path

import zen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from approval import ApprovalService, ApprovalError, SCENARIOS, REVIEWERS, AGENTS, VERSIONS
from build_rules import CHECKS
from build_english import artifacts, translate, translate_json

HAN = re.compile(r'[\u3400-\u9fff]')


class EnglishTests(unittest.TestCase):
    def test_generated_assets_are_current(self):
        for path, content in artifacts().items():
            with self.subTest(path=path.name):
                self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_all_system_copy_has_an_english_translation(self):
        html = (ROOT/'static/index.en.html').read_text(encoding='utf-8').replace('中文', '')
        self.assertIsNone(HAN.search(html))
        script = (ROOT/'static/app.en.js').read_text(encoding='utf-8').split("'use strict';", 1)[1]
        script = '\n'.join(line for line in script.splitlines() if not line.startswith('const receiptPayload='))
        self.assertIsNone(HAN.search(script))
        for group in (AGENTS, REVIEWERS, VERSIONS):
            self.assertIsNone(HAN.search(json.dumps(translate_json(group), ensure_ascii=False)))
        for scenario in SCENARIOS:
            self.assertIsNone(HAN.search(json.dumps(translate_json(scenario), ensure_ascii=False)))
        for _, label, rules in CHECKS:
            self.assertIsNone(HAN.search(translate(label)))
            for _, _, _, reason, _ in rules:
                self.assertIsNone(HAN.search(translate(reason)))
        # Validate error strings, including each part of interpolated field errors.
        for source in ('approval.py', 'server.py'):
            for node in ast.walk(ast.parse((ROOT/source).read_text(encoding='utf-8'))):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and len(node.exc.args) > 1:
                    for part in ast.walk(node.exc.args[1]):
                        if isinstance(part, ast.Constant) and isinstance(part.value, str):
                            self.assertIsNone(HAN.search(translate(part.value)), part.value)

    def test_all_scenarios_keep_outcomes_in_both_versions(self):
        for version in ('v1', 'v2'):
            for scenario in SCENARIOS:
                with self.subTest(version=version, scenario=scenario['id']):
                    service = ApprovalService()
                    try:
                        service.switch_policy(version)
                        original = service.evaluate(scenario['request'])['decision']
                        english = service.evaluate(translate_json(scenario['request']))['decision']
                        self.assertEqual(original['outcome'], english['outcome'])
                        self.assertEqual(original['required_roles'], english['required_roles'])
                        self.assertEqual([c['code'] for c in original['checks']], [c['code'] for c in english['checks']])
                    finally:
                        service.close()

    def test_english_graph_only_changes_display_copy(self):
        original = json.loads((ROOT/'rules/agent-approval.json').read_text(encoding='utf-8'))
        english = json.loads((ROOT/'rules/agent-approval.en.json').read_text(encoding='utf-8'))
        self.assertIsNone(HAN.search(json.dumps(english, ensure_ascii=False)))
        # Strip only the intended presentation fields; compare all executable conditions and outputs.
        def strip_copy(graph):
            graph = copy.deepcopy(graph)
            for node in graph['nodes']:
                node.pop('name', None)
                content = node.get('content', {})
                for column in content.get('inputs', []) + content.get('outputs', []):
                    column.pop('name', None)
                for rule in content.get('rules', []):
                    rule.pop('reason', None)
            return graph
        self.assertEqual(strip_copy(original), strip_copy(english))

    def test_english_editor_samples_run_in_real_engine(self):
        engine = zen.ZenEngine()
        decision = engine.create_decision((ROOT/'rules/agent-approval.en.json').read_text(encoding='utf-8'))
        for name, outcome in [('redact-mail', 'redact'), ('multi-review', 'review'), ('secret', 'deny')]:
            with self.subTest(name=name):
                sample = json.loads((ROOT/'samples'/f'{name}.en.json').read_text(encoding='utf-8'))
                self.assertEqual(sample['facts']['payload_bytes'], len(sample['request']['payload'].encode('utf-8')))
                self.assertEqual(sample['facts']['purpose_length'], len(sample['request']['purpose']))
                result = decision.evaluate(sample)['result']
                self.assertEqual(result['outcome'], outcome)
                self.assertIsNone(HAN.search(json.dumps(result['checks'], ensure_ascii=False)))

    def test_english_redaction_preserves_request_and_audit(self):
        service = ApprovalService()
        try:
            request = translate_json(SCENARIOS[1]['request'])
            before = copy.deepcopy(request)
            evaluated = service.evaluate(request)
            result = service.execute(evaluated['id'], evaluated['grant_token'], request)
            self.assertEqual(result['request']['request'], before)
            self.assertEqual(request, before)
            payload = result['receipt']['effective_payload']
            self.assertNotIn('customer@example.test', payload)
            self.assertNotIn('13800138000', payload)
            self.assertIn('Product: demo device', payload)
            self.assertTrue(service.state()['audit_valid'])
            with self.assertRaises(ApprovalError) as error:
                service.execute(evaluated['id'], evaluated['grant_token'], request)
            self.assertEqual(error.exception.code, 'ALREADY_EXECUTED')
        finally:
            service.close()

    def test_english_multi_role_approval_and_payload_binding(self):
        service = ApprovalService()
        try:
            request = translate_json(SCENARIOS[5]['request'])
            evaluated = service.evaluate(request)
            reviewed = service.review(evaluated['id'], 'chen', 'Security checks completed.')
            self.assertEqual(reviewed['state'], 'pending')
            reviewed = service.review(evaluated['id'], 'zhou', 'Budget checked and approved.')
            self.assertEqual(reviewed['state'], 'authorized')
            with self.assertRaises(ApprovalError) as error:
                service.execute(reviewed['id'], reviewed['grant_token'], dict(request, payload='Changed after approval'))
            self.assertEqual(error.exception.code, 'CONTENT_CHANGED')
        finally:
            service.close()

    def test_user_content_and_audit_notes_stay_verbatim(self):
        service = ApprovalService()
        try:
            request = translate_json(SCENARIOS[2]['request'])
            request['payload'] = '人工批准 is a literal in user text, not an event label.'
            evaluated = service.evaluate(request)
            note = 'Checked user content: 人工批准.'
            reviewed = service.review(evaluated['id'], 'lin', note)
            result = service.execute(reviewed['id'], reviewed['grant_token'], request)
            self.assertEqual(result['receipt']['effective_payload'], request['payload'])
            self.assertEqual(reviewed['approvals'][0]['note'], note)
            self.assertEqual(next(e for e in service.state()['events'] if 'note' in e['detail'])['detail']['note'], note)
            self.assertTrue(service.state()['audit_valid'])
        finally:
            service.close()


if __name__ == '__main__':
    unittest.main()
