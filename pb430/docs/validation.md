# PB430 validation

Run from the repository directory with Python `-B` and PowerShell `-NoProfile`:

```powershell
python -B pb430/tools/test-port.py --case all
python -B pb430/tools/test-port.py --case serial
python -B pb430/tools/test-port.py --case cache
python -B pb430/tools/test-stock-options.py
python -B pb430/tools/test-cache-check.py pb430/build/baios-pb430.bin
python -B pb430/tools/test-post-layout.py pb430/build/baios-pb430.bin
python -B pb430/tools/test-timing-recovery.py
python -B pb430/tools/test-ata-chs.py --image pb430/build/baios-pb430.bin
python -B pb430/tools/test-boot-source.py --image pb430/build/baios-pb430.bin
```

Run cases sequentially. Each invocation rebuilds the same current ROM and listing; concurrent invocations can interrupt another case's listing read.

Diagnostic builds, two-drive floppy swaps, stale boot-buffer rejection and native RAM-key observers use the supported stock-VGA build to leave room for instrumentation. The normal VGA60 image has separate native boot, display and video-service checks. A passing instrumented stock-VGA case does not by itself prove the same combined path on physical VGA60 hardware.

Each named case writes a JSON result under `pb430/build/test-results/`. A failure raises and writes `status: failed`; it is not counted as a pass. Native failed fixtures keep `.retain-diagnosis` until their consumer finishes. Test images, native VM files, disk/ISO copies, display cells, font bytes and PNGs belong to the port build directory. The single ignored task record contains exact commands and outcomes. This document records the supported execution boundaries.

## Execution boundaries

| Check | Actual production path and independent terminal |
| --- | --- |
| image | Builder and verifier; default, stock, VGA50/VGA60 and experimental command-line selection; retained video/padding, fixed VGA entry, selected late CD placement, reset/checksum and five damaged-image rejections |
| native | Actual NASM dependency/preprocessor provenance, active symbols and decoded assembled I/O, plus compiled missing-owner/UMC/PCI negatives; PB430 reset through all owners and INT19 to real DX/SX boot |
| display | Actual Cirrus provider, clean and dirty provider returns, Setup Discard return; all 2000 characters, 2000 attributes and 4096 original font bytes |
| chipset-settings | Real Setup edit/Save/KBC reset/vector/startup/apply; saved ADS with only Auto changed, masked 1A and preserved unknown bit 6 |
| setup-policy | New defaults, existing-record compatibility, real Save/Discard/Defaults and ADS hardware result, configured L1 display while hardware is off, Fast Boot cold and warm RAM block traces, saved choice after CAD and Setup reopening, full capacity and mandatory initialization, help inventory and actual F1 panels across Setup |
| boot-defaults | Actual Setup Defaults/Save followed by native boots with CD, floppy and disk available; removal of each earlier bootable medium proves CD, A, HDD priority; saved schema 1-5 disk-first orders boot disk with all three media available |
| diagnostics-input | Full warm startup to E4 retry with ordered stages, present/silent/failed keyboard; three compiled diagnostic callbacks and real PS/2 reset/IRQ12/callback |
| reset | Actual reset vector; 05/0A continuation, consumed shutdown byte, both-PIC/no-EOI contrast, original stack/EDX; normal warm and stale cold RAM/map/count contrasts; real Save/warm/cold/handoff/RAM/boot, legacy8042 wrapping and public AH87 temporary-gate restoration, complemented by native wrapping; signed ATA boot before and after both Ctrl+Alt+Del variants, with full POST/redetection and a native three-boot BDA witness |
| memory | Actual reset, all four independent bank views, exact OEM comparator/routing, measured alias count, real BDA/EBDA construction and installed INT12/15; native 4/8/32/64 MiB boots |
| settings-load | Real settings owners, recognized base versions 1-5, nondefault records and isolated invalid base/chip/port/IDE extension fallback, no CMOS writes |
| clock | Actual POST notice for an invalid clock versus a valid clock, with valid settings preserved; time-only editor versus date/time editor, good/low VRT predicate, diagnostic byte and public INT1A |
| setup | Draft edits, Defaults/Discard/Save, actual reset and later IRQ1/INT16; native editor, Discard and Manual Save/warm/frame |
| shadow | Real staged F000 transitions and C000 provider origin through Save/reset/full POST/retry; repeated onboard warm entry, fixed required field; four native provider/policy boots and whole visible F000 export |
| cache | Independent SRAM aliases through actual UI/Save/reset/full POST/final gate/late cache/summary/E4 retry; absent/ambiguous/qualified/disabled and CPU-off contrast; complete stock parent through4C56, controller/NMI continuation, pre-reset cache teardown and byte-identical pulse preparation; no diagnostic I/O inside the uninterrupted transient window |
| stock-options | Real ISA/COM menu Save/reset, Defaults/Discard, profiles, cold/warm/cache transitions, service resume, preserved register06 upper bits, alternate-pair discovery and public INT14; signed disk boot and public INT13 observe the selected divider |
| serial | Data-sheet DE oracle, actual UI/Save/reset/program/probe/BDA/INT14; both UARTs, all bases, simultaneous sources, nearest IRQ conflict, invalid/legacy records, duplicate prefix and later ISA UART |
| parallel | Real UI/Save/reset/program/BDA/INT11/INT17; Disabled, all three bases, equipment count, compatible/bidirectional and transmitted payload |
| floppy | Native real-media reads with swapped motors/units; absent/disabled controller public INT13 error and BDA status/equipment; real Save/reset/legacy VERSION probe and rejected 2.88 MiB read |
| disk-services | Native primary master, slave-only and both; actual AH48 geometry/capacity, AH42/AH43 payload and range rejection |
| cd | Native master/slave-only, unusable first with later bootable, unusable-only fresh retry, floppy emulation; actual catalog/device selection and AH4B vector/equipment cleanup |
| option-roms | Actual Save/reset/scanner/summary/retry for empty/one/multiple/covered/late/bad ROM collections; immediate return context and once-only calls; native multiple and damaged-first/later-valid scans; a 64 KiB video provider contains valid/invalid interior signatures that are skipped while a genuine later ROM initializes |
| boot-order | Native saved cursor through first success, unavailable floppy then disk, returning Other and INT18 provider, nine fresh-key retry chains and a stale signed sector buffer |
| ram | Shared burst owner with coverage, restore/context/descriptor/A20/parity assertions and fault; native Pause/resume, Esc and Delete/Save/warm with Fast Boot off and on, later real IRQ1/INT16 |
| build-hygiene | Actual copied retention command and unchanged shared safety guard in an owned fixture; WhatIf, completed/failed markers, current hashes, idempotence, owned junction rejection and running real emulator guard |

The bank cases execute the real reset vector, mapper/count, cache policy, staged shadow, PIC/PIT, RTC, SIO, AT prerequisites, video, keyboard, settings and publication owners before installed INT12/INT15. They do not jump from the mapper to publication.

The independent `memory_proof` models bank storage, aliases, floating-bus absence and register-selected visible order. It does not replace the memory decision owner. Its public-service state follows the mapped low bank, including an absent first bank. Native 86Box complements this with complete boot and real counts, but its memory model cannot establish physical bank wiring.

`core_proof` parameterizes the established Presario RTC/Setup input fixtures with independent ACC devices. Its port92 and8042 output values retain actual D0/D1/write state. The reset check decodes their ORed A20 gate with independent low/high RAM windows, observes the original handoff and RAM owner on actual Save/warm/cold/boot paths, then checks legacy disable/wrap/re-enable and installed INT15 AH87 data/context/gate restoration. A native guest repeats actual8042 wrapping and public move after cold startup/Setup Save/warm; complete native frame/font exports remain unchanged. The external seam responds to device I/O, the VGA provider and the hardware reset pulse. A reset pulse starts at F000:FFF0 and executes the real far reset vector. No board/shared helper is skipped. Composed cache, shadow and ROM cases continue through all production gates to the declared E4 no-device retry terminal. Each shadow UI/Save/reset path checks protected final mapping, original provider/font bytes and installed INT10/INT42/INT12/INT15 at its retry terminal. Each cache path checks L2 off at the actual final gate, the late write chronology, every segmented flush read and restored RAM at the late return and retry. UART/parallel paths check documented reserved masks and all unrelated register fields at actual owner return. The filtered IRQ conflict is saved and verified through reset/BDA/INT14. Component checks remain supplemental and are identified separately. The shadow check also supplies synthetic external ROMs with valid 16/32/64 KiB headers and an independent in-bounds font service at C000:1000; the same original 4096 font bytes are held equal across sizes. Each size runs actual UI/Save/reset/provider/policy/services/retry with shadow off/on. An independent C000/C800 device seam enforces the 32 KiB shadow window, exact short-copy extent and unchanged external upper bytes. Zero length, 129 units and corruption near the end of a 64 KiB declaration fail before the provider call. These are provider-contract fixtures, not claims about a tested physical card; the retained provider and native full-frame cases use the provider-specific font address. The same shadow check holds the original provider, font and Disabled policy equal while comparing C000:0100, C010:0000 and BFFF:0110 aliases for the identical physical INT10 handler. The raw vector reaches INT42 unchanged after actual UI/Save/reset/provider/services/retry. Physical BFFFF and D0000 vectors fail at E5 after one provider invocation; malformed headers still fail before that call. Initializer return context is checked on both outcomes.

Diagnostic cases retain the actual keyboard, floppy and mouse callback reports, their device/status details and disabled FDC/AUX contrasts. IRQ1 cases contrast active Delete request without queueing against closed Delete queueing, command replies and later INT16. Native Pause/Esc/Delete paths independently retain a RAM pattern and CR0/GDTR/A20/parity snapshots; Delete checks restoration before Save and again after the real warm reset. The exact UI-saved chipset record is also loaded by a fresh native cold boot.

Native disk guests check both BIOS units with distinct master/slave payloads, AH08/AH48 geometry, successful AH/count and range failures. Floppy guests read logical A and B with swapped and unswapped media. AH08 returns disk count in DL and the inherited reserved-cylinder geometry; the guest restores the unit before its next call. A disabled IDE case executes the real initialization/public error path without ATA commands. Scanner cases record ordered ROM entries; a provider installs a nonzero captured INT19 chain and returns to the real cursor/retry. A separate provider invokes public INT18 with the cursor inactive and reaches that same retry owner.

The ATA parameter check executes actual cold POST and Setup Save/reset against an independent 989-cylinder, 15-head, 56-sector disk model. It requires accepted parameters before CHS reads and after reset. LBA skips initialization. Rejected initial parameters publish no disk, and rejected reset restoration returns an error without reading media.

The boot-source check executes failed HDD, returning Other and INT18 Other continuations into the actual CD loader. Installed AH08/AH48 and nonzero cylinder/head reads and writes must retain native geometry and reach independent sector2080. The same producer proof runs on the other maintained ports. These models do not qualify physical controllers or disks.

Native guest observers use real interrupt services and 86Box devices. They do not set active/draft policy to manufacture a result. They export display/font/system bytes through real INT13 writes. Test keyboard stimuli use the existing 8042 injection and IRQ path. The RAM coverage helper is the committed shared fixture; input-skip cases check restoration without requiring an intentionally skipped whole-memory pass.

## Emulator dependency and limits

Installed 86Box 6.0 does not contain PB430. The retained official testing build is 10408, source commit `0847d46e37767cc1d509205fd9001b548ecd81d6`. Its executable SHA-256 is `034e876d37afc6d9b42e4055a0bb4bb122948131b185203d67c98274553c56c9`.

The official artifact URL is:

`https://ci.86box.net/job/86Box/10408/artifact/Old%20Recompiler%20(recommended)/Windows%20-%20x64%20(64-bit)/86Box-Windows-64-b10408.zip`

Extract it to `tools/deps/86box-b10408`. This preserves the installed emulator. The adapter selects this exact executable. Source contracts retained in build/deps show ACC2168 unchanged from the pinned research model, the same PB430 initializer and only an ACC3221 FDC reset/re-add/init-flag change. The native external-video fixture uses the original input at private `video/cirruslogic/cl5422.bin` with `cl_gd5422_migrated_isa`; it does not rename a donor machine or alter installed ROMs.

The ACC3221 model incorrectly requires primary UART source 1 although the data sheet and its own comments specify source 2. Correct physical DE programming therefore removes the native model's primary UART. Native display expects only the secondary UART; the independent data-sheet decoder proves both sources, real BDA entries and public INT14 traffic. The port does not change physical encoding or patch the emulator to hide this limit.

The native fixture timeout is an observation bound, not a physical POST timing claim. A timeout retains diagnosis and needs a reached-stage/CPU-progress explanation. The old installed-release missing-ROM timeouts were pre-main tooling failures, not firmware failures.

No software or emulator result proves DRAM/SRAM stability, board timing, populated cache size, electrical IRQ routing, write protect, or safe flashing. The user reports repeatable physical boot for `stock-cold-resume`, SUM32 `013A7200`. This report does not qualify later images or performance.

## Production source inventory

`src/bios.asm` includes the shared modular BIOS. Shared renderers, Setup, PC services, RAM testing and boot remain the existing owners. PB430-only tracing marks their boundaries and emits parity failure before display output. The shared option-ROM scanner skips the complete initialized video extent while retaining its selected first-segment floor and existing 2 KiB policy. Port files compose these contracts:

| Port source | Defined adapter contract |
| --- | --- |
| hardware/board-definition.inc | Board identity, standard I/O constants, EBDA hardware offsets, descriptor and test include hooks |
| hardware/startup-core.inc | `startup`, local `.post_settings` continuation, frame-free reset/memory entry and BDA/vector construction |
| hardware/board-core.inc | Shared CPU owner composition, hardware includes, `core_verify_initialization`, `board_a20_handoff`, `warm_reset`, `controlled_defaults_restart` |
| hardware/io.inc | `acc_read`, `acc_write`, `init_at_prerequisites`; AL index/AH value and OEM write delays |
| hardware/memory.inc | `memory_initialize`, `memory_probe_bank`, raw OEM map/pattern inputs; no stack before `startup.ram_ready` |
| hardware/shadow.inc | `shadow_system_bios`, `shadow_system_policy`, `shadow_external_video`, `initialize_video`; saved context/provider vectors |
| hardware/cache.inc | `cache_initialize`, `cache_initial_policy`, `cache_ranges`, `chipset_late_cache`; physical presence separate from qualification |
| hardware/chipset-core.inc | `chipset_defaults`, `chipset_valid`, record load/save and apply, CR0 CPU policy; existing shared RAM owner |
| hardware/chipset-data/ui/options.inc | Existing chipset descriptors/callbacks, availability, ordinary enum rendering, fixed onboard-video policy |
| hardware/sio-core.inc | `init_superio`, `ports_apply`, record/UI filters, UART/parallel/FDC/IDE adapters, floppy swap/capability and diagnostic queries |
| hardware/floppy-core.inc | `board_floppy_configure`, `board_floppy_perpendicular`; proven enhanced/legacy capability branch |
| hardware/ata-core.inc | Original two-slot `ata_detect_primary`, BPB/CD hardware selection and device labels |
| hardware/post-core.inc | Existing cache/bank/ROM summary hooks, no new screen owner |
| hardware/ports-setup.inc | Existing port-page labels/help |
| src/keyboard-diagnostic.inc | Shared keyboard diagnostic include |

Changes are in PB430 code/configuration/tooling/tests/docs, the shared option-ROM scanner's initial video-extent calculation and PB430-only trace points. The listing helper also recognizes emitted `incbin` rows. No UMC/VLSI/PCI register path or unfinished M919 policy hook is adopted. Original references remain unchanged.

The native check uses the generated configuration beside the candidate image, even when the root build configuration is absent. It rejects configuration dependencies from another build. It records NASM's 46 active dependency files, all active global labels and 48 required hardware/public-service symbols. It records shared-source comparison with the isolated base after newline normalization. This comparison does not reject inactive shared-source changes; acceptance checks the active emitted owners, assembled I/O and actual firmware behavior. Capstone decodes assembled IN/OUT instructions and constant-DX port selections from the actual listing. The validator rejects donor configuration indexes/PCI ports and foreign source dependencies. Separately assembled negative fixtures add UMC index I/O, PCI configuration I/O or remove a required owner. These inputs must fail the inventory guard; they are never executed as firmware candidates.


The reference-map command is `python -B pb430/tools/map_reference_roms.py`. It writes under `pb430/build/research/reference-maps`, verifies the original hashes, and assembles both complete ROM reconstructions for byte comparison. Durable text maps are in `pb430/reference/maps`. Assertions cover all83 ACC386 ROM-stack calls, PB430 inline-string returns, wrapped near targets, and real overlapping entries. Unknown indirect transfers remain explicit.

The focused stock comparison now includes early refresh/DMA I/O and963D-9687 warm-entry operations. The composed memory check rejects RAM entry before refresh/cascade setup. Warm disk checks require both the0000:7BFE early fill entry and0030:00EA final fill entry. Original ROM execution supplies the operation oracle. These checks do not simulate physical refresh decay or cache-tag SRAM.


For stock-transition and later candidates, the source comparison must not strip diagnostic instructions from9748-978D. It requires the contiguous instruction sequence and compares all activation IN/OUT operations, including any unexpected port80 writes. The failed stock-map image is rejected as a negative control. The earlier256-marker register-preservation cases do not qualify instrumentation inside transient cache mode and are removed.

For stock-timer and later candidates, compare all73 bytes of the originalCFDF-D027 IRQ0 handler, allowing only relocation of its zero-constant operand. Inject IRQ0 inside each tested STI-window boundary and reject high BIOS-memory accesses. Require restoration of the original INT08 vector after the late parent. Actual Ctrl+Alt+Del tests require the stock timer vector at the reset pulse and early warm entry, followed by the normal runtime vector after POST. These checks preserve the fixed0030 fill frame and do not model SRAM tags, CPU cache hits, or physical bus timing.

For stock-reset-entry and later candidates, require byte identity between the common-entry cache-disable prefix and original963D-964A. Also require the original cold-probe prefix8F3A-8F47 to match. This excludes the inherited WBINVD pair. Placement before modular RAM work remains an explicit adaptation. Cold POST, actual Ctrl+Alt+Del, and special shutdown-service dispatch checks cover the affected entry paths. Emulator results do not establish a cure for intermittent physical10/64 freezes.

The memory proof now counts conventional-memory writes independently of initial byte values. Cold startup must write every byte belowA0000 before reaching startup.ram_ready. The previous image fails this guard. The ram_skip_at argument injects an Esc scan at a visible-test service boundary. It must reach the production skip path and retain the normal boot continuation. Reports distinguish bytes unwritten during this reset from retained warm RAM. Actual Ctrl+Alt+Del scenarios cover both completed and skipped tests with retained cache detection. Initial zero-filled fixture memory is not evidence of hardware initialization.

For stock-cold-resume and later candidates, the original cold comparison includes E081-E0B1 andE0E6-E10B after probe/timing setup. The stock shutdown self-test executes these paths before returning to43C7. Require raw byte identity for both fragments and compare every tested cache size, CPU-cache setting, and jumper selection. The composed512KiB cold entry must match1A2C/1E5B before activation. The earlier24/7B expectation omitted the self-test reset. These checks reproduce its hardware writes but do not execute the full original shutdown self-test.

The cold adapter returns through the existing policy PUSHAD frame instead of the reference JMP DI. The proof checks every resulting stack read and requires L1 and L2 to remain disabled. This explicit inactive-cache frame adaptation does not relax the unchanged active-transition instruction, I/O, or physical-stack comparisons.

The cold SRAM probe comparison records every IN/OUT from selection of mode10h through its exit delay. It compares this complete stream with the reference, including unexpected port80 writes. The only excluded stock operations are its exact private CMOS presence/size storage sites; the port holds these facts in registers and publishes them after restoration. The first BD NMI mask and final70 unmask remain in the comparison. Component cases also reject diagnostic writes in probe mode for absent, ambiguous32/64KiB and qualified128/256/512KiB SRAM.


## Timing and recovery checks

Run the full port matrix with `python -B pb430/tools/test-port.py --case all`. The historical `fast-writes` case now runs the complete timing menu and reset checks. Also run these focused additions:

- `python -B pb430/tools/test-timing-recovery.py`: selected timings with caches off, block restoration, Fast Boot total, detected failure, pending-trial hard reset, one-retry guard, verified save, Delete/Esc and deliberate Ctrl+Alt+Del.
- `python -B pb430/tools/test-ram-order.py`: actual cold and warm POST orders RAM before floppy setup and restores stock prerequisites before late cache activation.
- `python -B pb430/tools/test-required-refresh.py`: mandatory AT refresh, removed posted writes, retained DRAM burst selection and CMOS checksums.
- `python -B pb430/tools/test-refresh-dependencies.py`: all five cache/refresh child controls and retained settings.
- `python -B pb430/tools/test-write-burst.py`: original optional-register restoration, menu dependency, Save and warm reset.
- `python -B pb430/tools/test-cache-transitions.py`: complete cold POST, cache edits in both directions, unchanged Save and Ctrl+Alt+Del, discard, canceled and rejected saves, active-record preservation and unqualified SRAM. Changed choices must run cold prerequisites before activation; unchanged choices must retain warm reset.

The model records reads and writes through real firmware instructions. It does not model electrical DRAM timing, refresh retention or cache SRAM signals. These results cannot certify the manual settings or explain every physical slowdown. The user-reported average benchmark gain is separate hardware evidence.
