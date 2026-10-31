# Repository layout and build policy

<!-- cpk-rule-owner: repository-layout -->
<!-- cpk-rule-guard: Never create a whole repository clone or Git worktree inside any build directory or port directory. -->
<!-- cpk-rule-guard: Completed flash candidates use the version and recorded UTC build timestamp in their filenames. -->

## Ownership

Each port owns its `src/`, `tests/`, `tools/`, `diagnostics/`, `docs/`, `reference/`, and ignored `build/`. Standalone bench-tool sources belong in `diagnostics/`; guest test harnesses belong in `tests/`. Shared firmware and helpers belong in root `shared/`. Generic installed tools belong in root `tools/deps/`. Permanent manuals and shared test media belong in categorized root `reference/`. A port must not depend on another port's disposable build output.

Put every Git worktree or full source clone in root `.agent/worktrees/<task>/`. Disposable pipeline snapshots belong in root `.agent/test-results/port-update/`. Neither belongs in a port or any `build/` folder. Preserve dirty or unique work before moving or removing a checkout. Keep the primary mixed index untouched. Remove a completed worktree after its work is integrated and its state is clean. A normal task must not create another public-repository clone.

## Port build directories

Use the same categories in every port:

| Path | Contents |
| --- | --- |
| `build/` | Fixed bench images, completed current candidates, assembly metadata and latest pointers. |
| `build/diagnostics/` | Standalone DOS tools and diagnostic firmware. |
| `build/tests/` | Automated test fixtures, emulator wrappers and test results. |
| `build/review/` | Current review images, screenshots and comparisons. |
| `build/research/` | Generated disassembly and current reverse-engineering output. |
| `build/releases/` | Explicit release packages. |
| `build/tmp/` | Disposable scratch; empty after cleanup. |

Create only the directories a task needs. Put an experiment under its category instead of inventing another top-level build folder. Keep original inputs outside build. Diagnostic executables must never appear directly in the build root. Current failed diagnoses may retain their needed files; use `.retain-diagnosis` where automatic cleanup would otherwise remove them.

## Finding and completing a candidate

Open `<port>/build/LATEST.txt`. It states whether the latest output is a bench iteration or a completed candidate and lists the exact files, sizes and additive byte checksums, SUM32. `LATEST.json` is the matching machine-readable record. Starting a new bench build also keeps the last completed group in this record and in the cleanup retention list.

During bench work, reuse fixed filenames such as `baios-pb430.bin` or the MP386 combined/even/odd names. A new successful normal build updates the bench record. Test and research builds in subfolders do not replace the port's latest pointer.

After test iterations finish, run:

    python -B tools/finish-candidate.py <port>

Use `--directory <port>/build/review/<case>` to finish a recorded build from another allowed output directory. The command validates the assembly hashes and complete artifact group, then writes names such as `baios-mp386-even-v0.1.1-20261027T203000Z.bin` directly in the port's build root. All members share one group identity. The UTC timestamp is the most recent recorded assembly in the group. VGA pairs must share their system BIOS; programmer lanes must reproduce the combined image.

`build-info.json` binds the version and build times to the exact assembled bytes. Finishing reads this record, not the current source version. The port's existing validation declaration defines the required group members. Changed files, missing members or incompatible pairs are rejected before latest changes. A legacy image without a recorded assembly timestamp must be rebuilt before it receives a timestamped name. Do not invent an old build time from a file's modification date.

Finishing names and records a candidate. It does not assert that physical testing passed, publish a release, or authorize changing hardware policy. Keep the physical result and review status in their existing owners.

## Versions

<!-- cpk-rule-owner: baios-port-versioning -->

Each port has its own firmware version. Use its existing identity owner: `port.json`, or Presario's `src/bios.asm`. Before 1.0, a feature or breaking change increments the minor number and resets patch; a bug fix increments patch. Significant unreleased changes count. For example, feature 0.1.4 becomes 0.2.0 and fix 0.1.4 becomes 0.1.5. After 1.0, breaking changes increment major, features minor and fixes patch.

Select the next version for each coherent feature or fix before the candidate build. Repeated trials of that change keep the selected version. Do not increment per rebuild or rename old bytes to a newer version. Documentation, layout changes, comments, tests and review housekeeping alone do not change a port's firmware version. Released tags and filenames are immutable.

## Cleanup and work limits

Preview `pwsh -NoProfile -File tools/clean-build.ps1 -WhatIf`, then apply it after emulators stop. The root command calls each port's retention policy. Preserve the current bench and completed images, latest metadata, active diagnostics, current comparisons, original inputs and installed tools. Remove consumed VMs, disk copies, old iterations, stale copied repositories and caches. Verify retained ROM hashes after cleanup. Old checkouts must first move their retained card VHD and installed tools out of build output. Cleanup refuses to remove these unmigrated inputs. The shared deletion guard refuses Git metadata, outside paths and reparse points; it never silently deletes unique source.

An organization-only change uses path, metadata, preservation and small synthetic tooling checks. It does not run a firmware or emulator validation matrix. Do not repeat an unchanged passing check. M919 remains excluded from routine port updates; its own roadmap governs resumed bench work and wider qualification.
