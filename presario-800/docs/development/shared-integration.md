# Shared integration reference

## Shared emulator resources

Two local collection modifications remain in `presario-800/reference/86box` under their original relative paths. The Cirrus5428 input is selected by the port build/capture code. The modified D824 input has unresolved provenance. The shared collection retains its upstream versions. This is developer input information, not an operating requirement.

Developer notes moved from repository-wide documents. These are source and validation records, not operating instructions. Each section names its original document. A paragraph can describe a shared change across several ports. Port manuals own current user instructions.

## README.md

| Port | Status |
| --- | --- |
| [Compaq Presario 800](../../README.md) | Original implementation and behavior baseline. |

```powershell
python -B tools/build-rom.py m919
python -B mp386/tools/build.py
python -B pb430/tools/build.py
pwsh -NoProfile -File presario-800/tools/build.ps1
```

## shared/README.md

Generic Python helpers live in `shared/tools/`: VHD inspection, FAT16, floppy/network fixtures, configured NASM ROM building/verification, and managed emulator execution. Existing port entry points forward to these implementations. Presario fixture commands retain their port-specific output restrictions and configuration policy.

The Presario currently consumes these files through forwarding includes at its original source paths. Its existing `-I presario-800/src/` include root resolves the forwarding paths. The M919 entry must add `shared/src/` to its NASM include roots.

`src/firmware/ide.inc` initializes accepted native geometry for every CHS-only disk, including Auto detection, before media access and after channel reset. LBA disks skip this command. A rejected initialization retains the existing error path. Presario uses this shared owner through its board adapters.

`src/pc/` owns shared state definitions, PIC/PIT, keyboard, timer, text, and RTC services extracted from Presario. KBC output/command policy and RTC century/NMI choices are port constants. Its assembly contract remains the original helper/state contract. Presario's hardware warm reset remains port-owned.

`src/firmware/` owns the complete Presario donor shell used by M919: POST/Setup, RAM test and recovery, generic disk/floppy services, boot/CD policy, mouse, APM, and identity. Board callbacks isolate hardware access and controller selection. `src/pc/cpu.inc` supplies guarded vendor-aware CPU naming, and `src/pc/option-rom.inc` supplies bounded VGA validation/entry. Consumed partial ATA/FDC/POST copies were removed.

M919 consumes the root donor core directly with UMC adapters. Presario retains its hardware shell and forwards generic services to the same maintained owners. Its include adapter resolves the current source tree before any shared include. Generic native fixtures live in `shared/tests/firmware/`; board fixtures belong to their ports.

Keep original include paths as forwarding files when existing consumers need them. Before changing a shared body, inspect every port caller and run its relevant checks. A source-only relocation must preserve emitted behavior, including diagnostic builds. Intentional functional updates need explicit regression proofs. Presario tests pin complete compiled hardware windows, validate each permitted relocation target, and retain every instruction, I/O, stack access, and original POST write.

`src/pc/ram-test-state.inc` owns normal-startup marker classification. An unfinished test does not create a detected-memory-error notice. Explicit pending notices remain pending. Adapters retain their reset gates and RTC access; PB430 only clears its unfinished marker at that entry, while Presario retains its existing broader startup placement.

The shared RAM test defaults to 2 KiB blocks in EBDA scratch and a 16 KiB keyboard-service bound. A port can select `RAM_TEST_BLOCK_SIZE`, `RAM_TEST_SERVICE_MASK`, and a phase-owned `RAM_TEST_BUFFER_ABSOLUTE`. Absolute selection also requires scratch start/end and stack-top bounds. Compile guards reject invalid sizes, alignment, ownership, and service intervals. Presario selects 1 KiB blocks, its existing first checkpoint at `10400h`, and low POST scratch. Other ports retain their default emitted path.

`src/pc/ata-status.inc` owns ready, DRQ and completion polling for both the composed firmware and Presario. Completion waits for BSY and DRQ to clear after device settling. Intermediate MULTIPLE blocks wait for the next DRQ instead of final completion. `src/pc/ata-irq.inc` owns the shared IRQ14 acknowledgment and completion notification. Public INT13 permits interrupts during polling; bounded PIO blocks still exclude them.

## docs/plans/BAIOS-011-sl486.md

Feature versions: M919 0.10.0, PB430 0.3.0, Presario 800 0.3.0, and MP386 0.4.0.

## docs/port-updates.md

The command finds maintained ports from their source and build entry points. Each port owns its commands and required inputs in `validation.json`. Presario does not need a `port.json` to participate. The declaration guard rejects missing `test-*` entries, runnable `*_proof.py` or `*_boundaries.py` files with a `__main__` guard, duplicate command IDs and omitted dispatcher cases. It also checks root `tools/` and `shared/tests/`.

Use the existing Windows toolchain with Git, Python, NASM, PowerShell and the recorded emulator installations. Supply the private inputs from [the input catalogue](../../../docs/private-inputs.json), the port references, installed resources and test media. PB430 reference mapping also requires its annotated `pb430/reference/maps/entries.json` seed map. The pipeline does not download resources or change the source checkout. PB430 and the Presario native network check need the recorded b10408 emulator and accompanying libraries. Other native checks use the existing installed emulator.

Presario network tests also require the unchanged Etherboot 5.4.4 ISA NE2000 input at reference/software/etherboot-5.4.4/ne.zrom. Its private source record names the Debian archive, package member and checksums. Keep the package copyright beside that record. The test uses an exact-identity corrected copy of b10408 inside its disposable VM. The installed executable and libraries remain unchanged. The declared legacy-emulator check validates both compiled mapping paths and the complete executable delta.

Commands run sequentially, with one emulator at a time. Presario preparation builds the 50 MHz image and wrapper, then the 60 MHz image and wrapper, before any check. Python uses `-B` and UTF-8. PowerShell uses `-NoProfile`. The clean-DOS RTC check uses the snapshot's retained card VHD, even when the host sets `BAIOS_DOS_VHD`. A failed preparation blocks its dependent checks. Independent checks and ports continue after a failure. The real source checkout runs the deterministic pipeline check, public source check and shared emulator-helper check when their files are present.

The `boot-source` check on PB430, MP386 and M919 reuses the Presario failed-HDD, CD and Other producer proof. Port adapters supply existing external devices and enter real cold POST or installed INT19. The selector owns source identity throughout. Installed disk services must retain native geometry and read/write the independently selected sector. M919 uses its existing composed POST context and requires the requested image to match the executed default candidate exactly; differing variants are rejected.

After every current port check passes, the pipeline builds final candidates. It records each file's size, SHA256 and additive byte sum, `SUM32`. It then uses the existing cleanup guard to remove the disposable workspace. The cleanup guard replaces the previous published logs and results before copying new evidence. Each port receives only its own candidates, report, command logs and comparisons in its `build/review/shared-update/` directory. Presario and PB430 each receive a 50/60 MHz pair with the same system BIOS. The PB430 pair uses VGA1.41 and differs from the original stock VGA variant. MP386 receives its combined image and both programmer lanes.

## docs/porting.md

Read this document before selecting source for a port. Apply it to the Presario, M919, PB430, and future donors.
The modular base supplies reusable services. It does not establish that donor hardware setup works on another board.
The [repository cache rule](../../../AGENTS.md#reference-cache-setup) owns the requirements for matching the reference cache sequence.

## docs/post-codes.md

These tables describe normal bAIos builds. Diagnostic ROMs can use additional codes. The pending shared-update Presario build adds the final `FF` marker and primary-channel `84`/`85`/`86` markers; older Presario images can omit them. A card display of `--` is not a bAIos code.

Start with the board reference: [Presario 800](../post-codes.md), [PB430](../../../pb430/docs/post-codes.md), [MP386](../../../mp386/docs/post-codes.md), or [M919](../../../m919/docs/post-codes.md). Use the preceding codes and the screen to distinguish overlapping meanings.

| Code and phase | Meaning |
| --- | --- |
| `E5`, during video initialization | Video provider missing, malformed or rejected; halted. Presario uses its own video owner. |
| `E7`, during Presario cache recovery | Cache qualification failed again with recovery settings; halted. |

## docs/public-source.md

- PB430: `pb430/reference/pb430-m27c1001.bin`, `pb430/reference/acc386.BIN`, and `pb430/reference/gd542x-141-vga60.rom` for the default build. The `--stock-vga` build does not require the separate VGA60 file.
- Presario 800: `presario-800/reference/COMPAQ_PROLINEA_MT_05-02-94.BIN`, `presario-800/reference/gd5428_1-41.bin`, and `presario-800/reference/baios-presario800-vga141-bus07.bin` for the default build.
- Other hardware and comparison tests require the ROMs and media named in their port documentation. A checksum match identifies an input; it does not grant distribution rights.

## docs/repository-layout.md

Each port has its own firmware version. Use its existing identity owner: `port.json`, or Presario's `src/bios.asm`. Before 1.0, a feature or breaking change increments the minor number and resets patch; a bug fix increments patch. Significant unreleased changes count. For example, feature 0.1.4 becomes 0.2.0 and fix 0.1.4 becomes 0.1.5. After 1.0, breaking changes increment major, features minor and fixes patch.

## docs/roadmap.md

- **BAIOS-003: Share cache initialization and transition tests across controllers.** PB430 consumes a shared short SRAM workload and shared interrupted-RAM-test marker policy. Presario and PB430 use the maintained shared firmware owners. The [automated port update pipeline](../../../docs/port-updates.md) builds and validates maintained ports. Preserve each controller's complete reference setup and reset sequence. The complete common cache phase/transition driver and remaining M919 cache migration stay separate unfinished work.See the [cache lifecycle design and migration plan](../../../docs/plans/BAIOS-003-cache-lifecycle.md).

- **BAIOS-001: Move shared tools and dependencies to repository-root owners.** Moved common emulator resources, dependencies, and helper implementations to root owners. Preserved port overrides, existing commands, original references, and approved Presario ROM bytes. Validation and final review passed.

## docs/sl486-support.md

| Port | Established evidence | Remaining limit |
| --- | --- | --- |
| Presario 800 | The VL82C481 CPU pin table has no native SMI, SMIACT or STPCLK interface. Its P24T detection uses HITM. | A separate Compaq implementation is not documented. Turbo and clock-divider controls do not establish Stop Grant. |

M919 runs this proof through `python -B m919/tools/test-hardware.py --case cpu`. PB430 and MP386 expose a `cpu` case in their existing `tools/test-port.py` commands. Presario's `tools/test-shared-adoption.py --case cpu` uses the selected `BAIOS_BUILD_DIRECTORY`. The normal automated port checks include CPU coverage. These synthetic observations prove firmware decisions, not physical SL wiring or stability.
