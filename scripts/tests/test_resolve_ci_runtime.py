import copy
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('resolve_ci_runtime', ROOT / 'scripts/resolve-ci-runtime.py')
RESOLVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESOLVE)
REPOSITORY = 'undefine-org/enchant'
REVISION = 'a' * 40


def run_record(identity=123):
    return {'id': identity, 'name': 'ci', 'path': '.github/workflows/ci.yml',
            'repository': {'full_name': REPOSITORY}, 'head_repository': {'full_name': REPOSITORY},
            'event': 'push', 'head_branch': 'main', 'head_sha': REVISION,
            'status': 'completed', 'conclusion': 'success'}


class ResolveRuntimeTests(unittest.TestCase):
    def test_only_fully_successful_exact_trusted_main_ci_is_qualified(self):
        self.assertTrue(RESOLVE.qualified(run_record(), REPOSITORY, REVISION))
        mutations = {'id': True, 'name': 'other', 'path': '.github/workflows/other.yml',
                     'repository': {'full_name': 'other/repository'},
                     'head_repository': {'full_name': 'someone/fork'},
                     'event': 'pull_request', 'head_branch': 'feature', 'head_sha': 'b' * 40,
                     'status': 'in_progress', 'conclusion': 'failure'}
        for field, value in mutations.items():
            with self.subTest(field=field):
                edited = dict(run_record(), **{field: value})
                self.assertFalse(RESOLVE.qualified(edited, REPOSITORY, REVISION))
        self.assertFalse(RESOLVE.qualified(run_record(), REPOSITORY, REVISION, '124'))

    def test_workflow_run_revalidates_exact_payload_and_never_falls_back_on_failure(self):
        requests = []
        def request(endpoint):
            requests.append(endpoint)
            return run_record()
        self.assertEqual('123', RESOLVE.resolve(REPOSITORY, REVISION, '123', request=request))
        self.assertEqual([f'repos/{REPOSITORY}/actions/runs/123'], requests)
        with self.assertRaisesRegex(ValueError, 'did not fully qualify'):
            RESOLVE.resolve(REPOSITORY, REVISION, '123', request=lambda _: dict(run_record(), conclusion='failure'))

    def test_tag_or_dispatch_reuses_newest_success_after_complete_run_revalidation(self):
        requests = []
        def request(endpoint):
            requests.append(endpoint)
            if '/workflows/ci.yml/runs?' in endpoint:
                return {'workflow_runs': [run_record(123), run_record(124)]}
            return run_record(124)
        self.assertEqual('124', RESOLVE.resolve(REPOSITORY, REVISION, request=request))
        self.assertIn('branch=main&event=push', requests[0])
        self.assertIn('head_sha=' + REVISION + '&status=success', requests[0])
        self.assertEqual(f'repos/{REPOSITORY}/actions/runs/124', requests[1])
        self.assertEqual(2, len(requests))

    def test_no_qualified_ci_keeps_normal_production_and_inventory(self):
        self.assertEqual('', RESOLVE.resolve(REPOSITORY, REVISION,
                                             request=lambda _: {'workflow_runs': []}))
        for edit in ({'event': 'workflow_dispatch'}, {'status': 'in_progress', 'conclusion': None}):
            with self.subTest(edit=edit):
                self.assertEqual('', RESOLVE.resolve(REPOSITORY, REVISION, request=lambda _: {
                    'workflow_runs': [dict(run_record(), **edit)]}))

    def test_run_restarted_after_list_result_is_not_reused_and_api_errors_stay_errors(self):
        def restarted(endpoint):
            if '/workflows/' in endpoint:
                return {'workflow_runs': [run_record()]}
            return dict(run_record(), status='in_progress', conclusion=None)
        self.assertEqual('', RESOLVE.resolve(REPOSITORY, REVISION, request=restarted))
        def unavailable(_):
            raise RuntimeError('API unavailable')
        with self.assertRaisesRegex(RuntimeError, 'API unavailable'):
            RESOLVE.resolve(REPOSITORY, REVISION, request=unavailable)

    def test_search_paginates_without_accepting_untrusted_runs(self):
        pages = []
        def request(endpoint):
            if '/workflows/' not in endpoint:
                return run_record(125)
            pages.append(endpoint)
            if endpoint.endswith('&page=1'):
                return {'workflow_runs': [dict(run_record(n), head_branch='foreign') for n in range(100)]}
            return {'workflow_runs': [run_record(125)]}
        self.assertEqual('125', RESOLVE.resolve(REPOSITORY, REVISION, request=request))
        self.assertEqual(2, len(pages))


class ReleasePublicationGateTests(unittest.TestCase):
    def test_actual_tag_gate_allows_skipped_inventory_only_with_resolved_ci(self):
        source = (ROOT / '.github/workflows/release.yml').read_text()
        block = source.split('  publish:\n', 1)[1]
        condition = re.search(r'    if: >-\n((?:      .*\n)+)', block)[1]
        expression = ' '.join(line.strip() for line in condition.splitlines())
        replacements = {'always()': 'True', 'github.ref_type': 'ref_type',
                        'needs.resolve-runtime.result': 'resolver',
                        'needs.resolve-runtime.outputs.runtime_run': 'runtime',
                        'needs.linux.result': 'linux', 'needs.linux-inventory.result': 'inventory',
                        'needs.linux-native-inventory.result': 'native'}
        for before, after in replacements.items():
            expression = expression.replace(before, after)
        expression = expression.replace('&&', 'and').replace('||', 'or')
        baseline = dict(ref_type='tag', resolver='success', linux='success',
                        inventory='skipped', native='skipped', runtime='123')
        for changes, expected in (({}, True), ({'runtime': ''}, False),
                                  ({'runtime': '', 'inventory': 'success', 'native': 'success'}, True),
                                  ({'resolver': 'failure'}, False), ({'linux': 'failure'}, False),
                                  ({'inventory': 'failure'}, False), ({'native': 'failure'}, False),
                                  ({'ref_type': 'branch'}, False)):
            with self.subTest(changes=changes):
                context = copy.copy(baseline)
                context.update(changes)
                self.assertEqual(expected, eval(expression, {'__builtins__': {}}, context))
