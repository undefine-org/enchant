#!/usr/bin/env python3
"""Run exact existing portable-byte identity controls inside the bounded VM."""
import os
from pathlib import Path
import runpy
import sys

root = Path.cwd()
sys.argv = [str(root / 'test/scripts/qualification_packaged_identity.py'),
            '--sdk', os.environ['CLOSURE_PROOF_SDK'],
            '--out', str(Path(os.environ['CLOSURE_PROOF_OUTPUT']) / 'packaged-identity')]
runpy.run_path(sys.argv[0], run_name='__main__')
