#!/usr/bin/env python3
"""Validate exact-SDK second-pass runtime proof; start no compiler or VM."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(root, path):
    path = path.resolve()
    return {'path': str(path.relative_to(root) if path.is_relative_to(root) else path), 'sha256': sha(path)}


def form_at(text, anchor):
    start = text.index(anchor)
    depth = 0
    quoted = escaped = comment = False
    for offset in range(start, len(text)):
        char = text[offset]
        if comment:
            if char == '\n':
                comment = False
            continue
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == ';':
            comment = True
        elif char == '"':
            quoted = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return text[start:offset + 1]
    raise AssertionError('unterminated real producer form')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--proof', type=Path, default=ROOT / '.local/closure-wave-1/runtime-proof-20')
    parser.add_argument('--existing', type=Path, default=ROOT / '.local/final-acceptance/history-3')
    parser.add_argument('--out', type=Path, default=ROOT / 'research/execution-protocol-audit/closure-wave-1/runtime-ownership-second-pass.json')
    args = parser.parse_args()
    root, proof, old = args.root.resolve(), args.proof.resolve(), args.existing.resolve()
    cases = json.loads((root / 'research/execution-protocol-audit/cases.json').read_text())['cases']
    result = json.loads((proof / 'result.json').read_text())
    inputs = json.loads((proof / 'inputs.json').read_text())
    execution = json.loads((proof / 'execution.json').read_text())
    old_result = json.loads((old / 'result.json').read_text())
    old_inputs = json.loads((old / 'inputs.json').read_text())
    old_execution = json.loads((old / 'execution.json').read_text())
    sdk = Path(result['sdk'])
    image = (sdk / 'image').resolve()
    assert result['status'] == 'passed' and result['child_exit'] == 0 and result['frozen_inputs_unchanged'] is True
    assert result['SDK_rebuilt'] is False and result['compiler_rebuilt'] is False
    assert old_result['status'] == 'regressions-passed' and old_result['frozen_inputs_unchanged'] is True
    assert str(sdk) == old_result['sdk'] == old_inputs['sdk']['path']
    assert sha(sdk / 'artifact.json') == result['sdk_metadata_sha256'] == old_inputs['sdk']['metadata']
    assert str(image) == old_inputs['sdk']['image']
    assert execution['image'] == old_execution['image']
    for name, digest in old_inputs['floor'].items():
        assert sha(image / 'priv/bootstrap/seed' / name) == digest
    passed = {}
    for file in execution['files']:
        assert file['status'] == 'passed'
        for test in file['tests']:
            assert test['pass'] > 0 and test['fail'] == test['error'] == 0
            passed[file['path'], test['namespace'], test['test']] = test
    assert len(passed) == 2 and sum(t['pass'] for t in passed.values()) == 35
    old_passed = {(file['path'], test['namespace'], test['test']): test
                  for file in old_execution['files'] if file['status'] == 'passed'
                  for test in file['tests'] if test['pass'] > 0 and test['fail'] == test['error'] == 0}
    log = (proof / 'run.log').read_text()
    for observation in [':history-wave2-E81', ':raw-native-carrier', ':source_native_target_refused',
                        ':installed-SDK-unchanged true', ':history-wave2-E79', ':adoption-result :sdk-runtime',
                        ':after-native-init {:env :global, :generation nil}', ':custody-kind :unmanaged-native-class']:
        assert observation in log, observation
    plans = {
        'E79': ('test/bl/execution_history_sdk_lifetime_wave2_causal_test.bl',
                'execution.history-sdk-lifetime-wave2-causal-test',
                'E79-real-SDK-init-adoption-survives-direct-construction-and-detects-restoring-global-wrapper', 9),
        'E81': ('test/bl/execution_history_cursor_wave2_causal_test.bl',
                'execution.history-cursor-wave2-causal-test',
                'E81-actual-page-producer-keeps-native-cursor-operations-behind-declared-callbacks', 26),
    }
    producers = {
        'E35': ['priv/host/env.bl', 'priv/host/server.bl', 'priv/lib/data/bounded-cache.bl',
                'priv/lib/data/cache-pool.bl', 'priv/std/proc/table.bl', 'priv/lib/live/app.bl'],
        'E79': ['priv/host/env.bl', 'priv/host/server.bl', 'priv/std/proc/table.bl', 'priv/std/proc/framework.bl',
                'priv/std/proc/queue-runtime.bl', 'priv/std/proc/queue.bl', 'priv/std/proc/owner-registry.bl',
                'priv/std/reload/execution.bl', 'priv/std/reload/generation.bl'],
        'E81': ['priv/lib/datom/store-ets.bl', 'priv/lib/datom/store.bl', 'priv/lib/datom/conn.bl',
                'priv/lib/data/bounded-cache.bl', 'priv/host/env.bl', 'priv/host/execution.bl',
                'priv/std/reload/generation.bl'],
    }
    rows = []
    for cid in ['E35', 'E79', 'E81']:
        case = next(case for case in cases if case['id'] == cid)
        selectors = []
        relevant = set(producers[cid])
        for selected in case['selectors']:
            key = selected['path'], selected['namespace'], selected['test']
            assert key in old_passed, key
            assert sha(root / key[0]) == old_inputs['inputs'][key[0]]
            relevant.add(key[0])
            selectors.append({'path': key[0], **old_passed[key], 'execution': 'existing_execution_detail'})
        for path in producers[cid]:
            assert sha(root / path) == inputs[path] == old_inputs['inputs'][path] == sha(image / path), path
        row = {'id': cid, 'issue': case['issue'], 'original_remaining': case['remaining'],
               'status': 'open', 'remaining': case['remaining'], 'selectors': selectors,
               'original_receipt_flags_preserved': True}
        if cid in plans:
            path, namespace, name, count = plans[cid]
            test = passed[path, namespace, name]
            assert test['pass'] == count and sha(root / path) == inputs[path]
            relevant.add(path)
            row['selectors'].append({'path': path, **test, 'execution': 'new_execution_detail'})
        row['source_sha256'] = {path: sha(root / path) for path in sorted(relevant)}
        rows.append(row)
    e35, e79, e81 = rows
    e35.update(
        assessment='All four named real SDK cache/table/session lifetime selectors pass in matching SDK5. The missing proof is the actual absent-adoption causal baseline. Real native starts authenticate original class/module MD5 and a one-shot init receipt; only the actual indexed SDK class can adopt. A private ordinary class is app-owned by design and would confound the result. No SDK module, origin, admission, permit, initializer or native-index row was replaced or invented.',
        minimal_missing_boundary='A genuinely compiler-produced mutant SDK leaf for one existing data-only table/cache/session class, removing only adopt-runtime! and retaining an authentic generated SDK index. Other SDK units and the compiler can remain cached; this is outside this pass\'s no-SDK-build constraint.')
    env_source = (root / 'priv/host/env.bl').read_text()
    before = '(BeamLisp.AOT/sdk_named_constructor! namespace name arity)'
    after = '(let [callable (BeamLisp.AOT/sdk_named_constructor! namespace name arity)] (fn [] (BeamLisp.Env/with_env :global (fn [] (erlang/apply callable (list))))))'
    assert env_source.count(before) == 1
    e79.update(status='partial-real-unmanaged-SDK-init-causal-mechanism-proven',
        remaining=['Execute an authentic nested managed-generation restoration control, with the real SDK init receipt, actual admitted old graph/custody and Source-derived original restoring helper. The unmanaged control has generation nil throughout and does not bind the historical generation-restoration variant.'],
        baseline={'kind': 'source-mutation', 'producer': 'priv/host/env.bl',
                  'producer_sha256': sha(root / 'priv/host/env.bl'), 'before': before, 'after': after,
                  'selector': {k: v for k, v in zip(['path', 'namespace', 'test'], plans['E79'][:3])}},
        qualified_scope='Actual unchanged SDK table-keeper, real unmanaged native start receipt with exact module/MD5, active authenticated SDK init, and genuinely captured fork Env token. Current direct SDK callable leaves ambient global/nil context; restoring the global with_env wrapper reverts the fork immediately and after actual init completion. Both actual adoptions return sdk-runtime; SDK class and Env bytes remain unchanged. No generation or origin is fabricated.',
        historical_mechanism='b5a1e0101d84759980ef5a20283bc54cefc3bb41 added adopted-context commit at the outer initializer fence. That helper is absent from current Source; current sdk_callable! instead returns the physical SDK callable directly. The new constructor mechanism is proven for unmanaged Env lifetime. Existing named queue variants pass independently in exact SDK5, but no real managed-generation restoring counterfactual was executed.')
    producer = 'priv/lib/datom/store-ets.bl'
    source = (root / producer).read_text()
    original_method = form_at(source, '(-ordered-page [s lo after hi limit direction max-bytes]')
    changes = [
        ('step (fn [key] (if descending? (ets/prev table key) (ets/next table key)))',
         'step (if descending? ets/prev ets/next)'),
        ('(step after)', '(step table after)'), ('(step bound)', '(step table bound)'), ('(step k)', '(step table k)'),
    ]
    mutated_method = original_method
    for before, after in changes:
        assert source.count(before) == original_method.count(before) == 1
        mutated_method = mutated_method.replace(before, after)
    assert source.count(original_method) == 1
    e81.update(status='causal-closure-proposed-from-matching-frozen-execution', remaining=[],
        baseline={'kind': 'source-mutation', 'producer': producer, 'producer_sha256': sha(root / producer),
                  'before': original_method, 'after': mutated_method,
                  'mutation_sites': [{'before': before, 'after': after} for before, after in changes],
                  'selector': {k: v for k, v in zip(['path', 'namespace', 'test'], plans['E81'][:3])}},
        qualified_scope='Actual SDK and exact copied ETS OrderedPageScan producer each consume all 17 rows through complete ascending/descending traversal at page sizes 1, 3 and 5. Actual managed Source invokes the statically declared SDK entry; private native producer copies have explicit frozen physical module grants and no ETS grant. Restoring the exact original raw ETS carrier/call arities refuses with source_native_target_refused in every direction/page-size variant; an independent raw ETS native carrier also refuses. Matching SDK5 independently proves actual Source schema initialization, serialized writer and accepted query. Original SDK producer/module bytes are unchanged.',
        producer_adaptations='The actual protocol method is exposed as a plain exported function in each private native probe. Its end sentinel helper is identical and its footprint alias forwards to the actual SDK module derived by Emit/module_for, preserving the hyphen in Bounded-cache. Neither adaptation changes cursor logic or installs SDK metadata.')
    rejected = []
    for name, reason in [
        ('runtime-proof-15', 'Fixture called nonexistent Core vector; no original-case result inferred.'),
        ('runtime-proof-16', 'Fixture passed SDK callback dynamically without a statically declared SDK preparation root; native-framework refusal did not establish a cursor regression.'),
        ('runtime-proof-17', 'Actual SDK ascending page traversal and adoption mechanism executed, but guessed private footprint module and wrong receipt field prevented complete passing controls.'),
    ]:
        artifact = root / '.local/closure-wave-1' / name
        if artifact.exists():
            rejected.append({'reason': reason, **{key: ref(root, artifact / file) for key, file in
                [('result', 'result.json'), ('inputs', 'inputs.json'), ('execution', 'execution.json'), ('log', 'run.log')]}})
    report = {'version': 1, 'scope': 'runtime ownership second focused pass', 'sdk': str(sdk),
              'engine': old_result['engine'], 'SDK_rebuilt': False, 'compiler_rebuilt': False,
              'aggregate_status': result['status'], 'new_tests': 2, 'new_assertions': 35,
              'case_manifest_at_assessment': ref(root, root / 'research/execution-protocol-audit/cases.json'),
              'existing_execution': ref(root, old / 'result.json'),
              'existing_execution_detail': ref(root, old / 'execution.json'),
              'existing_inputs': ref(root, old / 'inputs.json'),
              'new_execution': ref(root, proof / 'result.json'), 'new_execution_detail': ref(root, proof / 'execution.json'),
              'new_inputs': ref(root, proof / 'inputs.json'), 'new_log': ref(root, proof / 'run.log'),
              'closure_proposal_count': 1, 'partial_count': 1, 'open_count': 1,
              'cases': rows, 'retained_failed_or_setup_receipts': rejected}
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['aggregate_status', 'new_tests', 'new_assertions', 'closure_proposal_count', 'partial_count', 'open_count']}))


if __name__ == '__main__':
    main()
