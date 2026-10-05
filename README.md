# Make rebuild contract kit

**A successful build can still leave a stale executable.** This small, runnable repair lab demonstrates that mistake in one generated-header C program, then checks the fix does not rebuild needlessly.

It uses GNU Make, GCC and Python's standard library. It is an original synthetic example, not a scanner for your repository or a replacement build system.

## Run

Prerequisites: Linux, Python 3.12+, GNU Make 4.x and GCC. Make and GCC must be available in `/usr/bin` or `/bin`; the Python executable path must contain only ASCII letters, digits, `/`, `_`, `.`, `+` or `-`. Dependencies must already be installed. The lab does not install packages, use a network connection or accept an existing project path.

```sh
python3 -B lab.py --demo
python3 -B lab.py                     # repaired fixture: exit 0
python3 -B lab.py --profile order-only # deliberately stale build: exit 1
python3 -B lab.py --profile always     # deliberately needless rebuild: exit 1
python3 -B -m unittest discover -s tests -v
```

All runs print ASCII-escaped JSON. Exit `0` means the requested contract passed; `1` means a contract failed; `2` means an unsupported environment, setup failure or subprocess error prevented a complete assessment. Argument errors use argparse's normal stderr and exit 2. In `--demo`, exit 0 means the repair passes **and both broken controls are detected**, not that all profiles passed.

The important evidence looks like this:

| Profile | After changing value 11 → 29 | Same value from a clean build? | Unchanged build |
|---|---|---|---|
| `fixed` | app prints `29`; generate + compile run | Yes | No recipes |
| `order-only` | app still prints `11`; only generate runs | No: clean app prints `29` | No recipes |
| `always` | app prints `29`; generate + compile run | Yes | Compiles again |

The `order-only` Make invocation itself exits **0**. The lab catches the incorrect program result. The `always` example shows why rebuilding everything is an incomplete repair.

## The mistake and repair

The checked-in [fixture/Makefile](fixture/Makefile) is the repaired version:

```make
generated.h: value.txt generate.py
app: main.c generated.h
```

The lab creates two deliberately wrong copies in temporary directories:

- `order-only` changes the second line to `app: main.c | generated.h`. GNU Make ensures the header exists but does not use its age to invalidate an existing app
- `always` adds a phony `FORCE` prerequisite to `app`. This fixes stale output by compiling every time, but violates the no-op contract

In real projects, order-only prerequisites remain appropriate for dependencies whose update should not invalidate a target, such as an output directory. A header that changes compiled content belongs in normal prerequisites; larger C/C++ builds should normally use compiler-generated dependency files rather than manually enumerate every header.

## What the report establishes

Each profile uses the same five phases:

1. Clean build: the actual executable prints `11`; generation and compilation both occur
2. Unchanged build: output remains `11`; neither recipe should run
3. Change an unrelated file: output remains `11`; neither recipe should run
4. Change the generator input to `29`: the executable must print `29`; both recipes should run
5. Build the same mutated input in a separate clean directory: the executable prints `29` and must agree with the incremental result

The report contains actual program output, expected/observed recipe sequences, Make exit status, per-phase checks, clean/incremental equivalence, tool versions and verified timestamp ordering. Recipe markers are emitted by the fixture's actual recipes, not inferred from dry-run or debug text. The fixed generator deliberately rewrites its header; this example does not claim that all well-designed generators must compile after every input edit.

The lab copies only its five trusted fixture files. It moves their timestamps and the initial outputs into the past, verifies their strict ordering from the filesystem, then gives mutations later past timestamps. No sleep or future timestamp is used. Report timestamps vary between runs; they are evidence, not reproducibility targets. A filesystem that cannot preserve the required order is unsupported, not a pass.

Only owned temporary copies are changed and removed. Source fixture hashes are checked before and after successful runs. Child processes receive a minimal environment without inherited Make flags, injected Makefiles or compiler search-path variables. Each subprocess is limited to 15 seconds and 64 KiB of combined output; failures stop assessment. The trusted recipes create only small synthetic files. **This is not a sandbox:** modifying the fixture to execute untrusted commands makes it untrusted code. The bounds are not CPU, disk, memory or network isolation.

## Apply the lesson to your build

First identify an authorized project and one generated input that affects an observable application result. Reproduce a baseline in a disposable copy. Change that input, run the normal incremental build and inspect the actual program result; compare it with an independent clean build. Then check unchanged and genuinely unrelated-input builds. Repair only the authorized dependency declaration and rerun the same assertions.

Adapt the behavioral assertions to your project's real contract. This lab does not automatically read, edit, clean or execute another project. Recipe counts in this fixture are exact because its entire graph is known; different projects may legitimately do other work.

## Scope, versions and prior art

Initial local verification: Linux x86_64, GNU Make 4.4.1 and GCC 14.2.0, with Python 3.12.14 and 3.13.5. CI records its actual Make/compiler versions on Ubuntu 24.04 with those two Python versions. A successful run covers that environment; the accepted version range is not a claim that every version/platform combination has been tested.

This release covers one serial generated-header graph and its two bad variants. It does not prove parallel-build safety, shuffled-order robustness, hermeticity, bit-for-bit reproducibility, arbitrary dependency completeness, caching correctness or application correctness beyond the observed integer result. New build systems and a general-purpose runner are outside this release's maintenance scope.

- [GNU Make prerequisite types](https://www.gnu.org/s/make/manual/html_node/Prerequisite-Types.html) describe the intended normal/order-only behavior
- [GNU Make automatic prerequisites](https://www.gnu.org/software/make/manual/html_node/Automatic-Prerequisites.html) describe dependency-file generation
- [GNU Make options](https://www.gnu.org/software/make/manual/html_node/Options-Summary.html) include tracing and shuffled prerequisite order for other debugging needs
- [Ninja missingdeps](https://ninja-build.org/manual.html#ref_tools) checks missing dependency paths to generated inputs for Ninja projects
- [Reproducible Builds build variance](https://reproducible-builds.org/docs/adding-build-variance/) addresses reproducibility across environmental variation

Those tools and techniques should continue to be used. This lab's narrow contribution is a ready-to-run mutation → actual program output → clean-equivalence → no-op demonstration. It makes no novelty, demand or adoption claim.

## Optional creator invitation

This utility is made by the creator of [MyTest](https://mytest.app). If you want a separate game, the [private bot workshop](https://mytest.app/bot-workshop) lets you choose four rock-paper-scissors rules and inspect up to 20 hands per run. You can change rules, rerun, keep a rule card yourself or leave whenever you like. The scripted bot is not an independent AI. This is an optional promotional invitation: skip it freely. Visiting, playing or giving feedback is never required for the engineering task, and no productivity benefit is claimed.
