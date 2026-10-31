"""Extra qualification controls that do not start BEAM or compile anything."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
OBSERVATIONS=[]

def source_probe(relative,before=None,after=None):
 p=ROOT/relative;source=p.read_text();digest=hashlib.sha256(source.encode()).hexdigest()
 if before is not None:
  if source.count(before)!=1:raise ValueError('non-unique producer mutation')
  source=source.replace(before,after)
 ns={'__file__':str(p),'__name__':'qualification_extra_private_probe'}
 exec(compile(source,str(p),'exec'),ns)
 return ns,digest

class QualificationExtra(unittest.TestCase):
 def test_E42_actual_memory_collection_counts_direct_vms_swap_and_total(self):
  normal,digest=source_probe('scripts/bl-mem')
  before=' or runtime_code_path(argv)\n                     or immutable_boot_index(argv) is not None'
  missed,_=source_probe('scripts/bl-mem',before,'')
  total_before='"total_kb": st["VmRSS"] + st["VmSwap"]'
  no_swap,_=source_probe('scripts/bl-mem',total_before,'"total_kb": st["VmRSS"]')
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary)
   for pid,status in [('101','VmRSS: 1024 kB\nVmSwap: 2048 kB\nVmHWM: 4096 kB\n'),
                      ('102','VmRSS: 4096 kB\nVmSwap: 1048576 kB\nVmHWM: 8192 kB\n')]:
    (root/pid).mkdir();(root/pid/'status').write_text(status);(root/pid/'smaps_rollup').write_text('Pss: 512 kB\nAnonymous: 256 kB\n')
   commands={'101':['/erts/bin/beam.smp','-e','BeamLisp.Launcher.main()','--','run','one.bl'],
             '102':['/erts/bin/beam.smp','-pa','/candidate/lib/beam_lisp-0.1.0/ebin','driver.exs'],
             '103':['bash','-c','elixir -e BeamLisp.Launcher.main()']}
   def collect(ns):
    kv=ns['kv_kb'];ns['kv_kb']=lambda path,keys:kv(root/Path(path).parts[-2]/Path(path).name,keys)
    ns['uptime_s']=lambda:10000;ns['start_age_s']=lambda pid,boot:7200;ns['cmdline']=lambda pid:commands[str(pid)]
    with patch.object(ns['os'],'listdir',return_value=['101','102','103','not-a-pid']), \
         patch.object(ns['os'],'readlink',side_effect=lambda path:'/usr/bin/bash' if '/103/' in path else '/erts/bin/beam.smp' if path.endswith('/exe') else '/actual/cwd'):
     return ns['collect']()
   rows=collect(normal);omitted=collect(missed);undercharged=collect(no_swap)
   self.assertEqual([102,101],[r['pid'] for r in rows])
   self.assertEqual(1055744,sum(r['total_kb'] for r in rows))
   self.assertEqual(1050624,sum(r['swap_kb'] for r in rows))
   self.assertEqual([101],[r['pid'] for r in omitted])
   self.assertFalse(any(r['stale'] for r in undercharged));self.assertTrue(rows[0]['stale'])
   self.assertEqual(5120,sum(r['total_kb'] for r in undercharged))
  OBSERVATIONS.append({'case':'E42','producer':'scripts/bl-mem','producer_sha256':digest,
   'before':before,'after':'','current_counts_direct_vm_and_swap':True,'mutant_omits_direct_vm':True,
   'independent_total_mutation':{'before':total_before,'after':'"total_kb": st["VmRSS"]'},
   'scope':'Actual collect/kv parser and real fixture status files; /proc enumeration/readlink are I/O seams; trace delivery still needs BEAM control'})

if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(QualificationExtra))
 print('HISTORY_QUALIFICATION_EXTRA '+json.dumps({'passed':r.wasSuccessful(),'tests_run':r.testsRun,'observations':OBSERVATIONS},sort_keys=True))
 raise SystemExit(not r.wasSuccessful())
