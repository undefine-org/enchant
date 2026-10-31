"""Cause-specific controls derived from current production files; no BEAM starts.

Mutants are private Python namespaces or private shell copies. SDK and installed
host code are never edited. Passing these checks does not claim hosted Actions,
macOS/arm execution, browser-service support, or historical closure by itself.
"""
from __future__ import annotations
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OBSERVATIONS = []


def load(relative, before=None, after=None):
    path = ROOT / relative
    source = path.read_text()
    original = hashlib.sha256(source.encode()).hexdigest()
    if before is not None:
        if source.count(before) != 1:
            raise ValueError('non-unique actual-producer mutation: ' + relative)
        source = source.replace(before, after)
    namespace = {'__file__': str(path), '__name__': 'qualification_private_probe'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace, original


def observe(case, **data):
    OBSERVATIONS.append({'case': case, **data})


def block(source, job):
    lines = source.splitlines()
    start = lines.index('  ' + job + ':')
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r'^  [A-Za-z0-9_-]+:', lines[i])), len(lines))
    return '\n'.join(lines[start:end])


def step(source, name):
    lines = source.splitlines()
    start = lines.index('      - name: ' + name)
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith('      - ')), len(lines))
    return '\n'.join(lines[start:end])


def literal_paths(source, name):
    selected = step(source, name).splitlines()
    index = selected.index('          path: |')
    result = []
    for line in selected[index + 1:]:
        if not line.startswith('            '):
            break
        result.append(line.strip())
    return result


def workflow_expr(expression, context):
    # Independent interpreter for the actual small expression grammar used by
    # concurrency. No Python eval, commands, variable expansion or Source eval.
    tokens = re.findall(r"'[^']*'|==|&&|\|\||[A-Za-z_][A-Za-z0-9_.]*", expression)
    cursor = 0
    def atom():
        nonlocal cursor
        token = tokens[cursor]; cursor += 1
        if token.startswith("'"):
            return token[1:-1]
        value = context
        for name in token.split('.'):
            value = value[name]
        return value
    def equality():
        nonlocal cursor
        value = atom()
        if cursor < len(tokens) and tokens[cursor] == '==':
            cursor += 1; value = value == atom()
        return value
    def conjunction():
        nonlocal cursor
        value = equality()
        while cursor < len(tokens) and tokens[cursor] == '&&':
            cursor += 1; rhs = equality(); value = rhs if value else value
        return value
    def disjunction():
        nonlocal cursor
        value = conjunction()
        while cursor < len(tokens) and tokens[cursor] == '||':
            cursor += 1; rhs = conjunction(); value = value if value else rhs
        return value
    result = disjunction()
    if cursor != len(tokens):
        raise ValueError('unsupported workflow expression')
    return result


def concurrency(source, draft, dispatch=False):
    group = next(line.strip().removeprefix('group: ') for line in source.splitlines()
                 if line.startswith('  group: ci-'))
    context = {'github': {'ref_name': 'same-commit',
        'event_name': 'workflow_dispatch' if dispatch else 'pull_request',
        'event': {'pull_request': {'head': {'ref': 'same-commit'}, 'draft': draft}}},
        'inputs': {'runtime_run': ''}}
    return re.sub(r'\$\{\{(.*?)\}\}', lambda m: str(workflow_expr(m[1], context)), group)


class QualificationCausal(unittest.TestCase):
    def test_E11_actual_restore_policy_cannot_overwrite_new_native(self):
        source = (ROOT / '.github/workflows/ci.yml').read_text()
        before = '          path: |\n            ~/.cache/beam_lisp\n          key: ci-'
        self.assertEqual(1, source.count(before))
        mutant = source.replace(before, before.replace('\n          key:', '\n            priv/native\n          key:'))
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outcomes = []
            for index, policy in enumerate([source, mutant]):
                home, checkout, saved, restored = [base / str(index) / name for name in ['home','checkout','saved','restored']]
                old = checkout / 'priv/native/lazy_memo.so'; old.parent.mkdir(parents=True); old.write_bytes(b'old native product')
                cache = home / '.cache/beam_lisp'; cache.mkdir(parents=True); (cache/'addressed').write_bytes(b'old addressed product')
                archive = base / ('restore-' + str(index) + '.tar.gz')
                paths = literal_paths(policy, 'Restore the content-addressed native and library store')
                with tarfile.open(archive, 'w:gz') as out:
                    for name in paths:
                        source_path = home / name[2:] if name.startswith('~/') else checkout / name
                        arcname = 'home/' + name[2:] if name.startswith('~/') else 'checkout/' + name
                        out.add(source_path, arcname=arcname)
                target = restored / 'checkout/priv/native/lazy_memo.so'; target.parent.mkdir(parents=True); target.write_bytes(b'new native product')
                with tarfile.open(archive) as inp: inp.extractall(restored, filter='data')
                outcomes.append(target.read_bytes())
            self.assertEqual([b'new native product', b'old native product'], outcomes)
        observe('E11', producer='.github/workflows/ci.yml', before=before,
                after=before.replace('\n          key:', '\n            priv/native\n          key:'),
                current_native_preserved=True, mutant_overwrites_native=True,
                scope='Actual workflow cache-path policy and real archive restore order; opaque product bytes, no native ABI execution')

    def test_E52_actual_concurrency_and_archive_directory_mutations(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        before = "${{ github.event_name == 'pull_request' && github.event.pull_request.draft && 'quick' || 'full' }}"
        self.assertEqual(1, workflow.count(before))
        mutant = workflow.replace(before, "${{ 'full' }}")
        self.assertNotEqual(concurrency(workflow, True), concurrency(workflow, False, True))
        self.assertEqual(concurrency(mutant, True), concurrency(mutant, False, True))
        normal, digest = load('scripts/package-ci-runtime.py')
        broken, _ = load('scripts/package-ci-runtime.py', 'arcname=relative)', 'arcname="ci-runtime/" + relative)')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ['build/active.beam','priv/native/native.so','priv/z3/bin/z3','tooling/drop/target/release/drop-launcher']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
            candidate=root/'candidate';candidate.write_bytes(b'candidate');candidate.chmod(0o755)
            restored=[]
            for name, package in [('current',normal),('mutant',broken)]:
                archive=root/(name+'.tar.gz');package['package_runtime'](root,archive,candidate)
                with tarfile.open(archive) as inp:inp.extractall(root/name,filter='data')
                restored.append((root/name/'build/active.beam').is_file())
            self.assertEqual([True,False],restored)
        observe('E52', producer='.github/workflows/ci.yml',before=before,after="${{ 'full' }}",
                current_quick_full_distinct=True,mutant_same_slot=True,
                archive_producer='scripts/package-ci-runtime.py',archive_sha256=digest,
                directory_boundary_current=True,directory_boundary_mutant=False)

    def test_E82_actual_identity_filter_rejects_changed_candidate_and_inputs(self):
        before='if row.get("identity") == identity and "file" in row:'
        normal,digest=load('scripts/qualify-candidate.py')
        mutant,_=load('scripts/qualify-candidate.py',before,'if "file" in row:')
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=base/'checkout';root.mkdir();subprocess.run(['git','init','-q',str(root)],check=True)
            candidate=base/'candidate';candidate.write_bytes(b'actual candidate input')
            source=root/'compiler.bl';source.write_bytes(b'compiler source')
            floor=root/'floor.beam';floor.write_bytes(b'floor input')
            test=root/'fixture_test.bl';test.write_bytes(b'test input')
            identity={'candidate':normal['digest'](candidate),'source':normal['source_digest'](root)}
            receipts=base/'receipt';receipts.write_text(json.dumps({'file':'fixture_test.bl','identity':identity,'fail':0,'error':0})+'\n')
            self.assertEqual(identity['source'],normal['source_digest'](root))
            self.assertEqual({'fixture_test.bl'},set(normal['completed'](receipts,identity)))
            outcomes=[]
            for path in [candidate,source,floor,test]:
                original=path.read_bytes();path.write_bytes(original+b' changed')
                current={'candidate':normal['digest'](candidate),'source':normal['source_digest'](root)}
                outcomes.append([bool(normal['completed'](receipts,current)),bool(mutant['completed'](receipts,current))])
                path.write_bytes(original)
            self.assertEqual([[False,True]]*4,outcomes)
        observe('E82',producer='scripts/qualify-candidate.py',producer_sha256=digest,
                before=before,after='if "file" in row:',variants=['candidate','compiler Source','floor','test Source'],
                current_refuses_all=True,mutant_accepts_all=True,scope='Actual source digest and receipt consumer; receipt is untrusted test input, no SDK execution claim')

    def test_E83_dispatch_shell_uses_real_merge_base_and_keeps_new_blob_guard(self):
        workflow=(ROOT/'.github/workflows/ci.yml').read_text()
        before='if [ "$PUBLIC_EVIDENCE_EVENT" = workflow_dispatch ] && [ -z "$PUBLIC_EVIDENCE_BASE" ]; then'
        self.assertEqual(1,workflow.count(before))
        def shell(source):
            lines=step(source,'Inspect every new commit blob before native builds').splitlines()
            i=lines.index('        run: |')
            return '\n'.join(line[10:] for line in lines[i+1:] if line.startswith('          '))
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);origin=base/'origin.git';root=base/'checkout'
            subprocess.run(['git','init','--bare','-q',str(origin)],check=True)
            subprocess.run(['git','init','-q',str(root)],check=True)
            def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.PIPE).strip()
            git('config','user.name','Synthetic proof');git('config','user.email','proof@example.invalid')
            (root/'scripts').mkdir();shutil.copy2(ROOT/'scripts/check-public-evidence.py',root/'scripts/check-public-evidence.py')
            (root/'public.bl').write_text('(ns public.dispatch-proof)\n')
            def commit(name):git('add','--all');git('commit','-qm',name)
            commit('public baseline')
            # Synthetic negative Source only, matching the publication gate's
            # existing fixture vocabulary; never product or private app code.
            (root/'old-private-fixture.bl').write_text('(ns foundry.synthetic-dispatch-proof)\n')
            commit('synthetic historical prohibited namespace')
            (root/'old-private-fixture.bl').unlink();commit('sanitized baseline')
            git('branch','-M','main');git('remote','add','origin',str(origin));git('push','-q','origin','main')
            git('checkout','-qb','candidate');(root/'public.bl').write_text('(ns public.dispatch-proof)\n(def answer 42)\n');commit('new public candidate')
            env=dict(os.environ,PUBLIC_EVIDENCE_BASE='',PUBLIC_EVIDENCE_EVENT='workflow_dispatch',PUBLIC_EVIDENCE_DEFAULT_BRANCH='main')
            def execute(source):return subprocess.run(['bash','-c',shell(source)],cwd=root,env=env,text=True,capture_output=True,timeout=30)
            positive=execute(workflow);self.assertEqual(0,positive.returncode,positive.stderr)
            mutant=execute(workflow.replace(before,'if false; then'));self.assertNotEqual(0,mutant.returncode);self.assertIn('private Source unit declaration',mutant.stderr)
            (root/'new-private-fixture.bl').write_text('(ns foundry.synthetic-new-dispatch-proof)\n');commit('new synthetic prohibited namespace')
            refused=execute(workflow);self.assertNotEqual(0,refused.returncode);self.assertIn('private Source unit declaration',refused.stderr)
        observe('E83',producer='.github/workflows/ci.yml',before=before,after='if false; then',
                actual_dispatch_shell=True,old_sanitized_history_excluded=True,mutant_scans_old_history=True,new_prohibited_blob_still_refused=True)

    def test_E84_actual_release_waits_for_complete_reused_linux_inventory(self):
        source=(ROOT/'.github/workflows/release.yml').read_text()
        before='    needs: [linux, linux-inventory]'
        self.assertEqual(1,source.count(before))
        mutant=source.replace(before,'    needs: linux')
        # This uses the literal GitHub needs graph: the historical mutation
        # permits expensive platform jobs once Linux smoke passes, even when
        # the complete inventory is failed or still in progress.
        def admitted(workflow,inventory):
            text=block(workflow,'build')
            needs=next(x.strip().removeprefix('needs: ') for x in text.splitlines() if x.startswith('    needs:'))
            names=[x.strip() for x in needs.strip('[]').split(',')]
            states={'linux':'success','linux-inventory':inventory}
            return all(states[n]=='success' for n in names)
        self.assertEqual([False,False,True],[admitted(source,s) for s in ['failure','in_progress','success']])
        self.assertEqual([True,True,True],[admitted(mutant,s) for s in ['failure','in_progress','success']])
        inventory=block(source,'linux-inventory')
        self.assertIn('name: bl-linux-x86_64',inventory)
        self.assertIn('sha256sum -c bl-linux-x86_64.sha256',inventory)
        self.assertIn('"$GITHUB_WORKSPACE/.bl/ci-candidate"',inventory)
        self.assertIn('python3 scripts/ci-test-shard.py --index ${{ matrix.shard }} --count 4',inventory)
        self.assertNotRegex(inventory,r'run:.*(?:self-build|prepare-checkout-sdk|nix build)')
        shard,_=load('scripts/ci-test-shard.py');groups=shard['partitions'](ROOT,4)
        expected={str(p.relative_to(ROOT)) for p in (ROOT/'test').rglob('*') if p.is_file() and p.name.endswith(('_test.bl','_test.exs')) and not any(n.startswith('.') for n in p.relative_to(ROOT/'test').parts[:-1])}
        self.assertEqual(expected,set(sum(groups,[])));self.assertEqual(len(expected),len(sum(groups,[])))
        observe('E84',producer='.github/workflows/release.yml',before=before,after='    needs: linux',
                current_rejects_incomplete_inventory=True,mutant_starts_other_platforms=True,
                inventory_files=len(expected),shards=4,reuses_checksum_verified_candidate=True,
                scope='Actual workflow dependency and complete partition inventory; hosted Actions execution and supported cross-platform production remain unverified')

    def test_E83_actual_preparation_forwards_host_nix_policy(self):
        # Execute private copies of both actual shell entrypoints through an
        # external-command recorder. Stop at the first Nix boundary; no output,
        # SDK handle, ownership certificate, or successful build is fabricated.
        observations=[]
        for relative,anchor in [('scripts/prepare-checkout-platform','--out-link "$retained" --cores 1'),
                                ('scripts/prepare-checkout-sdk','--out-link "$job/source-retained" --option timeout')]:
            source=(ROOT/relative).read_text();self.assertEqual(1,source.count(anchor))
            mutant=source.replace(anchor,anchor.replace(' --cores',' --max-jobs 0 --cores').replace(' --option',' --max-jobs 0 --option'))
            records=[]
            for variant,text in [('current',source),('mutant',mutant)]:
                with tempfile.TemporaryDirectory() as temporary:
                    root=Path(temporary)
                    for directory in ['scripts','nix','native','tooling/drop','bin']:(root/directory).mkdir(parents=True,exist_ok=True)
                    for name in ['flake.lock','flake.nix']:(root/name).write_text('fixture')
                    script=root/relative;script.write_text(text);script.chmod(0o755)
                    shutil.copy2(ROOT/'scripts/sdk-inputs',root/'scripts/sdk-inputs')
                    policy={'version':1,'roots':['native'],'excluded':['native/unused'],'reserved':['.git','.bl'],'targetRoots':['native'],'limits':{'entries':1000,'fileBytes':1000000,'totalBytes':1000000,'depth':20}}
                    (root/'nix/engine-inputs.json').write_text(json.dumps(policy))
                    observer=root/'argv.json'
                    nix=root/'bin/nix-build';nix.write_text('#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ["PROBE_ARGV"]).write_text(json.dumps({"argv":sys.argv[1:],"NIX_CONFIG":os.environ.get("NIX_CONFIG")}))\nraise SystemExit(71)\n');nix.chmod(0o755)
                    manager=root/'bin/systemd-run';manager.write_text('#!/usr/bin/env python3\nimport os,sys\na=sys.argv[1:]\ni=next(i for i,x in enumerate(a) if not x.startswith("--"))\nos.execvp(a[i],a[i:])\n');manager.chmod(0o755)
                    env=dict(os.environ,PATH=str(root/'bin')+os.pathsep+os.environ['PATH'],PROBE_ARGV=str(observer),NIX_CONFIG='max-jobs = 2\nbuilders =\n')
                    result=subprocess.run([str(script)],cwd=root,env=env,text=True,capture_output=True,timeout=20)
                    self.assertNotEqual(0,result.returncode);self.assertTrue(observer.exists(),result.stderr)
                    record=json.loads(observer.read_text());self.assertEqual(env['NIX_CONFIG'],record['NIX_CONFIG'])
                    records.append(record['argv'])
            self.assertNotIn('--max-jobs',records[0]);self.assertEqual('0',records[1][records[1].index('--max-jobs')+1])
            observations.append({'producer':relative,'before':anchor,'after':anchor.replace(' --cores',' --max-jobs 0 --cores').replace(' --option',' --max-jobs 0 --option'),'current':records[0],'mutant':records[1]})
        observe('E83',preparation_argv_controls=observations,current_respects_host_policy=True,mutant_forces_no_local_workers=True,
                scope='Actual shell entrypoints and recorded external Nix argv; intentionally stop before production, hosted cold provisioning remains unexecuted')


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(QualificationCausal)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print('HISTORY_QUALIFICATION_CAUSAL '+json.dumps({'passed':result.wasSuccessful(),'tests_run':result.testsRun,'observations':OBSERVATIONS},sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
