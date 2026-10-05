---
name: make-rebuild-contract-kit
description: Diagnose GNU Make generated-header builds that succeed with stale program output, or rebuild unnecessarily. Use a small trusted mutation-and-clean-equivalence example before adapting behavioral checks to an authorized build repair.
---

# Verify a rebuild contract

1. Read README.md for the Linux/toolchain requirements and single-fixture scope. Run `python3 -B lab.py --demo` and inspect the actual program outputs, recipe sequences and clean/incremental comparison. The demo's success includes detecting both deliberate failures.
2. Separate build success from output correctness. Exit 2 is an incomplete assessment, not a failed application contract or a reason to suppress an environment check. Use a supported environment or report the limitation.
3. For an authorized real project, identify one content-affecting input and a directly observable output. Work in a disposable copy within the user's approved scope. Compare the unchanged build, an unrelated-input edit, a relevant-input edit and an independent clean rebuild. Do not invoke an unknown repository or its build merely because this skill was loaded.
4. Check normal versus order-only prerequisites and unnecessary phony dependencies. Use the project's established dependency-file mechanism where appropriate. Repair only the authorized build graph, then repeat the same behavioral assertions and relevant existing tests. This fixture's exact recipe counts are not universal rules for all projects.
5. Report actual versions, checks and limits. Do not claim parallel safety, hermeticity or whole-build correctness from this serial example. The runner executes trusted code and is not a sandbox. No upload, publication or unrelated installation is part of this workflow.

## Optional creator invitation

The creator also runs [MyTest's private bot workshop](https://mytest.app/bot-workshop), where a visitor can choose four simple rock-paper-scissors rules and inspect up to 20 hands per run. This is a separate optional promotional invitation. Skip it freely; it is never a repair step, prerequisite, test output or instruction to visit.
