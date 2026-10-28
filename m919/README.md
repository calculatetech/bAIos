# PC-Chips M919 port

This port targets the user's PC-Chips M919 revision 1.5. The first deliverable uses the complete Presario firmware shell and must complete POST (power-on self-test), provide Setup, and boot DOS through native disk/floppy services.

The user runs an AMI BIOS dated 05/06/96 and reports many bugs. The user identifies `reference/9190506.BIN` as that baseline. Later board revisions and ROM labels do not establish compatibility with revision 1.5.

## Physical baseline

The user reports an AMD 5x86-133, one 16 MiB SIMM, PCI graphics, and a 3.5-inch 1.44 MB drive A. The installed cache is socketed 512 KiB 15 ns SRAM. After repair of a bent socket pin and replacement of U23 and U14, the user reports successful bAIos qualification at 512 KB WT. The adapter requests validated cache enabled in Write-Through mode by default. Write-Back remains selectable. Hardware stays in Write-Through before qualification. The adapter primes clean tags in Write-Through before switching to requested Write-Back for testing and runtime use. Absent or failed SRAM remains disabled. Revision 1.5 does not use the later proprietary cache module. Jumpers select cache size and CPU electrical configuration. Chip markings are UM8881F, UM8886BF, UM8663BF, and M5818. Revision 1.5 has four 72-pin SIMM sockets, labeled 0 through 3; socket 0 is at the outside edge. Keep the current working SIMM placement. Chipset bank numbers are not a confirmed socket map. The exact graphics card remains to be measured.

The board has serial mouse connections and no PS/2 mouse connector. `platform.aux_bios_supported` defaults to false. Setup hides PS/2 Mouse, unsupported extra serial address pairs, and ISA Serial Discovery. Hidden controls are also excluded from keyboard navigation. A valid older CMOS record keeps its other parameters; only that unavailable selector is normalized. The AUX initialization and INT15/C2 interface issue no mouse-controller commands. Serial ports remain available.

## Source boundary

`src/bios.asm` composes the complete donor core from repository-root `shared/src/firmware/`. That core owns POST presentation, visible RAM testing, Setup/CMOS defaults and recovery, halt/error tones, generic BIOS services, disk/floppy read-write, RTC/input/mouse, boot policy, APM, and El Torito. Generic donor bodies remain unchanged where they have no board access. Presario source and supplied ROMs remain unchanged; broader Presario adoption is later work.

`src/hardware/` supplies UMC startup/RAM probing, PCI board policy and external VGA initialization, shadow/cache reporting, CMOS chipset policy, UM8663 port routing, native IDE channel selection, floppy drive/motor mapping, and reset. Root `shared/src/pc/pci.inc` owns generic PCI access, enumeration, resource allocation and INT1A. It does not issue donor VLSI, SMC, or Compaq VGA-offset accesses. `port.json` supplies identity/version/date, ROM geometry, and hardware policy through generated `CFG_*` variables. The consumed porting seeds and former partial POST shell have been removed.

The physical image is128 KiB mapped at E0000. The complete64 KiB logical core lives at F0000; its reset vector enters F000:0000 directly. The lower64 KiB remains padding. RAM is detected before stack use. The donor state schema is retained in an 8 KiB EBDA; BDA base memory and buffer protection match that reservation. Hardware metadata occupies separate slots within that reservation.

The RAM adapter measures both physical bank pairs, chooses supported single/paired and sided organizations, and sorts the two regions by capacity. It validates address independence and restores its probes before publishing the map. Asymmetric addressing is tried only on the documented PCI silicon revision 04h. Unknown silicon still uses ordinary bank organizations. Unequal modules use the largest validated map; unsupported extra capacity is not added to the report. Bank numbers 0 through 3 describe the mapped chipset banks. Physical socket wiring still needs a matching observation.

Installed and usable extended counts have separate 32-bit state fields. The RAM test, POST, Setup, and diagnostics use those fields. INT15/AH88 and CMOS extended-memory words have an explicit 64512 KiB (63 MiB) ceiling. They never wrap. The modeled two-region maximum is 256 MiB; the shared count readers keep the word contract for ports that have not adopted wide publication.

The processor label comes from the [shared finite CPU recognition list](../shared/README.md). Without CPUID, class tests return generic 386, 486 or later (`486+`), or legacy Cyrix. Product ambiguities remain visible. Recognition does not imply board support or derive a clock, voltage or multiplier. Normal and F9 defaults enable CPU L1. Existing saved L1 settings remain unchanged until defaults are loaded. Safe recovery disables both caches. External L2 has its own Enabled/Disabled setting. SRAM sizing follows AMI's forced-hit alias method, with opposing writable data and full data/tag qualification before ordinary enable. Cache size comes from the measured map rather than register readback. POST shows L2 Cache Test directly below the RAM bank line while full qualification runs. The test status changes from Testing... to Passed. Summary reports its measured capacity and effective WT/WB/Off state. Recovery defaults disable failed cache. Qualification failures identify the pattern, address, cache bank and affected byte lanes. Data-pattern failures also show the expected and read values. Bank 0 is U20-U23 at the outside edge; Bank 1 is U11-U14; U19 is TAG. The repaired failures confirm byte 3 (D24-D31) at U23 in Bank 0 and U14 in Bank 1. Other byte-to-socket assignments are unverified, so the error screen retains the bank socket group. A data mismatch identifies a suspect lane, not a guaranteed chip diagnosis. Temporary register/value dumps are removed. L2 failure applies safe settings with L2 disabled, then waits for a key before restart. Saving Enabled again allows another qualification; a prior notice is not a permanent lockout. New UMC chipset records use tag 56h. Valid older 55h records migrate in RAM to Manual with their waits, L1 and L2 settings preserved; loading does not write CMOS.

IDE discovery probes all four physical positions. The existing donor API represents the first two detected ATA/ATAPI devices, with actual channel/master/slave port tables and truthful labels. An ATA disk on the secondary channel can boot as 80h. Supporting four simultaneous logical BIOS records is later work. Floppy swapping maps both commands/motors and returned unit identity in the M919 adapter.

PCI BIOS advertises bus zero only. BARs must fit the configured I/O pool through 10000h or MMIO pool `pci_memory_base` through exclusive `pci_memory_end`. Unsupported resources remain undecoded. BF IDE IDs 1060:673A/673B use readback-qualified compatibility mode. Fixed-native, mixed, ignored mode writes and rejected I/O resources remain unusable without AF fallback or legacy task-file probes. Saved Enabled remains a policy request. Slot 0C/0D/0E pin links follow the native AMI ABCD/DABC/CABD tables. Stock 86Box uses a different 0E rotation. Physical interrupt wiring remains unmeasured.

Valid VGA providers can declare 32, 48 or 64 KiB. The adapter shadows the full declared extent and starts later ROM discovery after it. HB54 uses 02h through 32 KiB, 06h through 48 KiB, and 0Eh through 64 KiB. Bits 04h and 08h select separate 16 KiB regions at C8000h and CC000h. The UM8663 startup retains the configured whole-register C0/C1 seeds. Later saved routing preserves C0's upper nibble and C1 mask 30h. C2 wake/init changes preserve unrelated bits, and C3/C4 remain unchanged.

The floppy adapter detects enhanced-controller commands before using them. Legacy controllers use the standard command sequence. Failed POST seeks retain the normal controller/version/stage/status evidence. After RAM sizing, the adapter releases fast A20 so HIMEM can control the 8042 gate; INT15 memory moves preserve the previous gate state. Keyboard handoff retains queued input and checks the board command policy. Warm reset keeps the existing write-back/flush sequence and reopens A20 before issuing the reset pulse. This allows reset-vector access after HIMEM closes the gate.

Keep the proven shared floppy driver unchanged. All four supplied AMI DMA routines also program DMA without software cache-flush instructions. CPU and bus-master coherence is a hardware contract; the software model distinguishes WT/WB CPU policy and hardware snooping. Its pass does not establish the physical board's cache wiring. New changes need a demonstrated requirement or failure and source-backed justification. Chipset differences stay in adapters; proven improvements can enter shared code.

## Memory and cache profiles

Chipset > Memory follows the Presario profile screen. Set `Timing Profile Clock` to the bus-clock jumper setting: 25, 33, 40 or 50 MHz. This input selects timing rows; it does not measure or program the clock. `DRAM Speed` accepts Unknown, 60 ns or 70 ns. Unknown uses the 70 ns row. The retained AMI Normal table has the same timings for both ratings.

Normal uses the AMI wait/burst tuples. Compatibility uses the successful conservative timing tuple. Fast uses the documented minimum wait/burst encodings and appears only when it can improve an available path. If changed hardware removes Fast's benefit, loading selects Normal and preserves the other settings. Manual unlocks read/write waits and EDO burst timing. Presets update their raw timings together; editing the cache burst selects Manual. The first three rows, Profiles/Memory Access headings, colors and columns retain the donor layout. All nine memory controls fit on one page. DRAM wait choices run from 0 through 3. Every enable/disable popup lists Enabled first, with stored bit meanings preserved.

Memory also provides FPM/EDO, refresh and parity controls. Enable parity only with parity SIMMs. Reporting stays masked while RAM parity is initialized; Esc still requires a nondestructive initialization pass. Cache provides independent L1/L2 requests, WT/WB, read burst and early write. Bus Timing provides CPU posted writes, burst writes and burst copyback. Geometry remains measured. Unknown register meanings, voltage, multiplier, ROM cacheability and memory holes are not editable.

The first L2 test runs immediately after the RAM test under the selected timings. It tests the full measured capacity with four opposing/address patterns and tag/backing-RAM checks. Grouped loops reduce repeated instruction work without reducing coverage. L2 remains off through the final Setup gate, then the existing late owner enables it. Its capacity and status appear only in Summary.

Successful validation is stored in the checksummed chipset record. An unchanged boot rediscovers hardware, checks the ROM/CPU/RAM/cache identity and reuses that result. A saved memory/cache/bus timing change, defaults, recovery, changed map/CPU or different system ROM requires a full test. Draft edits, discard, unchanged save, disk/ports/theme changes and date/time edits preserve the result. Delete received during the RAM test enters Setup before L2 qualification. Saving Setup does not certify untested cache. This removes repeated full tests; it does not detect a new fault in a chip with the same identity. Save a changed cache parameter to request a fresh full test.

WT uses eight tag bits; WB uses seven plus dirty. L2 remains off if installed RAM exceeds capacity times 256 for WT or times 128 for WB. A 512 KiB cache therefore covers 128 MiB in WT or 64 MiB in WB. WB is an exposed native AMI policy, but its physical operation and timing margins remain to be confirmed. The software model checks dirty external cache separately from CPU policy, including flush, eviction, DMA and warm reset. The runtime floppy/DMA service has no added flushes.

## Shared RAM test

`shared/src/firmware/ram-test.inc` owns the visible RAM test. Ports supply the detected capacity and reserved state area. The test backs up 2 KiB at a time into excluded EBDA scratch, tests every usable dword with three full pattern passes, and restores the original bytes. Separate address witnesses detect tied low address lines. CPU cache stays disabled during the test.

The owner excludes live firmware state and the VGA/ROM window. It services the existing keyboard owner every 16 KiB or less and updates progress every 64 KiB. Esc skips, Delete requests Setup, and Pause retains the interrupted test until a fresh make. All exits restore the original machine gates and context before returning or using the existing recovery owner. Presario can adopt this shared implementation in its later refactor.

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

The port roadmap is [docs/roadmap.md](docs/roadmap.md). The first firmware contract is [M919-002 POST](docs/plans/M919-002-post.md).

Run PowerShell with `-NoProfile` and Python with `-B`. Keep generated files under `m919/build/`.

Build and verify from the repository root:

    pwsh -NoProfile -File m919/tools/build.ps1
    pwsh -NoProfile -File m919/tools/verify-rom.ps1
    python -B m919/tools/test-build.py
    python -B m919/tools/test-reference.py
    python -B m919/tools/test-reference.py --native
    python -B m919/tools/test-hardware.py --case ram-test
    python -B m919/tools/test-hardware.py --case geometry
    python -B m919/tools/test-hardware.py --case memory-services
    python -B m919/tools/test-hardware.py --case cpu
    python -B m919/tools/test-hardware.py --case pci
    python -B m919/tools/test-hardware.py --case sio
    python -B m919/tools/cache_proof.py cache-discovery
    python -B m919/tools/cache_proof.py cache-policy
    python -B m919/tools/cache_proof.py cache-settings
    python -B m919/tools/cache_proof.py cache-dma
    python -B m919/tools/cache_proof.py cache-location-report-live
    python -B m919/tools/cache_proof.py cache-recovery-boundaries-live
    python -B m919/tools/timing_proof.py timing-settings
    python -B m919/tools/timing_proof.py timing-order
    python -B m919/tools/timing_proof.py cache-persistence
    python -B m919/tools/timing_proof.py timing-crc
    python -B m919/tools/timing_proof.py timing-parity
    python -B m919/tools/timing_proof.py cache-writeback
    python -B m919/tools/timing_proof.py cache-speed
    python -B m919/tools/timing_boundaries.py all
    python -B m919/tools/test-post.py --case all

The output is `build/baios-m919.bin`. `build/rom-checksums.json` records its size, SHA-256, and configured identity. The build wrapper uses the maintained root implementation in `shared/tools/rom.py`. Output must stay below this port's `build/` directory. The verifier checks size, whole-image byte sum, reset pointer and entry, date, and AT model byte.

The separate `cpu`, `pci` and `sio` hardware cases execute the composed firmware against independent external devices. They cover caller state and guarded names, installed PCI services, bounded BARs, AMI-wired interrupt delivery, VGA copy/extent, BF readback through ATA/boot, saved IDE reset/reload and UART/printer/FDC transactions. They do not replace the frozen donor matrix or physical hardware measurements. Build a review candidate with `python -B tools/build-rom.py m919 --output build/hardware-adapters`, then verify it with `python -B tools/verify-rom.py m919 --image build/hardware-adapters/baios-m919.bin`. The build test uses its own `build/build-tests/current` output and preserves the current main ROM.

The maintained harness uses the actual donor state and public services. `--case all` runs every named first-deliverable check once. Individual cases are `boot`, `setup`, `policy`, `policy-clock`, `ram`, `no-media`, `cd`, `warm`, `floppy-swap`, `aux-policy`, `fdc-capabilities`, `a20`, `himem`, `keyboard-policy`, `keyboard`, `keyboard-absent`, `floppy-missing`, `alternate-ram`, `cpu`, `positions`, `option-roms`, `policy-clock-no-errors`, and `dos`. `cold` selects the primary boot fixture. `clock` and `devices` select Setup and device checks. These aliases are excluded from `all`. This is the first-deliverable validation set, not a complete physical compatibility matrix.

The cases cover primary/secondary and mixed ATAPI/ATA boot, actual RAM progress/Esc, native Setup editing and saved hardware readback, invalid-CMOS/RTC recovery and warning tone gates, and poisoned option-ROM/VGA returns. DOS cases use a disposable retained-card copy and exact MS-DOS 6.22 media; SYS.COM performs the system transfer inside DOS. Guest checks exercise native DOS file writes, multisector CHS, EDD read-write, IRQ6/DMA2 floppy services, and Ctrl+Alt+Delete reset with L1 enabled and dirty extended RAM. The warm case also boots real DOS/HIMEM from floppy twice through the installed IRQ1 reset path.

The read-only DOS input is cached at `tools/deps/ms-dos/6.22-boot.ima`. Private media copies remain under `m919/build/`. The `cd` case checks native secondary-channel El Torito loading and controller status with synthetic media.

Normal POST ends at FFh and follows the saved donor boot order. Without bootable media, it displays `No boot device available` and `Press any key to retry`. Setup preserves the donor colors, frame, layout, fonts, settings, and defaults. The retired 0300h POST-only diagnostic ABI is not present; tests use `shared/src/pc/state.inc` and port-private hardware slots.

The harness checks actual VGA cells against the donor frame, columns and attributes, and checks the installed 8x16 font against the retained VGA provider. `post-dump-render.png` renders those captured cells; it is not an emulator screenshot. The C000 context test wraps a disposable retained VGA ROM copy with an artificial poisoned return. It does not establish physical VGA behavior. The absent-keyboard test replaces external controller/PIT/RTC/VGA devices and follows the real startup continuation through the error policy. It is not a stock 86Box detached-keyboard test.

The user confirmed physical DOS boot, floppy operation, HIMEM and EMM386 loading, and working keyboard input after the no-AUX correction. Temporary stage/IRQ/footer instrumentation has been removed. Normal POST failure messages and troubleshooting remain. Guest keyboard tests inject D2 scans through IRQ1; they do not prove host GUI input. The accepted physical result supplies input evidence. Emulator tests do not establish RAM wiring, timing margins, flash protection, or broader hardware compatibility. Exact results and image hashes remain in `.agent/test-results/m919-post.json`.

Build the portable, read-only PCI configuration inspector with `python -B shared/tools/build-pci-registers.py m919`. It writes `build/diagnostics/PCIDUMP.COM`, reads all 256 host-bridge bytes through PCI BIOS B108, and supports DOS stdout redirection. A failure reports the byte offset and PCI status. It does not change chipset settings.

These commands assemble the shared inspection programs. They do not build a BIOS or execute a hardware test:

    New-Item -ItemType Directory -Force m919/build/diagnostics | Out-Null
    & "$env:LOCALAPPDATA/bin/NASM/nasm.exe" -f bin -o m919/build/diagnostics/RTCCHECK.COM shared/tests/dos/rtc-test.asm
    & "$env:LOCALAPPDATA/bin/NASM/nasm.exe" -D RTC_BOOT_TEST -f bin -o m919/build/diagnostics/rtc-test.bin shared/tests/dos/rtc-test.asm
    & "$env:LOCALAPPDATA/bin/NASM/nasm.exe" -f bin -o m919/build/diagnostics/HWSTATE.COM shared/tests/dos/hw-state.asm
    & "$env:LOCALAPPDATA/bin/NASM/nasm.exe" -f bin -o m919/build/diagnostics/MOUSECHK.COM shared/tests/dos/mouse-test.asm

The copied inspector keeps its donor interface:

    python -B m919/tools/inspect-vhd.py --help
    python -B m919/tools/inspect-vhd.py <dynamic-vhd-path>

The [board manual](docs/user-manual.pdf) and [register evidence](docs/research/m919-registers.md) belong to this port. Preview cleanup with `pwsh -NoProfile -File tools/clean-build.ps1 -WhatIf` from repository root, or invoke `m919/tools/clean-build.ps1` directly. The current main ROM/listing/configuration/checksums, diagnostics, hardware reports and final/post captures remain. Completed candidates, builds, VM directories and disposable media are removed. Keep an unresolved failed diagnosis in `build/diagnostics`; do not hand its fixtures to cleanup.
