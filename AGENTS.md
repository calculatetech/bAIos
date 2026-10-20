# bAIos repository instructions

Always run PowerShell with `-NoProfile`.

<!-- cpk-rule-owner: hardware-live-iteration -->
<!-- cpk-rule-guard: Do not run per-candidate preflight, trace closure, or native review during an active physical hardware iteration. -->
<!-- cpk-rule-guard: Run complete validation, trace closure, and native review after the user confirms the desired physical result or requests finalization. -->

## Live hardware iteration

A physical test result starts or continues fast iteration mode for that system.

During fast iteration mode:

1. Diagnose the reported hardware result.
2. Make the smallest evidence-based change.
3. Build a flash-ready image in the system directory.
4. Run the quick ROM-integrity checks that protect the physical image.
5. Run a focused emulator check only when it can distinguish the changed path.
6. Report the image path, size, programmer checksum, and next physical observation. Use the full physical image's additive byte sum as eight hexadecimal digits (SUM32), not a SHA-256 hash. State the checksum type. Keep cryptographic hashes for internal artifact and reference checks.

Do not run Design Preflight, boundary trace closure, native correctness review, or the complete validation matrix for each candidate.

Do not finalize documentation or lifecycle records for each candidate. Keep temporary results in the ignored task-result file.

Every flash candidate must pass these checks:

- The system ROM has the required size and checksum.
- The physical image has the required size and layout.
- Retained ROM regions remain byte-identical to their selected inputs.
- The reset vector still targets the intended startup entry.

Fast iteration mode ends when the user confirms the desired physical result or requests finalization.

At finalization:

1. Update the documentation and lifecycle records.
2. Run the complete validation matrix.
3. Run boundary trace closure.
4. Run the required native review sequence.
5. Deliver the final flash image and recorded evidence.

<!-- cpk-rule-owner: reference-cache-setup -->
<!-- cpk-rule-guard: Use the complete working reference BIOS cache sequence before attempting hardware cache changes. -->

## Reference cache setup

Use the complete working reference BIOS cache sequence for a port. Preserve its prerequisites, register values and masks, jumper tables, CPU cache enable and invalidation order, interrupt and NMI handling, external cache activation, fill or flush routine, and final state. Do not reconstruct this sequence one register or one failed hardware trial at a time.

Compare the assembled port with the reference before handing off a cache candidate. Check the full hardware operation order and the table bytes. Keep the existing modular services and presentation. Adapt reference settings and private state to the port's established owners, and record each necessary adaptation in the port's diagnostic evidence. Do not treat a passing emulator or synthetic cache probe as proof of physical cache stability.

Keep added diagnostics outside the reference's transient cache window. Do not insert POST writes, stack operations, or other instrumentation while temporary tag/cache modes are active. Reference comparisons must retain every instruction and every I/O operation in that window; filtering diagnostics out does not prove equivalence. Put progress codes before entry and after return to normal mode.

## New ports

<!-- cpk-rule-route-only: reference-first-porting -->
[Reference instructions for new ports](docs/porting.md)

## Setup help

<!-- cpk-rule-owner: setup-help-language -->
<!-- cpk-rule-guard: Write all Setup help in plain, human-friendly language. -->

Write all Setup help in plain, human-friendly language. Explain what the setting does and when to choose it. Include a documented recommended choice when one exists. Keep register names, bit numbers, raw addresses, firmware implementation details, and debugging notes in developer documentation. Fit the existing help panel and use the established help renderer.

## Sorted choice lists

<!-- cpk-rule-owner: sorted-choice-lists -->
<!-- cpk-rule-guard: All user-visible choice lists must be sorted by their displayed values. -->

All user-visible choice lists must be sorted by their displayed values. Use ascending numeric order for numbers and alphabetical order for text. Show each value once. Mark the existing value as Default instead of adding a duplicate entry. Map display positions to stored values so that sorting does not change saved settings or hardware behavior.

## Build hygiene

Run Python with `-B`. Keep generated files under the system's `build/` directory or the ignored task-result directory.

At task handoff, remove completed disposable VMs, disk copies, and Python caches. Stop task-owned emulator processes when they are no longer needed. Keep a failed VM only while it is needed for the current diagnosis. Keep a visible preview while the user is reviewing it.

Preserve current ROMs, their system ROMs, current comparison results and review screenshots. Preserve original references, manuals, source files, the retained card VHD and installed dependencies. Untracked source files are not junk.

Use `tools/clean-build.ps1 -WhatIf` before applying cleanup after emulators stop. Purge obsolete builds, old archives and disposable media. Do not create rollback or evidence archives; Git is the version history. Check resolved paths before deletion or moves, and verify current ROM hashes after cleanup.

Remove completed plans and captures after their required consumers finish. Make sure their original sources remain reachable in Git before deletion. Delete consumed task logs, traces, and temporary helpers. Preserve unresolved decisions before removing their last working record.

Port-specific documents and files belong in the port directory. Generic chipset/controller manuals, standards and shared permanent test inputs belong in categorized root `reference/`. Keep permanent inputs out of build directories. Root `docs/` owns only project-wide documentation and the central roadmap.

The central `docs/roadmap.md` tracks only repository-wide tasks. Each port's `docs/roadmap.md` owns its port tasks. This user-required repository rule overrides the skill's root-only roadmap guidance.

Each maintained port owns its `tools/clean-build.ps1` retention policy. Shared cleanup mechanics must check the running-emulator guard and resolved paths, ancestors and descendants for reparse points before deletion. Root cleanup discovers maintained port commands; it must not contain port-specific model or artifact names. Current failed-diagnosis output belongs in protected diagnostics and is retained until its consumer finishes.

## Public source boundary

Do not commit vendor ROMs, complete disassemblies, manuals, operating-system media, personal configuration, or local paths. Keep these inputs outside Git. Run `python -B tools/check-public-source.py` before publishing. The public repository must never receive private development branches or tags.
