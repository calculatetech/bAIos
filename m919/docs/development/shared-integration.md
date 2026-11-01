# Shared integration reference

Developer notes moved from repository-wide documents. These are source and validation records, not operating instructions. Each section names its original document. A paragraph can describe a shared change across several ports. Port manuals own current user instructions.

## README.md

| Port | Status |
| --- | --- |
| [PC-Chips M919](../../README.md) | Active development. Revision3.4 reset and floppy limitations remain unresolved. |

```powershell
python -B tools/build-rom.py m919
python -B mp386/tools/build.py
python -B pb430/tools/build.py
pwsh -NoProfile -File presario-800/tools/build.ps1
```

After a shared change, run `python -B tools/update-ports.py` to build and validate the active ports in disposable source copies. M919 is developed and validated separately while wider pipeline coverage remains deferred. The [port update pipeline](../../../docs/port-updates.md) describes validation, retained media and candidate promotion.

## shared/README.md

The Presario currently consumes these files through forwarding includes at its original source paths. Its existing `-I presario-800/src/` include root resolves the forwarding paths. The M919 entry must add `shared/src/` to its NASM include roots.

`src/firmware/` owns the complete Presario donor shell used by M919: POST/Setup, RAM test and recovery, generic disk/floppy services, boot/CD policy, mouse, APM, and identity. Board callbacks isolate hardware access and controller selection. `src/pc/cpu.inc` supplies guarded vendor-aware CPU naming, and `src/pc/option-rom.inc` supplies bounded VGA validation/entry. Consumed partial ATA/FDC/POST copies were removed.

Each maintained port exposes the read-only `board_cpu_sl_query` adapter. It returns CPU profile evidence in AX and qualified board functions in DX. M919 returns DX bit0 only after successful startup installation, relocation and a fresh ping; other adapters return zero. `board_cpu_detect_name` adds an SL suffix to qualified Intel desktop names. `board_smm_prepare` gates the shared bounded installer. `src/pc/smm.inc` also supplies a stackless Intel-compatible handler with fresh replies and guarded relocation. CPU evidence does not authorize SMM, clock control, or a reset change. See [SL-enhanced 486 support](../../../docs/sl486-support.md) for contracts, primary evidence, and board limits.

M919 `port.json` generates `CFG_*` NASM variables through `shared/tools/rom.py`. Root commands `tools/build-rom.py <port>` and `tools/verify-rom.py <port>` use that configuration. The selected port supplies its assembly entry and hardware owners. Model/version/date literals belong only to port configuration. Optional `rom.checksum_regions` entries give a start, length and checksum-byte offset for independently checked banks. The whole-image checksum byte must lie outside those regions; ports without entries keep their existing layout.

M919 consumes the root donor core directly with UMC adapters. Presario retains its hardware shell and forwards generic services to the same maintained owners. Its include adapter resolves the current source tree before any shared include. Generic native fixtures live in `shared/tests/firmware/`; board fixtures belong to their ports.

The generic adapter keeps the host's existing bus strobes. Its hardware requirement is a standard ATA host that honors IORDY, the device's wait signal. Device acceptance does not prove that electrical property. No unknown timing registers or bus clock are inferred. PIO3/4 on each physical generic host remains unqualified. A known controller can use `BOARD_ATA_PIO_ADAPTER` to qualify and program its timing. M919 programs its complete seven-field timing recipe only for the enabled, usable673A PCI IDE function. Its supported PIO modes are not limited by an exact silicon revision or a separate clock selector. [ATA/ATAPI-5 draft1321D revision3](https://www.seagate.com/support/disc/manuals/ata/d1153r17.pdf) defines the IDENTIFY and SET FEATURES fields used here.

Setup keeps one menu owner for each setting. Ports can supply a field count, labels, parameter mapping and masked commit through the existing Devices renderer. M919 uses these hooks for its five Devices controls and the saved ECP DMA bit. The common Drives page retains the floppy-controller setting. Chipset views must remain within their own descriptor group and row table.

## docs/plans/BAIOS-011-sl486.md

Feature versions: M919 0.10.0, PB430 0.3.0, Presario 800 0.3.0, and MP386 0.4.0.

## docs/port-updates.md

Declarations can name existing whole-proof wrappers in `wrapped_tests`, mapping a script to current check IDs. Each `case_sets` entry can use `covered_by` to map a case to its current covering check. These are explicit source-backed credits; the runner does not infer a call graph. Case inventories read literal top-level dictionary keys without evaluating handlers. A null `argument` selects the positional value after the script; an omitted argument uses `--case`. Only current checks supply case and wrapper credits. Preparation, historical checks and candidate builds do not satisfy current validation. M919 retains its declared independent proofs, but its pipeline declaration still excludes routine execution.

The `boot-source` check on PB430, MP386 and M919 reuses the Presario failed-HDD, CD and Other producer proof. Port adapters supply existing external devices and enter real cold POST or installed INT19. The selector owns source identity throughout. Installed disk services must retain native geometry and read/write the independently selected sector. M919 uses its existing composed POST context and requires the requested image to match the executed default candidate exactly; differing variants are rejected.

M919 development has resumed, but its pipeline hold remains in effect pending wider qualification. It is excluded from routine selection and active completeness. An explicit held-port selection is rejected. Common reports remain at root; a port never receives another port's logs, comparisons, or root private state. Follow the [layout and candidate policy](../../../docs/repository-layout.md) for final versioned names and `LATEST.txt`.


## docs/porting.md

Read this document before selecting source for a port. Apply it to the Presario, M919, PB430, and future donors.
The modular base supplies reusable services. It does not establish that donor hardware setup works on another board.
The [repository cache rule](../../../AGENTS.md#reference-cache-setup) owns the requirements for matching the reference cache sequence.

| Source | Initial-port rule |
| --- | --- |
| M919 modular organization | Reuse its separation of owners. Its unfinished hardware policy is not a template. |

## docs/post-codes.md

Start with the board reference: [Presario 800](../../../presario-800/docs/post-codes.md), [PB430](../../../pb430/docs/post-codes.md), [MP386](../../../mp386/docs/post-codes.md), or [M919](../post-codes.md). Use the preceding codes and the screen to distinguish overlapping meanings.

| Code | Marker reached |
| --- | --- |
| `70` | IDE discovery starts. M919 scans both channels; other ports scan the primary channel. |

`71` through `83` can repeat for master and slave on each scanned channel. PB430 also uses several `76`–`7F` values during timing/cache work; its board table gives that context. M919 does not emit the separate primary-channel `84`/`85`/`86` markers.

## docs/public-source.md

Historical RAM/cache comparison code is retained as original-source fixtures in `m919/tests/baselines/`. PB430 shared-source comparisons use a checked-in hash table. These checks do not require private Git objects. The completed private document-relocation audit is retired from this distribution.


## docs/repository-layout.md

An organization-only change uses path, metadata, preservation and small synthetic tooling checks. It does not run a firmware or emulator validation matrix. Do not repeat an unchanged passing check. M919 remains excluded from routine port updates; its own roadmap governs resumed bench work and wider qualification.


## docs/roadmap.md

- **BAIOS-004: Add SMI and System Management Mode support where hardware permits.** Shared SMM services and SL names have a reviewed checkpoint. M919 0.12.1 now has physical S1 and W0 observations for relocation, a fresh ping and timed RTC callback/cleanup. The request-local reference controller enables and their restoration have a clean local checkpoint. The Stop Grant source census covers all 33 retained UMC images, available documentation and reference implementations. Next is an opt-in clock-request/wake/restore experiment; normal clock policy remains unchanged until qualified. Use a scope as a last resort, and retain the exact remaining questions. See the [SMM plan](../../../docs/plans/BAIOS-004-smm.md).

- **BAIOS-003: Share cache initialization and transition tests across controllers.** PB430 consumes a shared short SRAM workload and shared interrupted-RAM-test marker policy. Presario and PB430 use the maintained shared firmware owners. The [automated port update pipeline](../../../docs/port-updates.md) builds and validates maintained ports. Preserve each controller's complete reference setup and reset sequence. The complete common cache phase/transition driver and remaining M919 cache migration stay separate unfinished work.See the [cache lifecycle design and migration plan](../../../docs/plans/BAIOS-003-cache-lifecycle.md).

- **BAIOS-010: Complete shared PIO0–4 support.** Shared negotiation, command completion, reset restoration and effective-mode reporting cover all maintained ports. Ports can set a mode ceiling and provide controller timing operations. M919 includes PIO3/4 timing and no longer exposes a game-port control. The changed-path checks, ROM integrity checks and final native review passed. Physical PIO3/4 qualification remains separate. See the [PIO plan](../../../docs/plans/BAIOS-010-pio.md).

- **BAIOS-009: Standardize port organization and candidate identity.** Relocated source checkouts, standardized build and diagnostic paths, protected retained inputs and completed candidates, and added version/UTC naming with latest pointers. All four build folders were cleaned. The focused checks and final native review passed. M919 was on hardware hold at this checkpoint; its port roadmap now owns resumed development.
