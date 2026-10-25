import experiment as e
import json
import os
import subprocess as sp
import time

e.results = json.loads((e.ROOT/'results.json').read_text())

def supervisor():
    unit = 'bl-nix-prototype-orphan-'+str(os.getpid())
    marker = e.ROOT/'systemd-child-pid'
    marker.unlink(missing_ok=True)
    # setsid escapes the parent's process group. The cgroup must still own it.
    script = 'setsid /bin/sh -c \'echo $$ > "$1"; exec sleep 30\' child "$1" & wait'
    r = e.run(['systemd-run','--user','--expand-environment=no','--unit='+unit,'--property=MemoryMax=64M',
               '--property=RuntimeMaxSec=15','--property=KillMode=control-group',
               '--setenv=PATH=/run/current-system/sw/bin','--','/bin/sh','-c',script,'parent',str(marker)])
    assert r.returncode == 0, r.stderr
    try:
        deadline = time.monotonic()+5
        while not marker.exists():
            assert time.monotonic() < deadline
            time.sleep(.03)
        pid = int(marker.read_text())
        pidfd = os.pidfd_open(pid)
        try:
            import select
            assert not select.select([pidfd],[],[],0)[0]
            kill = e.run(['systemctl','--user','kill','--kill-whom=main','--signal=KILL',unit])
            assert kill.returncode == 0, kill.stderr
            assert select.select([pidfd],[],[],5)[0], 'setsid child survived main death'
        finally:
            os.close(pidfd)
        return dict(setsid_child_terminated=True, policy='main-exit + KillMode=control-group')
    finally:
        e.run(['systemctl','--user','stop',unit])
        e.run(['systemctl','--user','reset-failed',unit])

def isolation():
    (e.ROOT/'host-canary').write_text('must not be visible to builder\n')
    out = e.build(mode='isolation')
    e.validate(out,42)
    return dict(host_canary_hidden=True, output=str(out))

def refusal():
    bad = e.run(e.BASE+['--argstr','answer','not an integer'])
    unknown = e.run(['nix','build','--no-link','--offline','--file',str(e.ROOT/'request.nix'), '--argstr','requestJson',
                     '{"answer":42,"shell":"unexpected"}'])
    assert bad.returncode != 0 and unknown.returncode != 0
    return dict(wrong_type_refused=True, unknown_request_field_refused=True)

for name, fn in [('systemd-setsid-descendant-cleanup',supervisor),
                 ('host-filesystem-isolation',isolation), ('request-contract-refusal',refusal)]:
    e.case(name,fn)
raise SystemExit(any(r['status'] != 'passed' for r in e.results))
