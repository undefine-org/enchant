#!/usr/bin/env python3
"""Select fully successful trusted main CI for this exact release commit."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

CI_PATH = '.github/workflows/ci.yml'


def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True))


def qualified(run, repository, revision, run_id=None):
    return (isinstance(run, dict) and type(run.get('id')) is int and run['id'] > 0
            and (run_id is None or str(run['id']) == str(run_id))
            and run.get('name') == 'ci' and run.get('path') == CI_PATH
            and run.get('event') == 'push' and run.get('head_branch') == 'main'
            and run.get('repository', {}).get('full_name') == repository
            and run.get('head_repository', {}).get('full_name') == repository
            and run.get('head_sha') == revision
            and run.get('status') == 'completed' and run.get('conclusion') == 'success')


def resolve(repository, revision, run_id=None, *, request=api):
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
            or not re.fullmatch(r'[0-9a-f]{40}', revision)):
        raise ValueError('Release requires a repository and exact commit SHA')
    prefix = f'repos/{repository}/actions'
    if run_id is not None:
        if not re.fullmatch(r'[0-9]+', run_id):
            raise ValueError('Qualified CI run must be an exact numeric ID')
        run = request(f'{prefix}/runs/{run_id}')
        if not qualified(run, repository, revision, run_id):
            raise ValueError('Requested CI did not fully qualify this exact trusted main push')
        return run_id
    # A release tag does not trigger another SDK/inventory when main already
    # qualified these exact bytes. API failures remain errors; only an actual
    # absence of successful CI selects the ordinary production path.
    page = 1
    while True:
        data = request(f'{prefix}/workflows/ci.yml/runs?branch=main&event=push'
                       f'&head_sha={revision}&status=success&per_page=100&page={page}')
        runs = data['workflow_runs']
        for candidate in sorted(runs, key=lambda run: run['id'], reverse=True):
            if qualified(candidate, repository, revision):
                # Recheck the complete run, not just a producer job or a stale
                # list result whose latest attempt has since started again.
                selected = request(f'{prefix}/runs/{candidate["id"]}')
                if qualified(selected, repository, revision, candidate['id']):
                    return str(candidate['id'])
        if len(runs) < 100 or page >= 10:
            return ''
        page += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'), required=False)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--run-id')
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    if not args.repository:
        parser.error('A repository is required')
    selected = resolve(args.repository, args.revision, args.run_id)
    if args.github_output:
        with args.github_output.open('a') as output:
            print('runtime_run=' + selected, file=output)
    print(f'Fully qualified CI: {selected}' if selected else 'No qualified CI for this commit; normal production and inventory required')


if __name__ == '__main__':
    main()
