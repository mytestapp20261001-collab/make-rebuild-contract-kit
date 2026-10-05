import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lab


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = lab.run(lab.PROFILES)
        cls.results = {row["profile"]: row for row in cls.report["results"]}

    def test_fixed_passes_every_contract(self):
        self.assertTrue(self.results["fixed"]["passed"])
        self.assertTrue(all(p["passed"] for p in self.results["fixed"]["phases"]))

    def test_real_stale_success_is_detected(self):
        result = self.results["order-only"]
        mutation, clean = result["phases"][-2:]
        self.assertEqual(mutation["make_exit"], 0)
        self.assertEqual(mutation["actual_recipes"], ["generate"])
        self.assertEqual(mutation["actual_output"], "11\n")
        self.assertEqual(clean["actual_output"], "29\n")
        self.assertFalse(result["incremental_equals_clean"])
        self.assertFalse(result["passed"])

    def test_needless_rebuild_is_detected(self):
        result = self.results["always"]
        for phase in result["phases"][1:3]:
            self.assertEqual(phase["actual_recipes"], ["compile"])
            self.assertFalse(phase["checks"]["recipe_sequence"])
            self.assertTrue(phase["checks"]["program_output"])
        self.assertTrue(result["incremental_equals_clean"])
        self.assertFalse(result["passed"])

    def test_both_controls_initially_build_successfully(self):
        for result in self.results.values():
            self.assertTrue(result["phases"][0]["passed"])
            self.assertTrue(result["phases"][-1]["passed"])

    def test_fixed_noops_execute_no_recipes(self):
        self.assertEqual([p["actual_recipes"] for p in self.results["fixed"]["phases"][1:3]], [[], []])

    def test_timestamp_order_is_actual(self):
        for result in self.results.values():
            stamps = result["initial_mtimes_ns"]
            self.assertTrue(all(stamps[n] < stamps["generated.h"] < stamps["app"] for n in lab.FILES))
            self.assertGreater(result["related_input_mtime_ns"], stamps["app"])

    def test_source_is_unchanged(self):
        self.assertTrue(self.report["source_fixture_unchanged"])
        self.assertEqual((lab.FIXTURE / "value.txt").read_text(), "11\n")
        self.assertFalse((lab.FIXTURE / "app").exists())
        self.assertFalse((lab.FIXTURE / "generated.h").exists())

    def test_versions_are_recorded(self):
        self.assertRegex(self.report["versions"]["make"], r"^GNU Make 4\.")
        self.assertTrue(self.report["versions"]["compiler"].startswith("gcc "))
        self.assertEqual(self.report["versions"]["python"], lab.platform.python_version())

    def test_cli_exit_contracts(self):
        for name, expected in (("fixed", 0), ("order-only", 1), ("always", 1)):
            with self.subTest(profile=name), patch.object(lab, "run", return_value={"results": [self.results[name]]}):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = lab.main(["--profile", name])
                self.assertEqual(code, expected)
                self.assertEqual(json.loads(out.getvalue())["passed"], expected == 0)

    def test_demo_requires_all_three_discriminations(self):
        with patch.object(lab, "run", return_value=dict(self.report)), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--demo"]), 0)
        self.assertEqual(set(json.loads(out.getvalue())["demo_checks"]),
                         {"repair_passes", "stale_control_detected", "needless_rebuild_detected"})

    def test_setup_failure_is_distinct(self):
        with patch.object(lab, "run", side_effect=lab.LabError("unsupported", "Example")):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(lab.main([]), 2)
            self.assertEqual(json.loads(out.getvalue())["error"], "unsupported")


class BoundaryTests(unittest.TestCase):
    def test_make_environment_is_not_inherited(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "should-not-exist"
            injected = Path(d) / "injected.mk"
            injected.write_text(f"$(shell touch {marker})\n")
            env = dict(os.environ, MAKEFLAGS="-n", MAKEFILES=str(injected),
                       GNUMAKEFLAGS="-B", CC="false", CPATH="/no/such/path")
            proc = subprocess.run([sys.executable, "-B", str(lab.ROOT / "lab.py")],
                                  capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(json.loads(proc.stdout)["passed"])
            self.assertFalse(marker.exists())

    def test_temporary_files_are_cleaned(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(lab.tempfile, "tempdir", d):
                lab.run(("fixed",))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_failure_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(lab.tempfile, "tempdir", d), patch.object(lab, "tools_for", side_effect=lab.LabError("test", "stop")):
                with self.assertRaises(lab.LabError):
                    lab.run(("fixed",))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_broken_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "fixture"
            shutil.copytree(lab.FIXTURE, root)
            (root / "Makefile").write_text("all:\n\ttrue\n")
            with self.assertRaises(lab.LabError) as error:
                lab.copy_fixture(Path(d) / "copy", "fixed", root=root)
            self.assertEqual(error.exception.kind, "fixture_error")

    def test_symlink_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "fixture"
            shutil.copytree(lab.FIXTURE, root)
            (root / "value.txt").unlink()
            (root / "value.txt").symlink_to(lab.FIXTURE / "value.txt")
            with self.assertRaises(lab.LabError):
                lab.source_hashes(root)

    def test_oversized_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "fixture"
            shutil.copytree(lab.FIXTURE, root)
            (root / "value.txt").write_bytes(b"x" * 16385)
            with self.assertRaises(lab.LabError):
                lab.source_hashes(root)

    def test_unknown_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(lab.LabError):
                lab.copy_fixture(Path(d) / "copy", "other")

    def test_subprocess_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(lab.LabError) as error:
                lab.command([sys.executable, "-c", "import time; time.sleep(20)"], d, lab.isolated_env(d), timeout=0.1)
            self.assertEqual(error.exception.kind, "timeout")

    def test_subprocess_output_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(lab.LabError) as error:
                lab.command([sys.executable, "-c", "print('x'*10000)"], d, lab.isolated_env(d), limit=100)
            self.assertEqual(error.exception.kind, "output_limit")

    def test_subprocess_failure_is_not_contract_failure(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(lab.LabError) as error:
                lab.command([sys.executable, "-c", "raise SystemExit(7)"], d, lab.isolated_env(d))
            self.assertEqual(error.exception.kind, "command_failed")

    def test_fixture_has_no_generated_files(self):
        self.assertEqual({p.name for p in lab.FIXTURE.iterdir()}, set(lab.FILES))


if __name__ == "__main__":
    unittest.main()
