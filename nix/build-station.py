"""Finite preparation transport. Placement is operator-owned local data.

The configured Nix store is a copy transport. Evaluation runs in the endpoint
process, from recipes copied with this immutable platform. Without a local
station description the same operations run through the ordinary Nix daemon.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import secrets
import socket
import subprocess
import tempfile
import sys
import time

STORE = re.compile(r'/nix/store/[0-9a-z]{32}-[^/]+\Z')
TICKET = re.compile(r'[0-9a-f]{64}\Z')
LIMIT = 1048576
PLATFORM = Path(__file__).resolve().parent.parent


def store(value):
    if not isinstance(value, str) or not STORE.fullmatch(value):
        raise ValueError('immutable store object required')
    return value


def operation(value):
    kind = value['kind']
    fields = {'native': {'version', 'kind', 'request'},
              'application': {'version', 'kind', 'sdk', 'request'},
              'release': {'version', 'kind', 'sdk'}}
    if kind == 'sdk':
        if value['version'] not in (1, 2, 3):
            raise ValueError('unsupported SDK operation version')
        expected = {'version', 'kind', 'source', 'product'}
        if value['version'] >= 2:
            expected.add('previous')
        if value['version'] == 3:
            expected.add('preparation')
        if value['product'] not in ('sdk', 'compiler', 'dependencies', 'bl-drop'):
            raise ValueError('unsupported SDK product')
    else:
        expected = fields[kind]
        if value['version'] != 1:
            raise ValueError('unsupported operation version')
    if set(value) != expected:
        raise ValueError('unknown preparation fields')
    for key in ('source', 'sdk', 'previous', 'preparation'):
        if value.get(key) is not None:
            store(value[key])
    if kind in ('native', 'application'):
        store(value['request']['source'])
    return value


def arguments(value, platform=PLATFORM):
    value = operation(value)
    kind = value['kind']
    recipe = {'native': 'native-artifact.nix', 'application': 'application-artifact.nix',
              'release': 'portable-artifact.nix', 'sdk': 'sdk-artifact.nix'}[kind]
    args = ['--file', str(platform / 'nix' / recipe)]
    if kind in ('application', 'native'):
        args += ['--argstr', 'requestJson', json.dumps(value['request'])]
    for key in ('source', 'sdk', 'previous', 'preparation', 'product'):
        if value.get(key) is not None:
            args += ['--argstr', key, value[key]]
    return args


def command(argv, **options):
    argv = list(map(str, argv))
    if argv[0] == 'nix':
        # Enable our CLI features without replacing operator NIX_CONFIG,
        # credentials, substituters or provider routing.
        argv[1:1] = ['--extra-experimental-features', 'nix-command flakes']
    started = time.monotonic()
    result = subprocess.run(argv, check=True, timeout=options.pop('timeout', 3300), **options)
    print('BUILD-STATION-PHASE ' + json.dumps(dict(tool=str(argv[0]), seconds=time.monotonic()-started)), file=sys.stderr, flush=True)
    return result


def bounded_json(stream):
    data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('station message exceeds bound')
    return json.loads(data)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def serve(message):
    if message.get('version') != 1:
        raise ValueError('unsupported station protocol')
    roots = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'beam_lisp/station'
    if message.get('action') == 'release':
        if set(message) != {'version', 'action', 'ticket'} or not TICKET.fullmatch(message['ticket']):
            raise ValueError('invalid station acknowledgement')
        directory = roots / message['ticket']
        if directory.exists():
            shutil.rmtree(directory)
        return {'version': 1, 'released': message['ticket']}
    if set(message) != {'version', 'action', 'operation', 'ticket'} or message['action'] != 'build' or not TICKET.fullmatch(message['ticket']):
        raise ValueError('invalid station request')
    value = operation(message['operation'])
    ticket = message['ticket']
    directory = roots / ticket
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    (directory / 'operation.json').write_text(json.dumps(value, sort_keys=True) + '\n')
    rows = json.loads(command(['nix', 'build', '--impure', '--print-build-logs', *arguments(value),
                              '--json', '--out-link', directory / 'result', '--option', 'timeout', '3300'],
                             stdout=subprocess.PIPE, text=True).stdout)
    target = store(rows[0]['outputs']['out'])
    if value['kind'] == 'sdk' and value['product'] == 'sdk':
        metadata = json.loads((Path(target) / 'artifact.json').read_text())
        target = store(metadata['image'])
    # The thin client does not import derivation/toolchain closures merely to
    # fetch logs. Keep a bounded report while its own remote output root lives.
    log = ''
    with tempfile.TemporaryFile() as stream:
        try:
            command(['nix', 'log', target], stdout=stream, stderr=subprocess.STDOUT, timeout=60)
        except subprocess.SubprocessError:
            pass  # A binary-cache hit need not have a local build log.
        else:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 256 * 1024))
            log = stream.read().decode('utf-8', errors='replace')
    return dict(version=1, ticket=ticket, operationSHA=digest(value), rows=rows,
                host=socket.gethostname(), log=log, logTarget=target)


def client(value, link, description=None):
    value = operation(value)
    if description is None:
        return json.loads(command(['nix', 'build', '--impure', '--print-build-logs', *arguments(value),
                                  '--json', '--out-link', link, '--option', 'timeout', '3300'],
                                 stdout=subprocess.PIPE, text=True).stdout)
    if set(description) != {'version', 'storeUri', 'transport'} or description['version'] != 1:
        raise ValueError('invalid local build description')
    uri, transport = description['storeUri'], description['transport']
    if not isinstance(uri, str) or not uri.startswith(('ssh-ng://', 'ssh://')):
        raise ValueError('station requires an SSH store transport')
    if not isinstance(transport, list) or not transport or not all(isinstance(a, str) and a and '\0' not in a for a in transport):
        raise ValueError('station requires an operator-provided command vector')
    if transport.count('{endpoint}') != 1:
        raise ValueError('transport must name the immutable endpoint exactly once')
    endpoint = str(PLATFORM / 'bin/beam-build-station')
    argv = [endpoint if a == '{endpoint}' else a for a in transport]
    inputs = [str(PLATFORM)]
    inputs += [store(value[k]) for k in ('source', 'sdk', 'previous', 'preparation') if value.get(k)]
    if 'request' in value:
        inputs.append(store(value['request']['source']))
    command(['nix', 'copy', '--to', uri, *dict.fromkeys(inputs)])
    ticket = secrets.token_hex(32)
    body = command(argv, input=json.dumps(dict(version=1, action='build', operation=value, ticket=ticket)),
                   stdout=subprocess.PIPE, text=True).stdout
    if len(body) > 3 * 1024 * 1024:
        raise ValueError('station response exceeds bound')
    response = json.loads(body)
    if response.get('version') != 1 or response.get('ticket') != ticket or response.get('operationSHA') != digest(value) or len(response['rows']) != 1:
        raise ValueError('station answered a different operation')
    output = store(response['rows'][0]['outputs']['out'])
    command(['nix', 'copy', '--from', uri, output])
    command(['nix-store', '--add-root', link, '--indirect', '--realise', output], stdout=subprocess.DEVNULL)
    if response.get('log'):
        (Path(link).parent / 'station-build.log').write_text(response['log'])
    print('BUILD-STATION-PLACEMENT ' + json.dumps(dict(host=response['host'], evaluation='station', output=output)), file=sys.stderr, flush=True)
    try:
        command(argv, input=json.dumps(dict(version=1, action='release', ticket=response['ticket'])), stdout=subprocess.DEVNULL, text=True)
    except subprocess.SubprocessError:
        print('station root retained for recovery: ' + response['ticket'], file=sys.stderr)
    return response['rows']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--operation', type=Path)
    parser.add_argument('--out-link', type=Path)
    parser.add_argument('--description', type=Path, default=Path('/etc/beam-lisp/build-station.json'))
    args = parser.parse_args()
    if args.serve:
        result = serve(bounded_json(sys.stdin))
    else:
        if args.operation is None or args.out_link is None:
            parser.error('client requires an operation and output root')
        with args.operation.open() as stream:
            value = bounded_json(stream)
        description = None
        if args.description.exists():
            with args.description.open() as stream:
                description = bounded_json(stream)
        result = client(value, args.out_link, description)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
