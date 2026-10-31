# PC-Chips M919 port

This port targets PC-Chips M919 revisions1.5 and3.4. The revision3.4 reset and floppy limitations below remain unresolved. The shared firmware provides POST (power-on self-test), Setup and native DOS disk/floppy services. Board revisions and fitted components still require separate physical observations.

The user runs an AMI BIOS dated 05/06/96 and reports many bugs. The user identifies `reference/9190506.BIN` as that baseline. Matching ROM labels alone do not establish board compatibility.

## Physical baseline

The tested board is revision 1.5 with an AMD 5x86 on a 33 MHz bus, 16 MiB RAM, UM8881F, UM8886BF and UM8663BF. The user reports a selected 512 KB SRAM population passing Memtest and running Quake with write-back enabled. Twelve rejected chips do not establish twelve defective parts. Some passed a programmer or worked in other boards. Memtest random sequences exposed faults missed by the short POST test.

S3 ViRGE and ViRGE/GX are compatible with normal display and DOS operation. The user confirmed the reset display fix in0.5.4. Normal reset entries blank the old VGA display before hardware setup and restore it after successful VGA initialization. AT shutdown-service continuations keep their existing display state. Trio64 also worked. The precise final SRAM part/date-code population and test duration are not recorded. Preserve its placement and settings.

The revision3.4 test unit has a cache module and a reported UM8670F Super I/O. Other revision3.4 boards can have UM8663. With version0.9.2, the user confirms PIO4 and stable settings on the test unit. Relaxed Setup timing temporarily restored its floppy, but the fault returned. The revision3.4 floppy remains unresolved. VLB operation was also validated and was much faster than PCI in that setup. These reports do not qualify every bus clock or every cache module.

Revision1.5 uses ordinary socketed SRAM, not the later proprietary cache module. Cache size and bank organization are measured. Normal defaults request L1 and L2 enabled with WB policy. The controller sequence primes clean tags in WT before switching to WB. Failed or absent cache remains off. Safe recovery disables both caches. A valid saved WT/off choice remains authoritative.

The board has serial mouse connections and no PS/2 mouse connector. `platform.aux_bios_supported` defaults to false. Setup hides PS/2 Mouse, unsupported extra serial address pairs, and ISA Serial Discovery. Hidden controls are also excluded from keyboard navigation. A valid older CMOS record keeps its other parameters; only that unavailable selector is normalized. The AUX initialization and INT15/C2 interface issue no mouse-controller commands. Serial ports remain available.

## Source boundary

`src/bios.asm` composes the complete donor core from repository-root `shared/src/firmware/`. That core owns POST presentation, visible RAM testing, Setup/CMOS defaults and recovery, halt/error tones, generic BIOS services, disk/floppy read-write, RTC/input/mouse, boot policy, APM, and El Torito. Generic donor bodies remain unchanged where they have no board access. Presario also consumes the shared Setup, IDE, ATA polling and IRQ14 owners. Supplied reference ROMs remain unchanged.

`src/hardware/` supplies UMC startup/RAM probing, PCI board policy and external VGA initialization, shadow/cache reporting, CMOS chipset policy, UM8663 port routing, native IDE channel selection, floppy drive/motor mapping, and reset. Root `shared/src/pc/pci.inc` owns generic PCI access, enumeration, resource allocation and INT1A. It does not issue donor VLSI, SMC, or Compaq VGA-offset accesses. `port.json` supplies identity/version/date, ROM geometry, and hardware policy through generated `CFG_*` variables. The consumed porting seeds and former partial POST shell have been removed.

The physical image is128 KiB mapped at E0000. The complete64 KiB logical core lives at F0000; its reset vector enters F000:0000 directly. The lower64 KiB remains padding. RAM is detected before stack use. The donor state schema is retained in an 8 KiB EBDA; BDA base memory and buffer protection match that reservation. Hardware metadata occupies separate slots within that reservation.

The RAM adapter measures both physical bank pairs, chooses supported single/paired and sided organizations, and sorts the two regions by capacity. It validates address independence and restores its probes before publishing the map. Asymmetric addressing is tried only on the documented PCI silicon revision 04h. Unknown silicon still uses ordinary bank organizations. Unequal modules use the largest validated map; unsupported extra capacity is not added to the report. Bank numbers 0 through 3 describe the mapped chipset banks. Physical socket wiring still needs a matching observation.

Installed and usable extended counts have separate 32-bit state fields. The RAM test, POST, Setup, and diagnostics use those fields. INT15/AH88 and CMOS extended-memory words have an explicit 64512 KiB (63 MiB) ceiling. They never wrap. The modeled two-region maximum is 256 MiB; the shared count readers keep the word contract for ports that have not adopted wide publication.

The processor label uses the [shared recognition list](../shared/README.md). Recognition does not imply board support or derive clock, voltage or multiplier. Cache qualification uses the shared short SRAM patterns and address witnesses inside the complete non-M919 reference controller sequence. Ordinary cache and tag-address checks follow sizing. Summary reports measured capacity and effective WT/WB/Off state. Failures retain their stage, address, expected value and read value. The chipset record uses tag 57h; incompatible older records fall back to defaults without writing CMOS on load. There is no persistent cache-test certificate.

The measured Bank 0 byte map is U23=D24-D31, U22=D16-D23, U21=D8-D15 and U20=D0-D7. Thus Err-Bits `00080000` and `00100000` identify U22's lane; `02000000` and `04000000` identify U23's lane. Each pair of hex digits represents eight data bits. Bank 1 uses U11-U14; only its D24-D31 mapping to U14 is confirmed. U19 is TAG. A lane result alone does not distinguish a chip from its socket, trace or timing.

IDE discovery retains all four physical positions. Shared services number enabled ATA disks contiguously as80h through83h and can boot a CD on either channel. Setup always names the fixed Primary Master, Primary Slave, Secondary Master and Secondary Slave positions. Each position uses its matching saved policy, even when no device is attached. Version0.9.7 removes the earlier detected-order rebinding without changing the saved byte format. Each device has its own complete geometry, block, EDD and32-bit transfer settings. POST labels show the physical channel and position. Reset restores only the affected channel. Boot remains the established CD/floppy/first-hard-disk policy. Floppy swapping maps both commands/motors and returned unit identity in the M919 adapter.

PCI BIOS advertises bus zero only. BARs must fit the configured I/O pool through 10000h or MMIO pool `pci_memory_base` through exclusive `pci_memory_end`. Unsupported resources remain undecoded. BF IDE uses readback-qualified compatibility mode. Fixed-native, mixed, ignored mode writes and rejected I/O resources remain unusable without AF fallback or legacy task-file probes. Saved Enabled remains a policy request. Slot routing uses the identical board interrupt tables from the four original M919 ROMs. Auto assignment excludes active onboard ISA devices. Manual choices that conflict with those devices remain unassigned. Active onboard ISA devices use edge triggering, including after a previous PCI assignment. Compatibility IDE reserves IRQ14/15 only while enabled and usable. Wider physical slot-routing coverage remains unmeasured.

Valid VGA providers can declare 32, 48 or 64 KiB. Shared PCI mechanics also measure the VGA expansion-ROM aperture. The adapter shadows the larger usable extent and starts later ROM discovery after it. A 32 KB header inside a 64 KB aperture must not expose a second VGA image at C8000. Temporary PCI command/BAR changes are restored; runtime decode is disabled after shadowing. HB54 uses 02h through 32 KiB, 06h through 48 KiB, and 0Eh through 64 KiB. Bits 04h and 08h select separate 16 KiB regions at C8000h and CC000h. The UM8663 startup retains the configured whole-register C0/C1 seeds. Later saved routing clears the unused game decoder at C0.20 and preserves the remaining upper bits and C1 mask30h. Startup and later FDC wake both apply C2=(old & DFh)|81h and preserve unrelated bits. Bit0 is the documented initialization value; its electrical purpose remains unknown. ECP DMA Channel owns only C3.40 when the parallel port is enabled in ECP mode; other modes retain the selector. C4 remains unchanged.

The floppy adapter detects enhanced-controller commands before using them. Legacy controllers use the standard command sequence. Failed POST seeks retain the normal controller/version/stage/status evidence. After RAM sizing, the adapter releases fast A20 so HIMEM can control the 8042 gate; INT15 memory moves preserve the previous gate state. Keyboard handoff retains queued input and checks the board command policy. Deliberate warm reset clears the CMOS shutdown-service byte before the reset pulse. Real-mode reset retains its write-back flush and fast-A20 restoration. Protected/V86 entry avoids privileged cache instructions and uses the original KBC D1/DF/FE sequence. Direct fixtures cover that branch and bounded controller timeouts. Microsoft EMM386 Ctrl+Alt+Del still hangs on the revision3.4 test unit. XMGR and JEMMEX work there, and revision1.5 resets normally. The adapter change is not a confirmed physical cure.

The shared floppy transfer and IRQ owners retain their established behavior. Global AT DMA cascade initialization now precedes the optional FDC gate. This lets other ISA DMA devices work when the floppy controller is disabled. The user confirms restored digital sound in that configuration. PB430 already supplied the cascade through its earlier refresh owner. All four supplied AMI DMA routines also program DMA without software cache-flush instructions. CPU and bus-master coherence is a hardware contract; the software model distinguishes WT/WB CPU policy and hardware snooping. Its pass does not establish the physical board's cache wiring. New changes need a demonstrated requirement or failure and source-backed justification. Chipset differences stay in adapters; proven improvements can enter shared code.

## Setup defaults and timing

Normal and F9 defaults use the shared CD, floppy, hard-disk boot order. Valid saved settings remain unchanged. The45 chipset controls are grouped as CPU and Cache, PCI Bus, PCI Interrupts, Local Bus, ISA Bus, Memory, and ROM Shadow and Cache. Choices are sorted for display without changing saved encodings. Defaults select three DRAM waits, 3-2-2-2 L2 reads, FPM, normal refresh and no posted writes. They do not infer the bus clock or installed SRAM speed.

The controls include host posting waits and burst writes, PCI posting, device response, locking, parking, master preemption, parity, explicit clock ratios, four interrupt-link assignments, IDE trigger mode, local-device sampling, resource locking, ROM shadows and video-ROM cacheability. Cyrix linear burst and AMI load/store tuning require positive processor identification. Device-number mapping is limited to the qualified host revision. Mandatory system/VGA shadows remain automatic. Fast Boot uses the shared RAM-test policy. IDE block mode and optional32-bit ATA transfers use shared data-transfer helpers. Four simultaneous device records are implemented in0.6.0. Version0.9.2 offers individual PIO0–4 limits. Auto selects the fastest mode permitted by the drive and request. The usable, enabled673A PCI IDE function supplies the complete original-board recipe in physical device order, including all seven fields through4Fh. No exact silicon revision or33MHz selector blocks the supported modes. Modes3/4 require valid drive IORDY capability, cycle time and accepted SET FEATURES completion. The user confirms PIO4 on revision3.4; electrical margins at every supported clock through50MHz remain unmeasured.

M9190.6.0 loads older two-device settings without writing CMOS. The additional devices default to Auto and enabled. Save and Exit migrates the complete extension to a checked compact format. IDE, onboard ports and chipset settings retain separate checksums. Other ports retain their existing two-device format. A RAM or cache recovery marker uses the selected format and cannot overwrite device geometry. The first save in0.6.0 is a one-way format change: older ROMs fall back to defaults if subsequently installed.

PIO requests retain their old two-bit plane and append one high bit per device. Older packed records keep their explicit selections. Values6/7 are rejected. Save and reload preserve the ECP selector, four disk records and ports settings. The former IDE timing-clock bit remains opaque compatibility data in its original packed position; it has no menu or hardware effect.

The selected PCI VGA provider also selects the original AMI normal bus policy. This raised the user's Landmark and Doom results. The user accepts the resulting PCI throughput and defers further PCI tuning. The qualified host receives the normal cache-line and latency header settings. The subsequent host-header change produced no reported performance gain. An explicit PCI ratio remains independent of the AMI automatic CPU-speed tables.

The [tuning omissions report](docs/research/m919-registers.md#tuning-omissions-in-candidate-053) distinguishes unfinished controls, automatic policies and unqualified register meanings. Shared APM is present. Chipset power management and SMM remain deferred. When Memory Parity is selected, Fast Boot still initializes extended-memory parity before reporting is enabled. Version0.8.0 completes the ordered host/bridge parity-reporting controls after RAM initialization, including Full, Fast Boot and Esc paths. Parity-capable physical memory remains unqualified. The nonexistent Game Port control is removed. Its old saved bit remains opaque compatibility data. The decoder stays off. Parallel ECP DMA Channel appears under Devices, directly after Parallel Port Mode, with choices1/3 and default3. Devices has five controls. The DMA choice is unavailable while the parallel port is disabled or outside ECP mode, but its saved value remains intact. Floppy Controller appears only under Drives. DRAM Read Waits appears only under Memory. The ISA view has three fields. No new ECP transfer engine is supplied.

The old profile and persistent-certificate design is not part of this replacement. Remaining controls and wider timing qualification stay separate. L2 qualification runs after the RAM test; runtime activation remains after the final Setup gate. Both policies retain the selected reference's seven tag bits plus dirty, with a cacheable extent of capacity times 128. A512 KB cache therefore covers64 MiB in this sequence. Installed RAM above the cacheable range no longer disables a successfully qualified cache. The full detected RAM map remains available. Qualification, geometry and the minimum span needed for the complete reference fill remain required. The fixture checks separate data below and above the cacheable boundary; it does not establish physical upper-range bypass. Do not extend the tag format merely because WT could use another format.

Doom can invert VLB graphics colors and crackle during sampled digital sound on the revision1.5 board. The same cards reproduce this with the OEM BIOS and with both caches disabled. Music-only, General MIDI and PC-speaker effects work. Disabling the FDC previously stopped digital sound and masked the color fault. The shared cascade repair restores sound, and the color fault returns. No register workaround is established. Further PCI and VLB tuning remains deferred.

The user accepts the unresolved revision3.4 EMM386 reset and recurring floppy faults for publication. Version0.9.7 fixed physical IDE policies and the preceding Setup ownership changes have focused fixture coverage, but no separate physical UI confirmation. These limits do not invalidate the recorded PIO4 and selected cache results.

## Shared RAM test

`shared/src/firmware/ram-test.inc` owns the visible RAM test. Ports supply the detected capacity and reserved state area. The test backs up 2 KiB at a time into excluded EBDA scratch, tests every usable dword with three full pattern passes, and restores the original bytes. Separate address witnesses detect tied low address lines. CPU cache stays disabled during the test.

The owner excludes live firmware state and the VGA/ROM window. It services the existing keyboard owner every 16 KiB or less and updates progress every 64 KiB. Esc skips, Delete requests Setup, and Pause retains the interrupted test until a fresh make. All exits restore the original machine gates and context before returning or using the existing recovery owner. Presario uses its configured block and scratch bounds in the same shared owner.

Run `python -B m919/tools/test-hardware.py --case ram-test` for coverage, randomized restoration, boundaries, failures, address aliases and native interaction checks. The comparison build uses the checked-in RAM baseline, without private Git history or mutable output from another fixture. Recorded instruction counts and host execution times are software measurements. They do not establish physical POST time or SIMM wiring.

The user reports a much faster physical RAM test with responsive keyboard control and working memory detection/bank reporting. The exact flashed image hash was not supplied. This confirms the observed behavior in the tested configuration; it does not establish every socket layout or timing margin.

## Reference ROMs

The four unique supplied files are 131072 bytes. Preserve them unchanged. The user removed the byte-identical `9-15-98.rom` duplicate. Its original identity remains in Git history.

| File in `reference/` | Decoded release date | SHA-256 |
| --- | --- | --- |
| `3-6-96.BIN` | 03/06/1996 | `42A204906D53CF31DA4FBEE790C26F692F52FDF3D438362A11A07E7D5D6C1886` |
| `9190506.BIN` | 05/06/1996 | `263077F3F8973A3A2BE5F9FC8A2428D72182B8BC41FA7292405C828FD5E1E686` |
| `9190914S.ROM` | 09/15/1998 | `AA34FCC7FFEC6011BF55F273F28D396242D41E7D318364A4DE997A450AAB4E13` |
| `9191016s.rom` | 10/16/1996 | `A4769633DAC24933D41703210FB0A89808630BEF3BD33C0D87253ED4BCC86D8F` |

Each image starts with `AMIBIOSC` and contains `AMIBIOSP`. The raw 10/10/94 and 02/02/95 strings identify AMI core generations. The release dates above come from the natively decoded main core at offset 813Ah. The baseline selection also agrees with the user's identification.

The byte sum over each full image is nonzero. That observation alone does not establish an AMI checksum error. Determine the checksum regions before judging integrity.

Use every AMI image as evidence. An AMI write establishes what firmware did, but does not prove what the register means or whether that behavior is correct.

The later S images retain the same forced-hit cache capacity/bank probe and normalized late cache-test instructions. The 1998 image removes the 36-byte discovery-exit block that saves CMOS F6h and clears HB50; it retains the discovered disabled map instead. The late test has limited coverage because its loops decrement CX after loading ECX. Intent and physical impact remain unknown. Independently, the user tested both later S ROMs successfully on the revision 1.5 board. This is observed boot compatibility for that hardware, rather than a conclusion from matching routines.

A displayed size or register readback cannot establish usable cache. Writable opposing data and independent alias behavior establish presence; there is no separate fake-cache classification. The register ledger separates those requirements from the limited AMI evidence.

## Chipset evidence

Use the [local pinned UMC manual](../reference/chipsets/umc/um888x/UMC_chipset_technical_reference_manual_RE.md) as a starting point. [SOURCE.md](../reference/chipsets/umc/um888x/SOURCE.md) records its upstream commit, license, and SHA-256. Its main hardware observations concern A-Trend ATC-1415 and Biostar MB-8433UUD-A. Its host-bridge register description covers tested PCI revision 4.

The user confirms the chip families listed above. Read PCI revision IDs and check the physical wiring on revision 1.5. Distinguish UM8886AF indexed IDE access from the BF/N PCI IDE design. Confirm the actual Super I/O variant. Do not infer those parts from later M919 boards.

The maintained [register ledger](docs/research/m919-registers.md) separates observed AMI writes, manual claims, emulator behavior, and unresolved physical meanings. The stock emulator does not model RAM geometry or most timing registers. A successful emulator RAM test cannot validate physical SIMM organization.

Require independent evidence for a disputed meaning. A match between AMI and 86Box can reflect the same inherited assumption. Prepare upstream corrections with a minimal reproducer and board-specific limits. Submit them only when the user requests submission.

## 86Box target

The [86Box M919 initializer](https://github.com/86Box/86Box/blob/858f4ac0bbc487d281748e3252025f11fd22cbb9/src/machine/m_at_socket3_pci.c#L1451) uses this model:

- Machine identifier `m919`.
- ROM path `roms/machines/m919/9190914s.rom`, 128 KiB mapped at `0xE0000`.
- PCI configuration type 1. Host bridge at device `0x10`, southbridge at `0x12`.
- PCI slots `0x0C`, `0x0D`, and `0x0E`, with the initializer's interrupt rotation.
- UMC HB4, UM8886AF, UM8663BF, and SST 29EE010 flash.

The installed 86Box executable reports file version 6.0. The linked upstream source is pinned separately. Check the installed model before relying on newer source behavior.

Keep private emulator ROMs, NVRAM, disposable disks, listings, and logs under `m919/build/`. Do not replace global emulator ROMs or the Presario build. Start with the stock M919 model. The user directs us to disregard chip and board revision differences until testing shows a concrete problem. Emulator results remain distinct from physical results.

Use [shared emulator resources](../tools/86box/README.md) at `tools/86box/`. Generic source, ROM inputs, helper implementations, and downloaded dependencies must have repository-root owners.

During porting, separate board operations from reusable PC services. Supply model identity, board revision, BIOS version/date, ROM size/layout, and chipset variants through port configuration variables. Shared routines must consume those values. Broader Presario firmware refactoring remains later work.

Emulator success does not replace revision 1.5 hardware testing.

## AMI tools

Supply your own licensed AMI analysis tools. Version numbers are not a chronological compatibility ranking. Start format recognition with these installed candidates:

- `AMIBCP 6.24/AMIBCP.EXE`.
- `AMI.ROMUtils.v627.10/627.10/EXE/`, including `ROMINFO.EXE` and `RETRIV.EXE`.
- `AMIBCP 7b12/BCP7B12.EXE` and `AMIBCP 7.60.04/AMIBCP76.exe`.

ROMINFO 6.28t and RETRIV 7 were copied into a private DOS fixture. That AMI boot did not reach the tools, so compatibility remains unproven. The offset-zero AMI94 header and uncompressed startup tables can be inspected directly. Root `shared/tools/ami94.py` executes each image's embedded decompressor in isolated memory, with an instruction budget. It checks directory bounds, native output placement, signatures and the reset vector. The known core outputs are pinned by hash. No original per-module checksum was identified. The earlier synthetic LH5 wrapper's data error does not invalidate the independently obtained native bytes. Give tools working copies under `m919/build/`. Keep the original tools and unique ROMs unchanged. Do not run flash utilities for module inspection.

Do not assume that a recent MMTool or UEFI utility understands this ROM generation. If a tool rejects the header, investigate the format before trying edits. Avoid linear disassembly of compressed payloads as if they were instructions.

## Work and commands

Build a bench image with:

    powershell -NoProfile -File m919/tools/build.ps1

The fixed image is `build/baios-m919.bin`. Complete candidates follow the [repository naming policy](../docs/repository-layout.md). `build/LATEST.txt` identifies the current bench image and last completed candidate. Emulator, fixture and source-review results do not replace physical testing of a new image.

Current replacement checks are:

    python -B m919/tools/manual_proof.py
    python -B shared/tools/ata_completion_proof.py m919/build/baios-m919.bin
    python -B shared/tools/checkpoint_proof.py m919/build/baios-m919.bin
    python -B tools/verify-rom.py m919 --image build/baios-m919.bin

The manual proof entry point includes settings/save/reload, VGA initialization through later ROM discovery, ordinary-cache failure rejection and supported cache/CPU controls. The ATA proof enters public INT13 with interrupts initially clear, services the shared IRQ14 owner while polling, and checks bounded PIO exclusion and delayed completion. The short `build/diagnostics/L2CHECK.COM` tests only its DOS-owned allocation. Its I0 result does not qualify all SRAM cells or timing margins. Memtest and real DOS workloads remain necessary hardware observations.
