#!/usr/bin/env python3
"""A single trusted GNU Make fixture, tested by observable build contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixture"
FILES = ("Makefile", "main.c", "generate.py", "value.txt", "unrelated.txt")
PROFILES = ("fixed", "order-only", "always")
NORMAL_RULE = "app: main.c generated.h\n"
MAX_OUTPUT = 65536
TIMEOUT = 15


class LabError(Exception):
    def __init__(self, kind: str, detail: str):
        self.kind, self.detail = kind, detail
        super().__init__(detail)


def command(argv, cwd, env, *, timeout=TIMEOUT, limit=MAX_OUTPUT):
    """Bound our known subprocesses. This is not a sandbox for arbitrary code."""
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True)
    except OSError as exc:
        raise LabError("tool_error", f"Could not start {Path(argv[0]).name}: {exc.strerror}") from exc
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LabError("timeout", "A fixture subprocess exceeded its time limit")
                for key, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(key.fileobj.fileno(), 4096)
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(data)
                        if len(output) > limit:
                            raise LabError("output_limit", "A fixture subprocess exceeded its output limit")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LabError("timeout", "A fixture subprocess exceeded its time limit")
            try:
                code = proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise LabError("timeout", "A fixture subprocess exceeded its time limit") from exc
        text = output.decode("utf-8", errors="replace")
        if code:
            raise LabError("command_failed", f"{Path(argv[0]).name} exited {code}: {text[:2000]}")
        return text
    finally:
        # Kill the owned group even if its original process already exited.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()


def isolated_env(home):
    # Do not inherit MAKEFLAGS, MAKEFILES, GCC_EXEC_PREFIX, CPATH, etc.
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(home),
            "LC_ALL": "C", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}


def source_hashes(root=FIXTURE):
    result = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
            raise LabError("fixture_error", f"Missing, linked or oversized fixture file: {name}")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def copy_fixture(destination, profile, value="11", root=FIXTURE):
    if profile not in PROFILES or value not in {"11", "29"}:
        raise LabError("fixture_error", "Unknown fixture profile or value")
    source_hashes(root)
    destination.mkdir()
    for name in FILES:
        shutil.copyfile(root / name, destination / name)
    makefile = (destination / "Makefile").read_text(encoding="utf-8")
    if makefile.count(NORMAL_RULE) != 1:
        raise LabError("fixture_error", "The fixture's normal app prerequisite rule changed")
    if profile == "order-only":
        makefile = makefile.replace(NORMAL_RULE, "app: main.c | generated.h\n")
    elif profile == "always":
        makefile = makefile.replace(NORMAL_RULE, "app: main.c generated.h FORCE\n")
        makefile += "\n.PHONY: FORCE\nFORCE:\n"
    (destination / "Makefile").write_text(makefile, encoding="utf-8")
    (destination / "value.txt").write_text(value + "\n", encoding="ascii")


def tools_for(root):
    if sys.version_info < (3, 12) or platform.system() != "Linux":
        raise LabError("unsupported", "This lab supports Linux and Python 3.12 or later only")
    tools = {"make": shutil.which("make", path="/usr/bin:/bin"),
             "cc": shutil.which("gcc", path="/usr/bin:/bin"), "python": sys.executable}
    if any(not value or not re.fullmatch(r"[/A-Za-z0-9_.+\-]+", value) for value in tools.values()):
        raise LabError("unsupported", "GNU Make, GCC and a simple absolute Python path are required")
    env = isolated_env(root)
    make_version = command([tools["make"], "--version"], root, env).splitlines()[0]
    if not re.match(r"GNU Make 4(?:\.|$)", make_version):
        raise LabError("unsupported", "GNU Make 4.x is required; other Make implementations are untested")
    gcc_version = command([tools["cc"], "--version"], root, env).splitlines()[0]
    if not gcc_version.lower().startswith("gcc "):
        raise LabError("unsupported", "The gcc executable did not identify itself as GCC")
    return tools, {"platform": platform.system(), "machine": platform.machine(),
                   "python": platform.python_version(), "make": make_version, "compiler": gcc_version}


def recipes(path):
    log = path / "recipes.log"
    if not log.exists():
        return []
    if log.stat().st_size > MAX_OUTPUT:
        raise LabError("output_limit", "The recipe log exceeded its limit")
    values = log.read_text(encoding="ascii").splitlines()
    if any(value not in {"generate", "compile"} for value in values):
        raise LabError("fixture_error", "Unexpected recipe log content")
    return values


def build(path, tools, expected, expected_recipes, phase):
    before = recipes(path)
    env = isolated_env(path)
    command([tools["make"], "--no-print-directory", "--no-builtin-rules",
             "--no-builtin-variables", "-f", "Makefile", "all",
             "CC=" + tools["cc"], "PYTHON=" + tools["python"]], path, env)
    after = recipes(path)
    if after[:len(before)] != before:
        raise LabError("fixture_error", "Recipe history was replaced unexpectedly")
    executed = after[len(before):]
    actual = command([str(path / "app")], path, env)
    checks = {"program_output": actual == expected + "\n", "recipe_sequence": executed == expected_recipes}
    return {"phase": phase, "make_exit": 0, "expected_output": expected + "\n",
            "actual_output": actual, "expected_recipes": expected_recipes,
            "actual_recipes": executed, "checks": checks, "passed": all(checks.values())}


def arrange_timestamps(path):
    # Past times avoid sleeps, clock-skew warnings and filesystem tick races.
    base = (time.time_ns() // 1_000_000_000 - 3600) * 1_000_000_000
    for name in FILES:
        os.utime(path / name, ns=(base, base))
    os.utime(path / "generated.h", ns=(base + 2_000_000_000,) * 2)
    os.utime(path / "app", ns=(base + 4_000_000_000,) * 2)
    stamps = {name: (path / name).stat().st_mtime_ns for name in (*FILES, "generated.h", "app")}
    if not all(stamps[name] < stamps["generated.h"] < stamps["app"] for name in FILES):
        raise LabError("unsupported_timestamps", "The filesystem did not preserve the required timestamp ordering")
    return base, stamps


def run_profile(profile, root, tools):
    work = root / profile
    copy_fixture(work, profile)
    phases = [build(work, tools, "11", ["generate", "compile"], "clean_initial")]
    base, stamps = arrange_timestamps(work)
    phases.append(build(work, tools, "11", [], "unchanged"))
    (work / "unrelated.txt").write_text("Changed, but still not a build input.\n", encoding="ascii")
    os.utime(work / "unrelated.txt", ns=(base + 6_000_000_000,) * 2)
    if (work / "unrelated.txt").stat().st_mtime_ns <= stamps["app"]:
        raise LabError("unsupported_timestamps", "Unrelated-file mutation time was not newer")
    phases.append(build(work, tools, "11", [], "unrelated_change"))
    (work / "value.txt").write_text("29\n", encoding="ascii")
    os.utime(work / "value.txt", ns=(base + 8_000_000_000,) * 2)
    mutation_time = (work / "value.txt").stat().st_mtime_ns
    if mutation_time <= (work / "generated.h").stat().st_mtime_ns or mutation_time >= time.time_ns():
        raise LabError("unsupported_timestamps", "Related-input timestamp ordering was not established")
    phases.append(build(work, tools, "29", ["generate", "compile"], "related_change"))
    clean = root / (profile + "-clean")
    copy_fixture(clean, profile, "29")
    phases.append(build(clean, tools, "29", ["generate", "compile"], "clean_mutated"))
    equivalent = phases[-2]["actual_output"] == phases[-1]["actual_output"]
    return {"profile": profile, "phases": phases,
            "timestamp_order_verified": True,
            "initial_mtimes_ns": stamps, "related_input_mtime_ns": mutation_time,
            "incremental_equals_clean": equivalent,
            "passed": equivalent and all(phase["passed"] for phase in phases)}


def run(profiles):
    before = source_hashes()
    with tempfile.TemporaryDirectory(prefix="make-rebuild-contract-") as name:
        root = Path(name)
        tools, versions = tools_for(root)
        results = [run_profile(profile, root, tools) for profile in profiles]
    unchanged = before == source_hashes()
    if not unchanged:
        raise LabError("fixture_error", "The source fixture changed during the run")
    return {"format": "make-rebuild-contract/1", "versions": versions,
            "source_fixture_unchanged": unchanged, "results": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--profile", choices=PROFILES, default="fixed")
    choice.add_argument("--demo", action="store_true", help="Verify the repair and both deliberately broken controls")
    args = parser.parse_args(argv)
    try:
        report = run(PROFILES if args.demo else (args.profile,))
        if args.demo:
            results = {result["profile"]: result for result in report["results"]}
            report["demo_checks"] = {
                "repair_passes": results["fixed"]["passed"],
                "stale_control_detected": not results["order-only"]["incremental_equals_clean"],
                "needless_rebuild_detected": not results["always"]["phases"][1]["checks"]["recipe_sequence"],
            }
            report["passed"] = all(report["demo_checks"].values())
        else:
            report["passed"] = report["results"][0]["passed"]
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if report["passed"] else 1
    except (LabError, OSError, UnicodeError) as exc:
        report = {"format": "make-rebuild-contract/1", "passed": False,
                  "error": getattr(exc, "kind", "environment_error"), "detail": str(exc)}
        print(json.dumps(report, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
