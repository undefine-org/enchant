"""Explicit sealed coverage; focused receipts never certify omitted profiles."""

GROUPS = {
    "imports": ([('test/bl/contextual_import_test.bl', 25), ('test/bl/contextual_phase_value_test.bl', 15)], ['compile.world']),
    "compiler-bootstrap-order": ([('test/bl/compiler_bootstrap_order_test.bl', 4)], []),
    "compiler-entry": ([('test/bl/compiler_entry_context_test.bl', 106), ('test/bl/namespace_header_test.bl', 14), ('test/bl/compiler_contextual_test.bl', 27), ('test/bl/generation_semantics_test.bl', 18), ('test/bl/compiler_lexical_consumers_test.bl', 13)], ['expand', 'env', 'connector.google.gdrive', 'connector.microsoft.graph', 'bl.cli', 'bl.doc', 'bl.doc.html', 'bl.profile']),
    "namespace-require": ([('test/bl/namespace_require_grammar_test.bl', 62), ('test/bl/namespace_clause_grammar_test.bl', 47)], ['js.build']),
    "namespace-header-imports": ([('test/bl/contextual_namespace_require_test.bl', 33), ('test/bl/contextual_phase_capture_test.bl', 9), ('test/bl/contextual_library_test.bl', 16), ('test/bl/contextual_library_compat_test.bl', 10), ('test/bl/contextual_revision_identity_test.bl', 28), ('test/bl/contextual_binding_test.bl', 141), ('test/bl/contextual_library_admission_test.bl', 49), ('test/bl/contextual_rename_test.bl', 22), ('test/bl/contextual_query_test.bl', 18)], ['compile.world', 'codebase.refactor']),
    "namespace-initialization": ([('test/bl/contextual_namespace_initialization_test.bl', 34), ('test/bl/contextual_runtime_value_test.bl', 32)], ['compile.world']),
    "declaration-header": ([('test/bl/contextual_declaration_header_test.bl', 24), ('test/bl/js_declaration_header_test.bl', 14)], ['expand-source', 'expand', 'js.build']),
    "factory-admission": ([('test/bl/sdk_lambda_origin_test.bl', 2), ('test/bl/contextual_factory_admission_test.bl', 41), ('test/bl/contextual_loader_instance_test.bl', 20), ('test/bl/contextual_loader_failure_test.bl', 29), ('test/bl/contextual_parent_admission_test.bl', 16), ('test/bl/contextual_allocation_custody_test.bl', 25), ('test/bl/contextual_profile_recovery_test.bl', 11), ('test/bl/contextual_realm_retirement_test.bl', 32), ('test/bl/contextual_session_retirement_test.bl', 43), ('test/bl/realm_code_lifetime_test.bl', 32), ('test/bl/closed_etf_test.bl', 150), ('test/bl/data_first_order_test.bl', 105), ('test/bl/contextual_unit_recipe_test.bl', 95), ('test/bl/reload/generation_preparation_state_test.bl', 25), ('test/bl/native_source_instance_test.bl', 23), ('test/bl/contextual_instance_factory_test.bl', 27), ('test/bl/contextual_instance_owner_test.bl', 68)], ['compile.world', 'system.phase', 'codebase.phase', 'reload.generation', 'vm.core', 'vm.manager', 'vm.realm', 'vm.session', 'vm.client', 'test.support.source-fixtures']),
    "lexical-scope": ([('test/bl/contextual_lexical_scope_test.bl', 103), ('test/bl/contextual_try_test.bl', 56), ('test/bl/lower_try_operand_test.bl', 9), ('test/bl/core_aot_test.bl', 16)], ['expand', 'codebase.refactor', 'java.manifest']),
    "namespace-exports": ([('test/bl/contextual_namespace_exports_test.bl', 48)], ['compile.world', 'system.phase', 'codebase.phase']),
    "binding-reference": ([('test/bl/contextual_binding_anf_test.bl', 112)], ['expand', 'system.ir', 'codebase.phase', 'js.emit']),
    "physical-declaration": ([('test/bl/compiler_physical_declaration_test.bl', 24)], []),
    "boot-isolation": ([('test/bl/contextual_boot_isolation_test.bl', 1)], []),
    "canonical-calls": ([('test/bl/canonical_call_consumers_test.bl', 18), ('test/bl/reload/registration_test.bl', 23), ('test/bl/reload/pattern_admission_test.bl', 16), ('test/bl/reload/source_producer_test.bl', 29), ('test/bl/reload/reconcile_residual_structural_test.bl', 43), ('test/bl/system/linear_call_view_test.bl', 16), ('test/bl/optimizer_canonical_invocation_test.bl', 4), ('test/bl/system/analysis_alias_context_test.bl', 4), ('test/bl/reload/initializer_call_view_test.bl', 31)], ['reload.initializer', 'optimize', 'system.linear', 'js.actor', 'system.smt', 'termination', 'reload.reconcile-recipe', 'reload.reconcile-values', 'reload.registration']),
    "pattern-operands": ([('test/bl/system/ir_test.bl', 19), ('test/bl/system/anf_arity_test.bl', 78), ('test/bl/system/suspension_test.bl', 13), ('test/bl/system/footprint_anf_test.bl', 66), ('test/bl/reload/closed_function_test.bl', 14)], ['system.arity.anf', 'system.suspension', 'system.footprint', 'reload.closed-function']),
    "lsp-calls": ([('test/bl/system/lsp_test.bl', 59), ('test/bl/system/lsp_clause_test.bl', 16)], ['lsp']),
    "typed-analysis": ([('test/bl/typed_analysis_boundary_test.bl', 12)], ['typed']),
    "ownership": ([('test/bl/system/ownership_test.bl', 138)], ['compile.world']),
    "ownership-calls": ([('test/bl/system/ownership_calls_test.bl', 123)], ['compile.world']),
    "native-outcomes": ([('test/bl/system/ownership_native_test.bl', 207)], ['system.ownership']),
    "vectors": ([('test/bl/vector_get_default_test.bl', 65)], []),
    "handoffs": ([('test/bl/native_execution_handoff_test.bl', 46)], []),
    "loops": ([('test/bl/system/ownership_loops_test.bl', 77)], ['compile.world']),
    "af": ([('test/bl/system/af_worklist_test.bl', 75)], ['system.gfp']),
    "capacity": ([('test/bl/proc_callback_capacity_test.bl', 101)], ['proc.callback', 'system.ownership']),
    "supervisor-context": ([('test/bl/proc/supervisor_context_test.bl', 32), ('test/bl/sdk_runtime_owner_context_test.bl', 7), ('test/bl/native_server_initializer_extent_test.bl', 19), ('test/bl/system/evidence_test.bl', 18)], ['data.bounded-cache', 'data.cache-pool', 'system.evidence', 'proc.task']),
    "generation-retirement": ([('test/bl/native_execution_scoped_retirement_test.bl', 32), ('test/bl/reload/preparation_owner_origin_test.bl', 29), ('test/bl/native_parent_start_lifetime_test.bl', 6)], ['reload.generation', 'reload.execution', 'vm.manager']),
    "message-context": ([('test/bl/native_execution_callback_analysis_test.bl', 16)], ['proc.message-domain', 'test.support.source-fixtures']),
    "returns": ([('test/bl/server_return_model_test.bl', 10)], []),
    "clauses": ([('test/bl/execution_clause_identity_test.bl', 5), ('test/bl/execution_entry_producer_test.bl', 47)], []),
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
    'unit-metadata': ['namespace-header-imports', 'namespace-require', 'lexical-scope', 'factory-admission', 'clauses'], 'source-and-class-proof': ['handoffs', 'capacity', 'pattern-operands'],
    'preboot-identity': ['namespace-header-imports', 'namespace-require', 'lexical-scope', 'compiler-bootstrap-order', 'factory-admission', 'clauses', 'filesystem', 'boot-isolation', 'physical-declaration'], 'sealed-loader': ['factory-admission', ],
    'constructor-and-scope': ['namespace-header-imports', 'namespace-require', 'lexical-scope', 'compiler-bootstrap-order', 'factory-admission', 'namespace-exports', 'imports', 'compiler-entry', 'namespace-initialization', 'declaration-header', 'physical-declaration', 'binding-reference', 'native-outcomes', 'constructor-calls'], 'artifact-profile-and-cache': ['namespace-header-imports', 'namespace-require', 'factory-admission', 'namespace-exports', 'imports'],
    'native-custody': ['pattern-operands', 'canonical-calls', 'native-outcomes', 'handoffs', 'capacity', 'supervisor-context', 'generation-retirement', 'message-context'],
    'record-representation': ['factory-admission', 'returns'], 'contextual-pipeline-identity': ['namespace-header-imports', 'namespace-require', 'compiler-bootstrap-order', 'factory-admission', 'namespace-exports', 'imports', 'compiler-entry', 'namespace-initialization', 'declaration-header', 'physical-declaration', 'binding-reference', 'clauses'],
    'contextual-analysis-reports': ['namespace-header-imports', 'namespace-require', 'lexical-scope', 'pattern-operands', 'canonical-calls', 'lsp-calls', 'typed-analysis', 'namespace-exports', 'binding-reference', 'ownership', 'ownership-calls', 'native-outcomes', 'loops', 'af'],
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
