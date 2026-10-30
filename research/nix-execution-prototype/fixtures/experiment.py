"""Isolated Nix artifact backend experiment; no implementation-tree mutation."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess as sp
import time

ROOT = Path(__file__).resolve().parent
BUSY = '/nix/store/r6zw8gd10c7qv9sifzg4r7h1s5qmrxjp-busybox-1.37.0'
RUST = '/nix/store/53lvgpxsb3b9ghkgb4v0jra6zzlnyw8n-rustc-1.98.1'
CARGO = '/nix/store/gmgfpzc0w2pgby0lmq9r88m39albiyfw-cargo-1.98.1'
CC = '/nix/store/788mx070y81zjlg5ipcl0cra3afviw9k-gcc-wrapper-15.2.0'
BASE = ['nix', 'build', '--file', str(ROOT/'artifact.nix'), '--json', '--no-link',
        '--offline', '--max-jobs', '1', '--cores', '1', '--option', 'builders', '',
        '--option', 'timeout', '35']
results = []

def run(argv, **kw):
    return sp.run(argv, text=True, capture_output=True, timeout=65, **kw)

def case(name, fn):
    start = time.monotonic()
    try:
        detail = fn()
        results.append(dict(name=name, status='passed', seconds=round(time.monotonic()-start, 3), detail=detail))
    except Exception as exc:
        results.append(dict(name=name, status='failed', seconds=round(time.monotonic()-start, 3), error=str(exc)))
    (ROOT/'results.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(results[-1]), flush=True)

def command(answer=42, mode='normal', token='stable'):
    return BASE + ['--arg', 'answer', str(answer), '--argstr', 'mode', mode, '--argstr', 'token', token]

def build(**kw):
    r = run(command(**kw))
    assert r.returncode == 0, r.stderr
    return Path(json.loads(r.stdout)[0]['outputs']['out'])

def validate(out, answer):
    m = json.loads((out/'manifest.json').read_text())
    assert m['answer'] == answer and m['schema'] == 1
    lib = ctypes.CDLL(str(out/'libprobe.so'))
    assert lib.answer() == answer
    return hashlib.sha256((out/'libprobe.so').read_bytes()).hexdigest()

def identity():
    timings = {}
    start = time.monotonic()
    a = build()
    timings['initial_request'] = round(time.monotonic()-start,3)
    digest = validate(a, 42)
    start = time.monotonic()
    b = build()
    timings['warm_request'] = round(time.monotonic()-start,3)
    assert a == b
    c = build(answer=43)
    assert c != a and validate(c, 43) != digest
    return dict(first=str(a), warm=str(b), changed=str(c), sha256=digest, request_seconds=timings,
                initial_may_be_cached=True)

def concurrent():
    args = command(token='concurrent-'+str(os.getpid()))
    ps = [sp.Popen(args, text=True, stdout=sp.PIPE, stderr=sp.PIPE) for _ in range(2)]
    outs = []
    try:
        for p in ps:
            stdout, stderr = p.communicate(timeout=60)
            assert p.returncode == 0, stderr
            outs.append(json.loads(stdout)[0]['outputs']['out'])
        assert outs[0] == outs[1]
        validate(Path(outs[0]), 42)
        log = run(['nix', 'log', '--file', str(ROOT/'artifact.nix'), '--argstr', 'token', 'concurrent-'+str(os.getpid())])
        assert log.returncode == 0, log.stderr
        assert log.stdout.count('PROTOTYPE_BUILD_STARTED') == 1, log.stdout
        return dict(outputs=outs, build_start_count=1)
    finally:
        for p in ps:
            if p.poll() is None: p.kill(); p.wait()

def requester_death():
    token = 'death-'+str(os.getpid())
    args = command(mode='slow', token=token) + ['--print-build-logs']
    logpath = ROOT/'requester.log'
    with logpath.open('w') as log:
        p = sp.Popen(args, stdout=log, stderr=log, text=True)
        try:
            deadline = time.monotonic()+25
            while 'PROTOTYPE_BUILD_STARTED' not in logpath.read_text():
                assert p.poll() is None, logpath.read_text()
                assert time.monotonic() < deadline, 'builder did not start'
                time.sleep(.05)
            p.kill(); p.wait(timeout=5)
        finally:
            if p.poll() is None: p.kill(); p.wait()
    out = build(mode='slow', token=token)
    return dict(requester_killed=True, replacement_valid=bool(validate(out,42)), output=str(out))

def descendant():
    out = build(mode='descendant', token='descendant-'+str(os.getpid()))
    validate(out, 42)
    assert (out/'child-ready').read_text().strip() == 'ready'
    before = sorted(p.name for p in out.iterdir())
    time.sleep(3)
    assert not (out/'late-write').exists(), 'orphan mutated published output'
    assert before == sorted(p.name for p in out.iterdir())
    return dict(output=str(out), no_late_write=True, child_dropped_inherited_descriptors=True)

def descendant_negative():
    out = ROOT/'negative-control'
    out.mkdir(exist_ok=True)
    late = out/'late-write'
    late.unlink(missing_ok=True)
    r = run(['/bin/sh','-c', '(exec 3>&- 4>&- 5>&- 6>&- 7>&- 8>&- 9>&-; sleep 2; echo escaped > "$out/late-write") </dev/null >/dev/null 2>&1 &',], env={**os.environ,'out':str(out)})
    assert r.returncode == 0, r.stderr
    time.sleep(3)
    assert late.read_text().strip() == 'escaped'
    return dict(unsupervised_child_wrote_after_parent_exit=True)

def failure():
    r = run(command(mode='fail', token='failure-'+str(os.getpid())))
    assert r.returncode != 0
    good = build()
    validate(good,42)
    return dict(failure_exit=r.returncode, prior_product_unchanged=str(good))

def rooting():
    out = build()
    root = ROOT/'retained-result'
    r = run(['nix-store','--add-root',str(root),'--indirect','--realise',str(out)])
    assert r.returncode == 0, r.stderr
    roots = run(['nix-store','--query','--roots',str(out)])
    assert str(root) in roots.stdout, roots.stdout+roots.stderr
    root.unlink()
    after = run(['nix-store','--query','--roots',str(out)])
    assert str(root) not in after.stdout
    return dict(root_registered=True, root_removed=True, global_gc_run=False)

if __name__ == '__main__':
    for name, fn in [('identity-and-warm-reuse',identity), ('concurrent-deduplication',concurrent),
                     ('requester-death-recovery',requester_death), ('descriptor-filtering-descendant',descendant),
                     ('unsandboxed-descendant-negative',descendant_negative),
                     ('failed-build-preserves-good-product',failure), ('explicit-retention',rooting)]:
        case(name,fn)
    raise SystemExit(any(r['status'] != 'passed' for r in results))
