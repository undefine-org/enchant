#!/usr/bin/env python3
"""Run exact existing unittest methods for a TestRT historical-case adapter.

These are Python test counts, never invented language assertion counts. The
outer historical runner owns source/floor freezing and native runtime identity.
"""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import unittest


def short_id(test):
    return type(test).__name__ + '.' + test._testMethodName


def flattened(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flattened(test)
        else:
            yield test


class ObservedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(short_id(test))


def execute(root, path, names):
    root, path = root.resolve(), path.resolve()
    if (not path.is_relative_to(root) or not path.is_file()
            or path.suffix != '.py' or not names or len(set(names)) != len(names)):
        raise ValueError('missing/escaped file, empty selection or duplicate unittest')
    spec = importlib.util.spec_from_file_location('history_qualification_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loader = unittest.TestLoader()
    discovered = list(flattened(loader.loadTestsFromModule(module)))
    if loader.errors:
        raise ValueError('unittest discovery failed: ' + repr(loader.errors))
    by_name = {}
    for test in discovered:
        name = short_id(test)
        if name in by_name:
            raise ValueError('duplicate discovered unittest: ' + name)
        by_name[name] = test
    if any(name not in by_name for name in names):
        raise ValueError('missing registered unittest: ' + repr(names))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, resultclass=ObservedResult).run(
        unittest.TestSuite(by_name[name] for name in names))
    passed = (result.wasSuccessful() and result.testsRun == len(names)
              and result.passed == names and not result.skipped
              and not result.expectedFailures and not result.unexpectedSuccesses)
    return {'status': 'passed' if passed else 'failed',
            'file': str(path.relative_to(root)), 'selected': names,
            'passed': result.passed, 'tests_run': result.testsRun,
            'failures': len(result.failures), 'errors': len(result.errors),
            'skipped': len(result.skipped), 'complete': passed,
            'output': stream.getvalue()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('names', nargs='+')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    try:
        report = execute(root, root / args.path, args.names)
    except Exception as error:
        report = {'status': 'error', 'complete': False, 'error': str(error)}
    print('BL-HISTORY-UNITTEST ' + json.dumps(report))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
