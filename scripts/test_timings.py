"""Read the existing BL_TEST_TIMES output without changing test execution."""
import re


def slowest(output, limit=5):
    namespace, rows = None, []
    for line in output.splitlines():
        if line.startswith('Testing '):
            namespace = line.removeprefix('Testing ')
        timing = re.fullmatch(r'  (.+?)\s+(\d+)ms', line)
        if timing:
            rows.append({'namespace': namespace, 'test': timing[1], 'milliseconds': int(timing[2])})
    return sorted(rows, key=lambda row: -row['milliseconds'])[:limit]
