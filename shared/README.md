# Shared firmware source

Generic Python helpers live in `shared/tools/`: VHD inspection, FAT16, floppy/network fixtures, configured NASM ROM building/verification, and managed emulator execution. Existing port entry points forward to these implementations. Presario fixture commands retain their port-specific output restrictions and configuration policy.

Common emulator source, stock ROMs, and downloaded dependencies have [repository-root owners](../tools/86box/README.md). Private adapters and VM state remain in each port's build directory.

Maintain reusable implementations in `shared/src/`. Ports provide board configuration and hardware policy. Do not maintain private copies of shared bodies.

The Presario currently consumes these files through forwarding includes at its original source paths. Its existing `-I presario-800/src/` include root resolves the forwarding paths. The M919 entry must add `shared/src/` to its NASM include roots.

| Shared source | Existing contract |
| --- | --- |
| `src/setup/layout.inc` | 80-column text UI and fixed offsets in the common firmware state segment. |
| `src/setup/chipset-fields.inc` | Existing packed menu descriptor format and numeric formatter selectors. |
| `src/setup/chipset-menu.inc` | Descriptor rendering and editing through port-provided policy callbacks and common UI helpers. |
| `src/keyboard-diagnostic.inc` | Optional PC-AT keyboard diagnostic through common print/wait helpers, KBC port constants, and diagnostic bytes at BDA addresses 04A4/04A5. |

These are shared implementations for a defined firmware contract. They do not promise compatibility with arbitrary state layouts or hardware.

Keep chipset register access and board-specific behavior outside this directory. Standard PC and PCI mechanisms belong here. A new port must provide the same helper/state contract or separate its policy before integration. The menu's policy, availability, formatting, and commit callbacks remain port-owned. Source sharing alone does not establish physical hardware support.

Port configuration owns vendor/model/revision, BIOS version/date, ROM size/layout, and chipset variants. Shared code must consume variables supplied by that configuration. Do not add system model or firmware-version literals to shared routines.

`src/pc/` owns shared state definitions, PIC/PIT, keyboard, timer, text, and RTC services extracted from Presario. KBC output/command policy and RTC century/NMI choices are port constants. Its assembly contract remains the original helper/state contract. Presario's hardware warm reset remains port-owned.

`src/firmware/` owns the complete Presario donor shell used by M919: POST/Setup, RAM test and recovery, generic disk/floppy services, boot/CD policy, mouse, APM, and identity. Board callbacks isolate hardware access and controller selection. `src/pc/cpu.inc` supplies guarded vendor-aware CPU naming, and `src/pc/option-rom.inc` supplies bounded VGA validation/entry. Consumed partial ATA/FDC/POST copies were removed.

`src/pc/pci.inc` owns bus-zero configuration access, complete advertised-function enumeration, bounded endpoint BAR allocation and PCI BIOS INT1A. Ports supply the existing state offsets, I/O/MMIO pool bounds and three direct callbacks: `board_pci_device`, `board_pci_irq`, `board_pci_router`. Command writes preserve unrelated command fields and write-one-to-clear status. A rejected BAR disables its whole decode category, including earlier allocated BARs. Bus mastering remains off. Configuration requests reject other buses, out-of-range offsets and misaligned words/dwords before I/O. IRQ wiring, chipset routing, IDE compatibility ownership and VGA shadow controls remain port-owned.

CPU recognition uses writable EFLAGS.ID, all twelve vendor bytes and a leaf-zero maximum of at least one before reading the signature. It preserves all registers except returned SI, including upper ESI, and all EFLAGS. It does not configure a CPU or establish a port's electrical support. The shared finite list covers these documented family/model codes:

| Vendor | Family 4 | Family 5 |
| --- | --- | --- |
| Intel | Models 0/1 DX, 2 SX, 3 DX2/487/OverDrive, 4 SL, 5 SX2, 7 DX2, 8/9 DX4. Type 1 identifies OverDrive. Type 1 model 8 specifically identifies DX4 OverDrive (`486DX4 OD`). | Models 1/2 Pentium, type 1 OverDrive; type 1 model 3 P24T; model 4 MMX, type 1 MMX OverDrive. |
| AMD | Models 3/7 DX2, 8/9 DX4 or 5x86, E/F 5x86. | Models 0..3 K5, 6/7 K6, 8 K6-2, 9 K6-III, D K6-2+ or K6-III+. |
| Cyrix | Model 4 MediaGX. | Model 2 6x86 or 6x86L, model 4 GXm. |
| UMC | Models 1 U5D, 2 U5S. | None in this list. |
| Centaur | None in this list. | Model 4 WinChip C6, model 8 stepping 0..6 WinChip 2, 7..9 2A, A..F 2B; model 9 WinChip 3. |
| NexGen | None in this list. | Model 1 Nx586. |
| Rise | None in this list. | Models 0/2 iDragon, 8/9 iDragon II. |

Intel Pentium type-zero signatures cannot exclude an OverDrive product. Ambiguous entries retain both possible names or a common product name. AMD signatures do not establish MHz. Unknown vendors and leaf-zero-only processors return Unknown. Unknown signatures also return Unknown, except Intel type1/family4 retains the proven generic `486 OverDrive` type identity. Its documented model8 gets the specific DX4 OverDrive label. Without CPUID, the AC toggle distinguishes 386 from 486 or later (`486+`). The documented 5/2 division-flags test identifies legacy Cyrix after the 486-or-later gate. Early SLC/DLC manuals send FE/FF outside the CPU, so this path retains `Cyrix 486+ class` and issues no configuration-port probes or writes.

The primary tables are [Intel AP-485, tables 3/4](https://datasheets.chipdb.org/Intel/x86/CPUID/24161817.pdf), Intel 272771 section 4.1, [AMD 19720C figure 4-1](https://datasheets.chipdb.org/AMD/486_5x86/19720C.pdf), [AMD 20734 revision 3.12 table 3](https://kib.kiev.ua/x86docs/AMD/AMD-CPUID-Spec/20734-r3.12.pdf), AMD 23913 table 1, and [Cyrix Detection Guide 1997 table 1 and 5/2 method](https://www.bitsavers.org/components/cyrix/appnotes/Cyrix_CPU_Detection_Guide_1997.pdf). Supplemental guarded identities use pinned Linux [UMC](https://github.com/torvalds/linux/blob/v2.6.12/arch/i386/kernel/cpu/umc.c), [NexGen](https://github.com/torvalds/linux/blob/v2.6.12/arch/i386/kernel/cpu/nexgen.c), [Rise](https://github.com/torvalds/linux/blob/v2.6.12/arch/i386/kernel/cpu/rise.c), and [Centaur](https://github.com/torvalds/linux/blob/v6.12/arch/x86/kernel/cpu/centaur.c) tables. UMC's twelfth vendor byte is NUL. The shared detector does not use legacy NexGen probes, feature-unhiding, MSR writes, or family 6 and later catalogues.

M919 `port.json` generates `CFG_*` NASM variables through `shared/tools/rom.py`. Root commands `tools/build-rom.py <port>` and `tools/verify-rom.py <port>` use that configuration. The selected port supplies its assembly entry and hardware owners. Model/version/date literals belong only to port configuration.

M919 consumes the root donor core directly with UMC adapters. The existing Presario source is retained for later adoption. Generic native fixtures live in `shared/tests/firmware/`; board fixtures belong to their ports.

`shared/tests/dos/` owns the unchanged standalone RTC, PC hardware-state and mouse-interface inspection programs. Port commands select their output directory. These utilities do not build a firmware image or replace its native checks.

Board callbacks own A20 transitions, controller command capabilities, disk ports, floppy mapping, and mouse availability. A board without an AUX connector filters only the mouse selector after CMOS validation, preserves other settings, disables editing through the existing availability rule, and rejects INT15/C2 before any controller operation. Serial mice remain UART clients. Temporary physical stage/IRQ/footer tracing is not part of the shared core.

Keep original include paths as forwarding files when existing consumers need them. Before changing a shared body, inspect every port caller and run its relevant checks. Source relocation must preserve complete assembled Presario ROM bytes, including diagnostic builds.

Shared manual conversion and verification live in `tools/convert-docs.ps1` and `tools/verify-docs.ps1` here. Root commands select generic references; port wrappers add their board documents. Shared `tools/build-cleanup.ps1` owns process, path, reparse and preview safety. Each port owns artifact retention; root `../tools/clean-build.ps1` dispatches maintained port commands.

`src/pc/cache-test.inc` owns the short direct-SRAM workload: two complementary word-pattern write/read passes and retained unique address witnesses across the detected span. The board adapter supplies safe SRAM access, capacity, scratch ownership, reference controller transitions and result publication. PB430 is the first consumer; this does not establish a shared phase or reset driver for all ports.

`src/pc/ram-test-state.inc` owns normal-startup marker classification. An unfinished test does not create a detected-memory-error notice. Explicit pending notices remain pending. Adapters retain their reset gates and RTC access; PB430 only clears its unfinished marker at that entry, while Presario retains its existing broader startup placement.

`BOARD_POST_RAM_ROW` selects the live RAM counter and status row. Its default preserves existing layouts. PB430 selects row6, leaving a blank row after L2 and placing the bank list on row7.
