#!/usr/bin/env python3
"""Validate reuse of current SDK causal executions; starts no compiler or VM.

A proposal is new analysis of frozen existing execution. It never rewrites the
original replay receipt's historical_case_closed flag or treats file existence
as execution evidence. Pending variants remain explicit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = {'adapters', 'descriptor', 'native'}
OPEN_ASSESSMENTS = {
    'E01': 'Actual cache/index/solver workers passed; Trace currently conveys its handler, but no causal trace/test-child/query-scope matrix is executed. TestRT async child registered-scope propagation needs a direct control.',
    'E16': 'Actual live callable substitutions and transitive support bindings passed. A changed native lambda slot/private bridge or macro factory origin has not been independently executed.',
    'E26': 'Actual replay without mutable shim initialization passed. Wrong immutable callable-home refusal remains a distinct unexecuted variant.',
    'E31': 'Actual BEAM lambda index and private macro origin checks passed. No current producer mutation proves traversal through multiple nested captured closures.',
    'E32': 'Actual explicit cold native grant passed. Source-only SDK unit loading and an original causal loading mutation are still unbound.',
    'E35': 'Actual shared cache/table/session lifetime selectors passed. Proving the historical owner-retention fault requires a real indexed SDK init/lifetime mutation; private forged adoption records would not prove it.',
    'E43': 'Actual same-scope borrowed SDK callback and unused stable boundary selectors passed. New E62 descriptor-walk probe is pending; exact helper/provider initialization and deferred unrelated initializers still require causal binding.',
    'E45': 'Actual emitted companion/cache replay selectors passed. Native metadata invocation with an actual admitted caller remains unbound.',
    'E47': 'Actual generated Source actor and structural init/guard projection selectors passed. Fixed SDK actor counterpart plus compiled init/guard/body ordering traces remain unbound.',
    'E60': 'Actual immutable-SDK proof selectors and opaque callback analysis passed. Original ingress custody baseline is preserved; remaining unexpected symbolic diagnostics and exceptional release paths have no complete current causal receipt.',
    'E62': 'New current producer/list-as-map causal control is authored and pending a parent-coordinated SDK run. Opaque callback registration/invocation is independently covered by the matching SDK5 native_execution_callback_analysis_test selector; it must be explicitly mapped before closure.',
    'E71': 'Current owner transition controls passed, including a real producer mutation. Complete inventory of non-global SDK retirement owners and all named lifetime variants is not proven.',
    'E79': 'Actual queue initializer identity, forged adoption refusal and death cleanup selectors passed. Nested restoration versus committed adoption requires a real indexed SDK initializer mutation; no production module replacement or invented init authority was used.',
    'E81': 'Actual Source Datom writer/schema/query flow passed. Complete page/cursor iteration and refusal of raw native carriers have not been executed as independent controls.',
    'E86': 'Actual live codegen-source key prediction passed and includes Server. Changed server rule/entry ABI must still be exercised against actual cached emitted output; key formula equality alone cannot close this case.',
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(root, path):
    return {'path': str(path.relative_to(root) if path.is_relative_to(root) else path), 'sha256': sha(path)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--execution', type=Path, default=ROOT / '.local/final-acceptance/history-3')
    parser.add_argument('--proof', type=Path, default=ROOT / '.local/closure-wave-1/focused-proof-4')
    parser.add_argument('--readiness-proof', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'research/execution-protocol-audit/closure-wave-1/runtime-ownership.json')
    args = parser.parse_args()
    root, execution = args.root.resolve(), args.execution.resolve()
    manifest = json.loads((root / 'research/execution-protocol-audit/cases.json').read_text())
    result = json.loads((execution / 'result.json').read_text())
    inputs = json.loads((execution / 'inputs.json').read_text())
    actual = json.loads((execution / 'execution.json').read_text())
    assert result['status'] == 'regressions-passed' and result['frozen_inputs_unchanged'] is True
    assert len(result['cases']) == 86 and result['files'] == 106 and result['tests'] == 200
    sdk, image = Path(result['sdk']), Path(inputs['sdk']['image'])
    assert inputs['sdk']['path'] == str(sdk) and result['engine'] == inputs['sdk']['engine']
    assert sha(sdk / 'artifact.json') == inputs['sdk']['metadata']
    assert (sdk / 'image').resolve() == image.resolve()
    for name, digest in inputs['floor'].items():
        assert sha(image / 'priv/bootstrap/seed' / name) == digest
    assert inputs['inputs']['test/scripts/execution-history-driver.bl'] == sha(root / 'test/scripts/execution-history-driver.bl')
    passed = {}
    for file in actual['files']:
        assert file['status'] == 'passed'
        for test in file['tests']:
            assert test['pass'] > 0 and test['fail'] == 0 and test['error'] == 0
            passed[(file['path'], test['namespace'], test['test'])] = test
    log = '\n'.join(p.read_text() for p in sorted(execution.glob('run-*.log')))
    before_row = (root / 'priv/host/env.bl').read_text()
    offset = before_row.index('(defn- unretained_sdk_forwarders!')
    start = before_row.index('           row (when-not covered', offset)
    end = before_row.index('\n      (if-not row out', start)
    before_row = before_row[start:end]
    fixture = (root / 'test/fixtures/sdk_prelease_publication_control.bl').read_text()
    block = re.search(r'historical-row \(str (.*?)\)\n      fixed-row', fixture, re.S).group(1)
    literals = re.findall(r'"(?:[^"\\]|\\.)*"', block)
    assert re.sub(r'"(?:[^"\\]|\\.)*"', '', block).strip() == ''
    historical_row = ''.join(json.loads(value) for value in literals)
    plans = {
        'E02': ('priv/host/aot_cache.bl', '(Map/put slots root now)', '(Map/put (Map/new) root now)',
                'test/bl/execution_history_native_test.bl', 'execution.history-native-test',
                'E02-original-root-switch-regression-detects-singleton-throttle-publication'),
        'E07': ('priv/host/aot_cache.bl', '(generation_lock_path root (Map/get g :name)) false true',
                '(generation_lock_path root (Map/get g :name)) true true',
                'test/bl/execution_qualification_test.bl', 'execution.qualification-test',
                'E06-E07-independent-vms-enforce-build-and-generation-custody'),
        'E21': ('priv/host/env.bl', before_row, historical_row,
                'test/bl/reload/sdk_prelease_publication_control_test.bl', 'reload.sdk-prelease-publication-control-test',
                'real-image-before-first-lease-protects-seed-only-code-and-detects-the-image-only-mutation'),
        'E37': ('priv/host/loader.bl', '(and (or (Process/get :bl_generation) (Process/get :bl_application_identity))\n           (BeamLisp.AOT/sdk_library_unit? ns))', 'false',
                'test/bl/reload/sdk_loading_context_control_test.bl', 'reload.sdk-loading-context-control-test',
                'source-derived-loader-without-sdk-redirect-must-fail-the-same-invariant'),
        'E74': ('priv/host/env.bl', '(if-not (source_data_decode_required?) (capture)', '(if-not false (capture)',
                'test/bl/reload/source_context_projection_causal_test.bl', 'reload.source-context-projection-causal-test',
                'raw-context-cannot-roundtrip-through-the-source-binding-boundary'),
        'E76': ('priv/std/proc/evolve.bl', '(control-spec grant spec)', 'spec',
                'test/bl/proc/evolve_composed_control_causal_test.bl', 'proc.evolve-composed-control-causal-test',
                'composed-source-owner-requires-an-opaque-control-payload-before-candidate-admission'),
    }
    child_files = {
        'E07': ['test/scripts/test_execution_process_custody.py', 'test/scripts/execution-custody-worker.exs',
                'test/scripts/execution-qualification-driver.py', 'priv/build/build.bl', 'priv/std/bl/cli.bl'],
        'E21': ['test/fixtures/sdk_prelease_publication_control.bl', 'test/fixtures/execution_publication_before_lease.bl',
                'test/scripts/check_sdk_prelease_publication.py', 'test/support/source_fixtures.bl'],
        'E37': ['test/fixtures/sdk_loading_context_control.bl', 'test/fixtures/sdk_sealed_loading_context_control.bl',
                'test/scripts/check_sdk_sealed_initialization.py', 'test/support/source_fixtures.bl'],
    }
    proof = args.proof.resolve()
    proof_result = json.loads((proof / 'result.json').read_text())
    proof_inputs = json.loads((proof / 'inputs.json').read_text())
    proof_execution = json.loads((proof / 'execution.json').read_text())
    assert proof_result['sdk'] == str(sdk)
    assert proof_result['sdk_metadata_sha256'] == inputs['sdk']['metadata']
    assert proof_result['frozen_inputs_unchanged'] is True
    assert proof_result['SDK_rebuilt'] is False and proof_result['compiler_rebuilt'] is False
    assert proof_execution['image']['priv-root'] == str(image / 'priv')
    assert proof_execution['image']['compiler-key'] == actual['image']['compiler-key']
    probe_path = 'test/bl/execution_history_runtime_ownership_causal_test.bl'
    probe_ns = 'execution.history-runtime-ownership-causal-test'
    probe_file = next(file for file in proof_execution['files'] if file['path'] == probe_path)
    assert probe_file['status'] == 'passed'
    probe_passed = {test['test']: test for test in probe_file['tests']}
    proof_log = (proof / 'run.log').read_text()
    fresh_plans = {
        'E08': ('priv/host/aot.bl',
                '(Map/get (Process/get :bl_definition_collector) :declarations)',
                '(if (constructor_context) (Map/get (Process/get :bl_definition_collector) :declarations) {})',
                'E08-current-staged-declarations-select-the-same-provider-as-the-emitted-table'),
        'E18': ('priv/host/aot.bl',
                '(Enum/reduce (rest (elem form 1)) vdefs\n        (fn [nested out] (capture_value_def out nested ns)))',
                'vdefs', 'E18-current-nested-collector-emits-values-that-survive-fresh-replay'),
        'E85': ('priv/host/loader.bl',
                '(and loaded (erlang/is_list path)\n             (erlang/== (Path/dirname (Path/expand (erlang/list_to_binary path))) (Path/expand ebin))\n             (erlang/function_exported mod :__bl_init__ 0)\n             (let [row (BeamLisp.AOT/sdk_compiler_row mod)]\n               (and row (erlang/== ns (Map/get row :forwarder-namespace))\n                        (erlang/== :mutable-forwarder (Map/get row :role)))))',
                '(and loaded (erlang/function_exported mod :__bl_init__ 0))',
                'E85-tier-ownership-requires-a-real-SDK-row-and-physical-library-path'),
    }
    assert ':history-wave-E08' in proof_log and ':declarations {}' in proof_log
    assert ':history-wave-E18' in proof_log and ':replayed {:first {:ok, 3}, :second {:ok, 2}}' in proof_log
    assert ':history-wave-E85' in proof_log and ':ordinary-normal false, :ordinary-mutant true' in proof_log
    assert ':genuine-sdk-owner "datom"' in proof_log and ':self-is-sdk false, :tooling-library-is-sdk true' in proof_log
    readiness = None
    if args.readiness_proof:
        receipt = args.readiness_proof.resolve()
        receipt_result = json.loads((receipt / 'result.json').read_text())
        receipt_inputs = json.loads((receipt / 'inputs.json').read_text())
        receipt_execution = json.loads((receipt / 'execution.json').read_text())
        assert receipt_result['sdk'] == str(sdk)
        assert receipt_result['sdk_metadata_sha256'] == inputs['sdk']['metadata']
        assert receipt_result['frozen_inputs_unchanged'] is True
        assert receipt_result['SDK_rebuilt'] is False and receipt_result['compiler_rebuilt'] is False
        assert receipt_execution['image'] == proof_execution['image']
        test_path = 'test/bl/execution_history_readiness_causal_test.bl'
        file = next(file for file in receipt_execution['files'] if file['path'] == test_path)
        test = next(test for test in file['tests'] if test['test'] == 'E62-current-definition-list-walk-reaches-real-SDK-helper-bodies')
        assert file['status'] == 'passed' and test['pass'] >= 10 and test['fail'] == test['error'] == 0
        receipt_log = (receipt / 'run.log').read_text()
        for observation in [':normal-follows-helper true', ':mutant-follows-helper false',
                            ':normal-follows-helper-body true', ':mutant-follows-helper-body false',
                            ':unused-namespace-unchanged true']:
            assert observation in receipt_log, observation
        readiness = (receipt, receipt_inputs, test_path, test)
    # These observations are emitted by assertions in the exact frozen controls.
    assert ':actual-policy :seed-protected' in log
    assert ':historical-changed {:status :returned, :value {}}' in log
    assert ':mode "without-redirect"' in log and ':invariant false' in log
    assert ':mode "copied-original"' in log and ':initialization-count 1' in log
    assert ':history-E74-raw-roundtrip {:reason :source_context_scope_refused, :status :refused}' in log
    assert ':history-E76-raw-control' in log and ':payload-map? true' in log and ':owner-reason :source_native_target_refused' in log
    rows = []
    for case in manifest['cases']:
        if case['family'] not in FAMILIES or not case['remaining']:
            continue
        row = {'id': case['id'], 'family': case['family'], 'issue': case['issue'],
               'original_remaining': case['remaining'], 'status': 'open',
               'remaining': case['remaining']}
        if case['id'] in OPEN_ASSESSMENTS:
            row['assessment'] = OPEN_ASSESSMENTS[case['id']]
        if case['id'] == 'E62':
            rejected = root / '.local/closure-wave-1/complete-proof-5'
            if rejected.exists():
                rejected_execution = json.loads((rejected / 'execution.json').read_text())
                rejected_file = next(file for file in rejected_execution['files']
                                     if file['path'] == 'test/bl/execution_history_readiness_causal_test.bl')
                rejected_test = next(test for test in rejected_file['tests']
                                     if test['test'] == 'E62-current-definition-list-walk-reaches-real-SDK-helper-bodies')
                assert rejected_test['pass'] == 7 and rejected_test['fail'] == 3 and rejected_test['error'] == 0
                row['rejected_causal_control'] = {
                    'result': ref(root, rejected / 'result.json'),
                    'execution': ref(root, rejected / 'execution.json'),
                    'inputs': ref(root, rejected / 'inputs.json'),
                    'log': ref(root, rejected / 'run.log'), 'test': rejected_test,
                    'before': ':definitions (Map/new definitions)', 'after': ':definitions definitions',
                    'reason': 'Current Env/ns_defs already returns a map: removing Map.new retains the map and traverses the same 38 references. This failed control cannot establish original list-as-map causality.',
                    'historical_fix_commit': '235437ec599132c85a9941e6f46b748aec35d211',
                }
        if case['id'] in plans:
            producer, before, after, path, namespace, name = plans[case['id']]
            text = (root / producer).read_text()
            assert text.count(before) == 1
            relevant = {producer, *child_files.get(case['id'], [])}
            selectors = []
            for selected in case['selectors']:
                key = (selected['path'], selected['namespace'], selected['test'])
                assert key in passed, (case['id'], key)
                selectors.append({'path': key[0], 'namespace': key[1], 'test': key[2], **passed[key]})
                relevant.add(key[0])
            assert (path, namespace, name) in passed
            for file in relevant:
                assert sha(root / file) == inputs['inputs'][file], file
            assert sha(root / producer) == sha(image / producer), producer
            source_sha = sha(root / producer)
            if case['id'] == 'E02':
                assert source_sha.upper() in log
                assert hashlib.sha256(text.replace(before, after).encode()).hexdigest().upper() in log
                assert ':normal {:error 0, :pass 2, :fail 0, :tests 1}' in log
                assert ':mutant {:error 0, :pass 1, :fail 1, :tests 1}' in log
            if case['id'] in {'E21', 'E37'}:
                assert source_sha in log
            row.update(status='causal-closure-proposed-from-matching-frozen-execution',
                remaining=[], selectors=selectors, original_receipt_flags_preserved=True,
                source_sha256={file: sha(root / file) for file in sorted(relevant)},
                baseline={'kind': 'source-mutation', 'producer': producer, 'producer_sha256': source_sha,
                          'before': before, 'after': after,
                          'selector': {'path': path, 'namespace': namespace, 'test': name}},
                justification='All mapped selectors and the current-producer original/mutation control passed in the exact final immutable SDK. Every relevant producer/test/child file still matches the frozen execution; SDK Source and current Source match. Original false historical_case_closed flags are retained in their original receipt. This is a separately validated closure proposal.')
        elif case['id'] in fresh_plans:
            producer, before, after, name = fresh_plans[case['id']]
            producer_text = (root / producer).read_text()
            assert producer_text.count(before) == 1
            relevant = {producer, probe_path}
            assert sha(root / probe_path) == proof_inputs[probe_path]
            assert sha(root / producer) == proof_inputs[producer] == inputs['inputs'][producer] == sha(image / producer)
            probe_test = probe_passed[name]
            assert probe_test['pass'] > 0 and probe_test['fail'] == 0 and probe_test['error'] == 0
            selectors = []
            for selected in case['selectors']:
                key = (selected['path'], selected['namespace'], selected['test'])
                assert key in passed, (case['id'], key)
                assert sha(root / key[0]) == inputs['inputs'][key[0]]
                relevant.add(key[0])
                selectors.append({'path': key[0], **passed[key], 'execution': 'existing_execution_detail'})
            selectors.append({'path': probe_path, **probe_test, 'execution': 'new_execution_detail'})
            row.update(status='causal-closure-proposed-from-matching-frozen-execution', remaining=[],
                selectors=selectors, original_receipt_flags_preserved=True,
                source_sha256={file: sha(root / file) for file in sorted(relevant)},
                baseline={'kind': 'source-mutation', 'producer': producer, 'producer_sha256': sha(root / producer),
                          'before': before, 'after': after,
                          'selector': {'path': probe_path, 'namespace': probe_ns, 'test': name}},
                justification='The fresh per-test candidate/mutation control passed in the unchanged immutable SDK; all named original variants passed in the previous frozen replay with matching producer/test/SDK identity. The focused aggregate failed on other agents\' cases, and is retained as failed. This proposal relies only on the explicit passed file and passed selector rows, never the aggregate status. Ordinary generated artifacts and private probe modules carry no invented SDK origin, admission, permit or native-index rows.')
        elif case['id'] == 'E62' and readiness:
            receipt, receipt_inputs, test_path, test = readiness
            producer = 'priv/std/reload/sdk-readiness.bl'
            before, after = ':definitions (Map/new definitions)', ':definitions (Enum/to_list definitions)'
            assert (root / producer).read_text().count(before) == 1
            assert sha(root / producer) == receipt_inputs[producer] == inputs['inputs'][producer] == sha(image / producer)
            assert sha(root / test_path) == receipt_inputs[test_path]
            opaque = ('test/bl/native_execution_callback_analysis_test.bl', 'native-execution-callback-analysis-test',
                      'metadata-analysis-borrows-the-actual-retained-callback-after-graph-retirement')
            source_roundtrip = ('test/bl/proc/callback_handle_boundary_test.bl', 'proc.callback-handle-boundary-test',
                                'managed-source-roundtrips-an-opaque-registration-without-a-wrapper')
            relevant = {producer, test_path, opaque[0], source_roundtrip[0], 'test/support/source_fixtures.bl',
                        'test/fixtures/source_effect_observer.bl', 'priv/host/env.bl', 'priv/host/execution.bl',
                        'priv/std/proc/callback.bl', 'priv/std/proc/message-domain.bl', 'priv/std/reload/generation.bl',
                        'priv/std/proc/dispatch.bl', 'priv/std/proc/admission.bl'}
            selectors = []
            for key in [(s['path'], s['namespace'], s['test']) for s in case['selectors']] + [opaque, source_roundtrip]:
                assert key in passed, key
                relevant.add(key[0])
                selectors.append({'path': key[0], **passed[key], 'execution': 'existing_execution_detail'})
            for path in relevant - {test_path}:
                assert sha(root / path) == inputs['inputs'][path], path
                if path.startswith('priv/'):
                    assert sha(root / path) == sha(image / path), path
            selectors.append({'path': test_path, **test, 'execution': 'readiness_execution_detail'})
            row.update(status='causal-closure-proposed-from-matching-frozen-execution', remaining=[],
                selectors=selectors, original_receipt_flags_preserved=True,
                source_sha256={path: sha(root / path) for path in sorted(relevant)},
                baseline={'kind': 'source-mutation', 'producer': producer, 'producer_sha256': sha(root / producer),
                          'before': before, 'after': after,
                          'selector': {'path': test_path, 'namespace': test['namespace'], 'test': test['test']}},
                justification='Actual current readiness Source, compiled into fresh ordinary namespaces, follows real definition bodies and transitive native helper references; restoring the historical list container with Enum.to_list at the actual definitions boundary loses them. Current Env/ns_defs already returns a map, so removing Map.new alone is a retained failed/no-op control. The observer only records existing enqueue! calls and descriptor container kinds, preserving actual SDK loads. Matching immutable SDK5 independently proves managed Source registering, returning, observing, invoking and closing an opaque token without a wrapper, plus retired callback invocation, copied selector refusal and unregister cancellation. All canonical variants and relevant producer/helper/test hashes match their frozen executions.')
            row.pop('assessment', None)
        rows.append(row)
    report = {'version': 1, 'scope': 'runtime/ownership causal closure reuse and current-producer controls', 'executed_new_VM': True,
              'SDK_rebuilt': False, 'sdk': str(sdk), 'engine': result['engine'],
              'case_manifest_at_assessment': ref(root, root / 'research/execution-protocol-audit/cases.json'),
              'existing_execution': ref(root, execution / 'result.json'),
              'existing_execution_detail': ref(root, execution / 'execution.json'),
              'existing_inputs': ref(root, execution / 'inputs.json'),
              'existing_logs': [ref(root, p) for p in sorted(execution.glob('run-*.log'))],
              'new_execution': ref(root, proof / 'result.json'),
              'new_execution_detail': ref(root, proof / 'execution.json'),
              'new_inputs': ref(root, proof / 'inputs.json'),
              'new_log': ref(root, proof / 'run.log'),
              'new_aggregate_status_preserved': proof_result['status'],
              'proposal_count': sum(row['status'].startswith('causal-closure-proposed') for row in rows),
              'open_count': sum(row['status'] == 'open' for row in rows), 'cases': rows}
    if readiness:
        receipt = readiness[0]
        report.update(readiness_execution=ref(root, receipt / 'result.json'),
                      readiness_execution_detail=ref(root, receipt / 'execution.json'),
                      readiness_inputs=ref(root, receipt / 'inputs.json'),
                      readiness_log=ref(root, receipt / 'run.log'))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['proposal_count', 'open_count', 'executed_new_VM', 'SDK_rebuilt']}))

if __name__ == '__main__':
    main()
