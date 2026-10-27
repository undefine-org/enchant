"""Explicit sealed coverage; focused receipts never certify omitted profiles."""

GROUPS = {
    "imports": ([('test/bl/contextual_import_test.bl', 25), ('test/bl/contextual_phase_value_test.bl', 15)], ['compile.world']),
    "ownership": ([('test/bl/system/ownership_test.bl', 136)], ['compile.world']),
    "ownership-calls": ([('test/bl/system/ownership_calls_test.bl', 123)], ['compile.world']),
    "native-outcomes": ([('test/bl/system/ownership_native_test.bl', 207)], ['system.ownership']),
    "vectors": ([('test/bl/vector_get_default_test.bl', 65)], []),
    "handoffs": ([('test/bl/native_execution_handoff_test.bl', 46)], []),
    "loops": ([('test/bl/system/ownership_loops_test.bl', 77)], ['compile.world']),
    "af": ([('test/bl/system/af_worklist_test.bl', 75)], ['system.gfp']),
    "capacity": ([('test/bl/proc_callback_capacity_test.bl', 101)], ['proc.callback', 'system.ownership']),
    "supervisor-context": ([('test/bl/proc/supervisor_context_test.bl', 32)], []),
    "message-context": ([('test/bl/native_execution_callback_analysis_test.bl', 16)], ['proc.message-domain']),
    "returns": ([('test/bl/server_return_model_test.bl', 10)], []),
    "clauses": ([('test/bl/execution_clause_identity_test.bl', 5)], []),
    "constructor-calls": ([('test/bl/reload/reconcile_callsite_test.bl', 5)], ['reload.reconcile-callsite', 'proc.reconcile-runtime']),
    "solver-frames": ([('test/bl/execution_solver_protocol_test.bl', 71)], []),
    "solver-lifetime": ([('test/bl/execution_solver_lifetime_test.bl', 47)], []),
    "solver-retirement": ([('test/bl/system/z3_retirement_test.bl', 9)], ['z3pool']),
    "filesystem": ([('test/bl/file_lock_test.bl', 15), ('test/bl/build_claim_reentrant_test.bl', 77)], []),
    "filesystem-operations": ([('test/bl/build_custody_operations_test.bl', 71)], ['selfbuild']),
    "filesystem-refresh": ([('test/bl/vm/native_refresh_test.bl', 43), ('test/bl/native_runtime_custody_test.bl', 17)], ['vm.native', 'build', 'artifact', 'bl.artifacts']),
    "filesystem-regressions": ([('test/bl/build_custody_regressions_test.bl', 30)], ['deps-compile', 'selfbuild']),
}
BOUNDARIES = {
    'unit-metadata': ['clauses'], 'source-and-class-proof': ['handoffs', 'capacity'],
    'preboot-identity': ['clauses', 'filesystem'], 'sealed-loader': [],
    'constructor-and-scope': ['imports', 'native-outcomes', 'constructor-calls'], 'artifact-profile-and-cache': ['imports'],
    'native-custody': ['native-outcomes', 'handoffs', 'capacity', 'supervisor-context', 'message-context'],
    'record-representation': ['returns'], 'contextual-pipeline-identity': ['imports', 'clauses'],
    'contextual-analysis-reports': ['ownership', 'ownership-calls', 'native-outcomes', 'loops', 'af'],
    'vector-lookup-default': ['vectors'], 'finite-cleanup-progress': ['loops', 'af'],
    'constructor-evaluation-order': ['returns'], 'execution-clause-identity': ['clauses'],
    'solver-command-frames': ['solver-frames', 'solver-lifetime', 'solver-retirement'],
    'filesystem-custody': ['filesystem', 'filesystem-operations', 'filesystem-refresh', 'filesystem-regressions'],
}
PIPELINE = {'unit-metadata', 'source-and-class-proof', 'sealed-loader', 'constructor-and-scope',
            'artifact-profile-and-cache', 'contextual-pipeline-identity', 'contextual-analysis-reports',
            'execution-clause-identity'}
UNIVERSAL = ['fresh-source-free-load', 'new-project-packaged-macro', 'class-image-proof',
             'source-present-loader', 'tamper-before-initialization', 'missing-unit-before-initialization']
SDK_INITIALIZATION = {'unit-metadata', 'source-and-class-proof', 'preboot-identity',
                      'sealed-loader', 'constructor-and-scope', 'native-custody',
                      'contextual-pipeline-identity'}


def plan(boundaries=None):
    chosen = list(BOUNDARIES) if boundaries is None else list(boundaries)
    if not chosen or len(chosen) != len(set(chosen)) or set(chosen) - set(BOUNDARIES):
        raise ValueError('empty, duplicate or unknown sealed boundaries')
    selected = {group for boundary in chosen for group in BOUNDARIES[boundary]}
    groups = [{'id': name, 'tests': [{'path': path, 'assertions': count} for path, count in tests]}
              for name, (tests, _) in GROUPS.items() if name in selected]
    roots = list(dict.fromkeys(root for name, (_, roots) in GROUPS.items() if name in selected for root in roots))
    pipeline = bool(set(chosen) & PIPELINE)
    if pipeline:
        roots = list(dict.fromkeys(['compile.world', 'build', *roots]))
    sdk_initialization = bool(set(chosen) & SDK_INITIALIZATION)
    if sdk_initialization:
        # Generation preparation selects this fixed provider lazily to avoid
        # a require cycle. A Source-free initialization receiver needs its unit.
        roots = list(dict.fromkeys([*roots, 'proc.reg', 'reload.source-guard', 'reload', 'reload.binding']))
    return {'version': 1, 'mode': 'complete' if boundaries is None else 'focused',
            'boundaries': chosen, 'universal': UNIVERSAL, 'pipeline': pipeline, 'roots': roots,
            'sdk-initialization': sdk_initialization,
            'solver': pipeline or any(name.startswith('solver-') for name in selected),
            'groups': groups, 'assertions': sum(row['assertions'] for g in groups for row in g['tests'])}


def validate(plan, receipt):
    if (receipt.get('status') != 'passed' or receipt.get('source-free') is not True
            or receipt.get('boundaries') != plan['boundaries']
            or receipt.get('mode') != plan['mode'] or receipt.get('pipeline') != plan['pipeline']
            or receipt.get('sdk-initialization', False) != plan['sdk-initialization']):
        raise ValueError('wrong sealed selection or missing source-free receipt')
    expected = [(g['id'], row['path'], row['assertions']) for g in plan['groups'] for row in g['tests']]
    actual = receipt.get('files')
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValueError('missing or unexpected sealed file coverage')
    for row, (group, path, count) in zip(actual, expected):
        if (row.get('group') != group or row.get('path') != path or row.get('pass') != count
                or type(row.get('pass')) is not int
                or any(type(row.get(k)) is not int or row[k] != 0 for k in ['fail', 'error'])
                or type(row.get('tests')) is not int or row['tests'] <= 0):
            raise ValueError('failed, empty or incorrect sealed test coverage: ' + path)
    if receipt.get('assertions') != plan['assertions']:
        raise ValueError('incorrect sealed assertion total')


def validate_initialization(plan, receipt):
    if plan['sdk-initialization']:
        if (not isinstance(receipt, dict) or receipt.get('status') != 'passed'
                or receipt.get('fresh-receiver') is not True or receipt.get('source-free') is not True
                or type(receipt.get('sdk-source-compiles')) is not int or receipt['sdk-source-compiles'] != 0):
            raise ValueError('missing fresh Source-free SDK application initialization control')
    elif receipt is not None:
        raise ValueError('unexpected SDK application initialization scope')


def validate_universal(receipt):
    if (receipt.get('status') != 'passed' or receipt.get('source_free_sdk') is not True
            or receipt.get('tampering_refused_before_initialization') is not True
            or receipt.get('missing_unit_refused_before_initialization') is not True
            or receipt.get('sealed_source_consumers', {}).get('status') != 'passed'):
        raise ValueError('missing universal sealed integrity controls')
    consumer = receipt.get('consumer', {})
    if (consumer.get('status') != 'passed' or consumer.get('legacy-compiles') != 0
            or any(consumer.get(key) is not True for key in ['actual-sealed-image', 'class-image-proof',
                                                           'packaged-macro-new-project', 'sdk-source-absent'])):
        raise ValueError('missing universal fresh source-free consumer proof')
