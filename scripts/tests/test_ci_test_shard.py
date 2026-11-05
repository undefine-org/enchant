import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("ci_test_shard", Path(__file__).resolve().parents[1] / "ci-test-shard.py")
SHARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARD)


class TestPartitions(unittest.TestCase):
    def test_every_conventional_test_appears_exactly_once(self):
        root = Path(__file__).resolve().parents[2]
        groups = SHARD.partitions(root, 8)
        flat = [name for group in groups for name in group]
        expected = {str(path.relative_to(root)) for path in (root / "test").rglob("*")
                    if path.is_file() and path.name.endswith(("_test.bl", "_test.exs"))
                    and not any(part.startswith(".") for part in path.relative_to(root / "test").parts[:-1])}
        self.assertEqual(expected, set(flat))
        self.assertEqual(len(flat), len(set(flat)))
        self.assertTrue(all(groups))

    def test_long_suites_are_spread_by_duration_without_losing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test").mkdir()
            (root / "scripts").mkdir()
            for name in "abcd":
                (root / "test" / f"{name}_test.bl").touch()
            (root / "scripts/test-durations.json").write_text(
                '{"test/a_test.bl":9000,"test/b_test.bl":8000,"test/c_test.bl":1000,"test/d_test.bl":1000}')
            groups = SHARD.partitions(root, 2)
            self.assertEqual([["test/a_test.bl", "test/d_test.bl"], ["test/b_test.bl", "test/c_test.bl"]], groups)

    def test_fixtures_and_hidden_directories_are_not_suites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["test/a_test.bl", "test/nested/b_test.exs", "test/helper.bl", "test/.private/c_test.bl"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual([["test/a_test.bl"], ["test/nested/b_test.exs"]], SHARD.partitions(root, 2))

    def test_partition_count_must_be_positive(self):
        with self.assertRaises(ValueError):
            SHARD.partitions(Path("."), 0)

    def test_isolated_startup_is_balanced_without_combining_private_lifetimes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test").mkdir()
            (root / "scripts").mkdir()
            for name in "abcd":
                (root / "test" / f"{name}_test.bl").touch()
            timings = {f"test/{name}_test.bl": duration
                       for name, duration in zip("abcd", [9000, 8000, 1000, 1000])}
            isolated = {"test/c_test.bl": "requires a private VM"}
            (root / "scripts/test-durations.json").write_text(json.dumps(timings))
            (root / "scripts/test-isolation.json").write_text(json.dumps(isolated))
            groups = SHARD.partitions(root, 2, startup_ms=8000)
            self.assertEqual([["test/a_test.bl", "test/b_test.bl"],
                              ["test/c_test.bl", "test/d_test.bl"]], groups)
            self.assertEqual(isolated, json.loads((root / "scripts/test-isolation.json").read_text()))
            self.assertEqual(set(timings), {name for group in groups for name in group})

    def test_startup_estimate_must_be_a_nonnegative_integer(self):
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SHARD.partitions(Path("."), 1, startup_ms=value)
