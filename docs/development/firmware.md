# Shared firmware implementation contracts

This is a developer reference. Source paths beginning with `src/`, `tools/` or `tests/` below are relative to `shared/`. Operating instructions start in the [project manual](../../README.md).

Common emulator source, stock ROMs, and downloaded dependencies have [repository-root owners](../../tools/86box/README.md). Private adapters and VM state remain in each port's build directory.

Maintain reusable implementations in `shared/src/`. Ports provide board configuration and hardware policy. Do not maintain private copies of shared bodies.

| Shared source | Existing contract |
| --- | --- |
| `src/setup/layout.inc` | 80-column text UI and fixed offsets in the common firmware state segment. |
| `src/setup/chipset-fields.inc` | Existing packed menu descriptor format and numeric formatter selectors. |
| `src/setup/chipset-menu.inc` | Descriptor rendering and editing through port-provided policy callbacks and common UI helpers. |
| `src/keyboard-diagnostic.inc` | Optional PC-AT keyboard diagnostic through common print/wait helpers, KBC port constants, and diagnostic bytes at BDA addresses 04A4/04A5. |

These are shared implementations for a defined firmware contract. They do not promise compatibility with arbitrary state layouts or hardware.

`src/firmware/cache-lifecycle.inc` owns assembly-time cache phase placement. The board supplies `BOARD_CACHE_EARLY`, `BOARD_CACHE_AFTER_RAM` and `BOARD_CACHE_FINISH` expansions, and `BOARD_CACHE_RESET` names its complete reset owner. Empty phases emit no instructions. Keep temporary controller transactions, reset classification, saved-policy eligibility and context restoration inside their existing adapters.

`src/pc/cache-test.inc` provides an inline two-pass address-derived dword workload and the separate complementary word workload for adapters with that accepted contract. The dword workload preserves all registers except EAX, EDX and EDI; failure leaves EDI at the bad dword and EAX as the expected value. The caller captures the observed value. Fixed tag witnesses use distinct addresses at the same cache index within initialized scratch RAM and the selected mode's cacheable range. These startup screens do not establish electrical stability or comprehensive tag/DMA correctness.

Run `python -B shared/tests/test-cache-transitions.py --port all` after building the selected ports. The shared runner requires each adapter's complete applicable scenario inventory and propagates failed or missing results. Each port owns its hardware model, complete reference comparison and detailed results. Use `--port` for one adapter or `--self-check` for synthetic adapter dispatch and result validation without executing firmware.

Keep chipset register access and board-specific behavior outside this directory. Standard PC and PCI mechanisms belong here. A new port must provide the same helper/state contract or separate its policy before integration. The menu's policy, availability, formatting, and commit callbacks remain port-owned. Source sharing alone does not establish physical hardware support. The shared POST cursor call preserves FS, GS and the caller flags across retained VGA execution. Setup restores FS and GS and clears the direction flag before it resumes firmware drawing.

POST publishes native disk counts and parameter-table vectors before option ROMs initialize. Runtime INT13 services and parameter-table updates leave those published vectors and counts alone. A provider can use a vector as its native BIOS predecessor; the Adaptec AHA154xB uses INT46 this way. Native geometry and table contents still use the current BIOS state.

Port configuration owns vendor/model/revision, BIOS version/date, ROM size/layout, and chipset variants. Shared code must consume variables supplied by that configuration. Do not add system model or firmware-version literals to shared routines.

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

`shared/tests/dos/` owns the unchanged standalone RTC, PC hardware-state and mouse-interface inspection programs. Port commands select their output directory. These utilities do not build a firmware image or replace its native checks.

Board callbacks own A20 transitions, controller command capabilities, disk ports, floppy mapping, and mouse availability. A board without an AUX connector filters only the mouse selector after CMOS validation, preserves other settings, disables editing through the existing availability rule, and rejects INT15/C2 before any controller operation. Serial mice remain UART clients. Temporary physical stage/IRQ/footer tracing is not part of the shared core.

Shared manual conversion and verification live in `tools/convert-docs.ps1` and `tools/verify-docs.ps1` here. Root commands select generic references; port wrappers add their board documents. Shared `tools/build-cleanup.ps1` owns process, path, reparse and preview safety. Each port owns artifact retention; root `tools/clean-build.ps1` dispatches maintained port commands.

`src/pc/processor.inc` selects cache instructions and byte swapping for the configured processor class. `BOARD_CPU_386` omits 486 cache instructions and reserved CR0 cache bits. `BOARD_A20_READ` and `BOARD_A20_WRITE` select board routines with AL as a gate token. The default preserves the existing port92 path. The token's bit0 follows that default's reset convention, so an8042 adapter must translate its opposite reset polarity. The adapter owns queued keyboard input and gate restoration. Optional paired Stop Grant macros extend APM Idle in all three modes. Ports without a provider retain HLT. A provider must release STPCLK before IRQ delivery and can decline only before consuming a wake.

`src/pc/primary-ata.inc` owns the existing two-position primary ATA detector and boot-sector ownership callbacks. `src/pc/chs-geometry.inc` owns the common Auto geometry and BPB validation. Explicit geometry takes precedence. `boot_candidate` clears `B_DRIVE` before each target selection, so a failed HDD cannot lend its source identity to CD or Other. The actual ordinary read then records its drive.

`src/pc/ata-identify.inc` owns IDENTIFY polling for both firmware compositions. An absent ATA position that returns00h orFFh exits promptly. A known ATAPI identification stage retains the full startup wait, including an initial zero status. Busy and non-progressing present devices retain their bounded wait.

Ports can select `BOARD_FAST_BOOT_SETTING` through their own saved policy. The shared RAM-test owner skips the extended sweep while retaining memory publication and the separate cache qualification. `BOARD_ATA_DWORD_IO` permits ordinary data reads/writes through the shared16/32-bit PIO helpers. A port's `BOARD_IDE_32BIT_POLICY` supplies the saved request. IDENTIFY, packet, ECC and odd word counts retain word transfers. Sorted IDE choices map display positions to the existing stored translation, block and EDD encodings.

`src/pc/pci.inc` owns VGA expansion-ROM aperture measurement and decode release. The usable aperture can exceed the validated legacy header. Board adapters retain shadow register writes and pass the resulting extent to later ROM discovery. The shared PCI helpers restore temporary command/BAR changes. This prevents a mirrored VGA image being initialized as an unrelated C800 ROM.

`src/firmware/ide-pio.inc` owns PIO0 through PIO4 capability decoding, SET FEATURES completion and pending-channel guards. Auto selects the fastest device mode within `BOARD_ATA_PIO_MAX` (0..4). Every maintained port sets this ceiling explicitly. Discovery, reset and packet continuation use the service even without a saved PIO menu setting. `src/pc/ata-reset.inc` restores both ATA/packet peers before later data commands. The effective accepted mode appears in POST. Before issuing SET FEATURES, the shared owner requires BSY and DRQ clear but ignores ERR from the previous command. An optional SET MULTIPLE abort must not prevent a new mode command. Completion of SET FEATURES itself still rejects ERR; unresolved busy or data phases still block replacement commands until reset.

The four-position ATA inventory binds saved policies to physical channel/master/slave positions. Device absence never shifts those settings. Setup can edit every fixed position before discovery without probing the bus. BIOS hard-disk numbers still enumerate only detected, enabled ATA disks. The saved record format remains unchanged. The two-position include retains its existing physical binding.

`BOARD_SETTINGS_LEGACY_CHIP_TAG` lets an adapter identify an older chipset record that owned the packed format's marker bytes. Exact packed markers retain precedence. The adapter must validate the old record checksum and translate its retired fields; recognizing the format alone does not make the settings valid.

`src/setup/defaults.inc` owns the normal defaults: CD, floppy, hard disk, and enabled supported caches with WB where available. Valid saved selections and the separate recovery policy retain their own authority. Adapters translate the common request without adding unsupported hardware modes.

The `BOARD_BOOT_HANDOFF` callback runs at the INT19 bootstrap entry, including direct software restarts. Board A20 adapters preserve the previous gate token around extended-memory copies. Extended RTC adapters can map logical configuration bytes outside the physical RTC. Their checksum and interrupt contracts remain separate from cache eligibility.

`src/firmware/floppy.inc` initializes the global AT DMA cascade before the optional floppy-controller gate. Disabled floppy policy issues no controller commands, transfer programming or IRQ6 enable. Other ISA DMA devices retain the global cascade path.

`src/pc/ata-status.inc` owns ready, data-request and completion polling. Completion requires BSY and DRQ clear. Intermediate MULTIPLE blocks wait for their next data phase. The shared ATA interrupt owner acknowledges completion. Public disk polling permits interrupts while bounded PIO blocks retain their existing interrupt exclusion.

Port configuration supplies identity, versions, ROM geometry and hardware selectors. Shared source consumes these values rather than model literals. `shared/tools/rom.py` builds and verifies configured images. Independent checksum regions and the overall checksum retain their declared ownership.

The common Setup renderer owns menu interaction. Each editable setting has one menu owner. Floppy-controller policy belongs in Drives, memory timing in Chipset > Memory, and parallel-port DMA in Devices. Descriptor counts, groups, help and navigation must move together.
