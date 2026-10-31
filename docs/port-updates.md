# Update and validate maintained ports

Run the local pipeline after a shared source change:

```powershell
python -B tools/update-ports.py
```

The command finds maintained ports from their source and build entry points. Each port owns its commands and required inputs in `validation.json`. Presario does not need a `port.json` to participate. The declaration guard rejects missing `test-*` entries, runnable `*_proof.py` or `*_boundaries.py` files with a `__main__` guard, duplicate command IDs and omitted dispatcher cases. It also checks root `tools/` and `shared/tests/`.

Declarations can name existing whole-proof wrappers in `wrapped_tests`, mapping a script to current check IDs. Each `case_sets` entry can use `covered_by` to map a case to its current covering check. These are explicit source-backed credits; the runner does not infer a call graph. Case inventories read literal top-level dictionary keys without evaluating handlers. A null `argument` selects the positional value after the script; an omitted argument uses `--case`. Only current checks supply case and wrapper credits. Preparation, historical checks and candidate builds do not satisfy current validation. M919 retains its declared independent proofs, but its pipeline declaration still excludes routine execution.

Use the existing Windows toolchain with Git, Python, NASM, PowerShell and the recorded emulator installations. Supply the private inputs from [the input catalogue](private-inputs.json), the port references, installed resources and test media. PB430 reference mapping also requires its annotated `pb430/reference/maps/entries.json` seed map. The pipeline does not download resources or change the source checkout. PB430 and the Presario native network check need the recorded b10408 emulator and accompanying libraries. Other native checks use the existing installed emulator.

Presario network tests also require the unchanged Etherboot 5.4.4 ISA NE2000 input at reference/software/etherboot-5.4.4/ne.zrom. Its private source record names the Debian archive, package member and checksums. Keep the package copyright beside that record. The test uses an exact-identity corrected copy of b10408 inside its disposable VM. The installed executable and libraries remain unchanged. The declared legacy-emulator check validates both compiled mapping paths and the complete executable delta.

The native success case boots the downloaded image. The error case receives a real TFTP file-not-found error, sends Q at the provider menu, and checks BIOS disk continuation. Etherboot retries without that explicit quit. The same external observer stays passive during successful network boot. The shared Local Switch peer uses loopback broadcast replies on Windows.

The pipeline copies current Git source, including uncommitted files, to a disposable workspace. It copies declared inputs and resources into that workspace. Installed resource junctions become ordinary copies. It excludes resource Git metadata. All firmware commands, including nested builders with fixed output paths, run in the copy. Approved images in the original port directories remain unchanged. Private inputs are compared before and after the run.

Commands run sequentially, with one emulator at a time. Presario preparation builds the 50 MHz image and wrapper, then the 60 MHz image and wrapper, before any check. Python uses `-B` and UTF-8. PowerShell uses `-NoProfile`. The clean-DOS RTC check uses the snapshot's retained card VHD, even when the host sets `BAIOS_DOS_VHD`. A failed preparation blocks its dependent checks. Independent checks and ports continue after a failure. The real source checkout runs the deterministic pipeline check, public source check and shared emulator-helper check when their files are present.

Native CD checks wait for the supplied disc's DOS startup and installation menu, verify the captured text, and stop the emulator. `--preview` remains interactive. Native CD and clean-DOS RTC fixtures use valid saved CMOS with cache Off because the d824 emulator does not model the board's L2 SRAM. They use the production BIOS without changes.

The complete read-only floppy sweep has an explicit 600-second limit per case. It still reads every track and head under both tested interrupt states and verifies that the source images did not change. The host fixture lifecycle check uses a synthetic process only; the separate native EMM reset commands must still reach their real guest exit codes.

The `boot-source` check on PB430, MP386 and M919 reuses the Presario failed-HDD, CD and Other producer proof. Port adapters supply existing external devices and enter real cold POST or installed INT19. The selector owns source identity throughout. Installed disk services must retain native geometry and read/write the independently selected sector. M919 uses its existing composed POST context and requires the requested image to match the executed default candidate exactly; differing variants are rejected.

The current report is `.agent/test-results/port-update/current.json`. Each command records its exact arguments, exit code, elapsed time and log. Generated comparison reports and screenshots remain in the run's `results/` directory after workspace cleanup. The report records their retained paths and hashes. It binds all results to a fingerprint of the copied source. A new invocation replaces the current result. An earlier success never satisfies a new run.

After every current port check passes, the pipeline builds final candidates. It records each file's size, SHA256 and additive byte sum, `SUM32`. It then uses the existing cleanup guard to remove the disposable workspace. The cleanup guard replaces the previous published logs and results before copying new evidence. Each port receives only its own candidates, report, command logs and comparisons in its `build/review/shared-update/` directory. Presario and PB430 each receive a 50/60 MHz pair with the same system BIOS. The PB430 pair uses VGA1.41 and differs from the original stock VGA variant. MP386 receives its combined image and both programmer lanes.

If a check, input, artifact or cleanup operation fails, the command exits with an error and retains the workspace for diagnosis. It does not promote a candidate. Original source, approved images and copied input identities must remain unchanged. The report names the retained workspace.

Inspect the declaration inventory without private inputs or builds:

```powershell
python -B tools/update-ports.py --list
```

Use selectors for a focused diagnosis:

```powershell
python -B tools/update-ports.py --port pb430 --check cache-check
```

A subset of ports or checks is a partial run. It cannot promote candidates or claim complete validation. Full validation means every current command for every active port. Two retired MP386 bench-probe suites and a frozen whole-ROM source-equivalence check remain historical, with their original conditions and exclusion reasons. The source-equivalence case permits only the old Auto CHS patch, so current shared adoption cannot satisfy it. Its pins are unchanged. They are not reported as passed. Use `--historical` only when those original superseded inputs are available. The pipeline never rebuilds current firmware under their old names.

A private checkout can also retain `tools/test-repository-layout.py`. That one-time migration audit requires private Git history and the former two-task roadmap. The pipeline lists it as historical when present. It does not count it as current firmware validation. `--historical` attempts that original audit too, and its failure remains a failure.

When a port gains a test, add its command to that port's declaration. Add optional native modes and self-checking diagnostic builders as separate commands. Use `case_sets` for an explicitly enumerated dispatcher. The guard reads its literal case tuple or argument choices from source and rejects an omitted later case. Default suites that already enumerate all their own cases keep that behavior.

Keep input and resource paths relative to the repository. Preparation commands create working images and required diagnostics inside the copy. Candidate commands run after complete validation. Artifact entries name the complete physical files and expected sizes. An experimental build used by a check does not become a promoted flash candidate.

Run the deterministic pipeline check after changing this command or a declaration:

```powershell
python -B tools/test-port-updates.py
```

This check uses disposable source and real child commands. It covers preservation, resource copies, current failures, partial selections, inventory drift, artifact rejection and guarded cleanup. Software checks do not establish electrical timing margins or qualify a new physical flash.

M919 development has resumed, but its pipeline hold remains in effect pending wider qualification. It is excluded from routine selection and active completeness. An explicit held-port selection is rejected. Common reports remain at root; a port never receives another port's logs, comparisons, or root private state. Follow the [layout and candidate policy](repository-layout.md) for final versioned names and `LATEST.txt`.
