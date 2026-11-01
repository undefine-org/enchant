#!/usr/bin/env python3
"""Index a qualified pre-unit-store compiler without recompiling its units.

The immutable product's complete P/B/C proof binds every old byte. Only its
recorded source digests can justify reuse; the Source producer additionally
checks its current unit inputs, codegen key and host ABI declaration bytes.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

MARKER = b';; Artifact production owns preparation'


def baseline(compiler, source, current):
    spec = importlib.util.spec_from_file_location('proof', Path(__file__).with_name('check-produced-compiler.py'))
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    proof.store_output(str(compiler))
    proof.store_output(str(source))
    proof.verify_proof(compiler, compiler / 'seed')
    inputs = proof.read_json(compiler / 'qualification/inputs.json')
    seed = source / 'priv/build/seed.bl'
    if inputs.get('priv/build/seed.bl') != proof.digest(seed):
        raise ValueError('Prior compiler source differs from its qualified inputs')
    prefix, separator, _ = seed.read_bytes().partition(MARKER)
    if not separator:
        raise ValueError('Prior compiler has no artifact ABI boundary')
    natives = {name: value for name, value in inputs.items() if name.startswith('priv/native/')}
    if not natives or any(proof.digest(current / name) != value for name, value in natives.items()):
        # A native change can affect the actual producer, even with equal BL source.
        return None
    return {'version': 1, 'compiler': str(compiler), 'floor': str(compiler / 'seed'),
            'compiler_key': proof.manifest_keys(compiler / 'seed/manifest.term')['compiler_key'],
            'abi_prefix_sha256': hashlib.sha256(prefix).hexdigest(), 'inputs': inputs,
            'modules': proof.actual_inventory(compiler / 'seed')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(baseline(args.compiler, args.source, args.current), sort_keys=True) + '\n')
