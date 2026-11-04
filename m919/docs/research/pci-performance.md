# PCI performance and register findings

This developer record closes the M919-012 investigation for production version 0.18.2. The user requested conservative RAM/cache defaults with the confirmed fixes. The final production image removes Register Lab and its cold-start CMOS reset. Saved Setup settings again survive power-off.

## Confirmed hardware results

The comparison used an AMD 5x86 and an S3 Trio64 with 2 MB. With the same RAM/cache performance, bAIos initially reached about 43.78 FPS in Doom; the original BIOS reached about 46.02–46.05. Forcing PCI /1 made all three slots perform alike. Keep Current could retain /2 after changing slots. Measured PCI clock was 33.43 MHz with 46.5% duty cycle under both BIOSes in the paired /1 test.

| Control | Observed result | Production owner |
| --- | --- | --- |
| IBC41 bit 0 = 1 | Doom rose to 45.96–45.99 FPS. Bits 3, 4 and 7 were not required for this gain. | `startup-core.inc`, before PCI initialization and the VGA ROM. Byte read-modify-write preserves other controls. |
| IBC45 bit 3 = 1 | This bit alone stopped startup/exit sound crackle at ISA /3. At /4 crackle remained, but was reduced. It did not fix palette corruption. | Same startup policy, before PCI/VGA. The electrical function is unknown. |
| IBC83 bit 6 = 0 | Setting it caused keyboard loss, a POST hang and a continuous beep. | `chipset.inc` clears retained state early, including warm starts. |
| IDE42 bit 6 = 0 | Setting it allowed identification but prevented HDD reads and boot. | Existing PCI IDE initializer writes the normal 42h value 30h. No lab override remains. |
| Local-device sampling = 2 T2 | The user reports 1 T2 instability with VLB VGA. The faster PCI result remained available with 2 T2. | Conservative Setup defaults. |
| ISA I/O recovery = 2 BCLK | User confirmed stable operation; no measured throughput gain. | Normal defaults retain 2 BCLK, with the conservative ISA divider. |

The user later reached 46.19 FPS during timing experiments. The conservative production defaults do not promise that score without equivalent user-selected timings. The user also validated the findings at a 40 MHz bus with PCI graphics and reported no issues. This is physical evidence for the tested configurations, not qualification of every board, card or timing combination. The consolidated production binary still requires its own physical confirmation.

The IBC41 bit 0 and IBC45 bit 3 names remain unknown. Do not rename them as parking, FIFO, arbitration or resource-lock controls without independent evidence. The source already has separate owners for documented parking and locking bits.

## Production consolidation

Normal boot order remains CD, floppy, hard disk. Fast Boot defaults Off. Supported caches default enabled/write-back. DRAM waits and cache burst defaults are conservative. Explicit saved clock choices are applied before PCI enumeration and the VGA ROM, then preserved by late tuning. Early initialization restores Slow DEVSEL before VGA because warm-reset retained Fast timing caused Setup/default-recovery failures during the lab experiments.

The shared Setup renderer retains the new Both Channels / Disabled / Primary Only controller choice. Disabling the secondary IDE channel removes its decode, probing, timing writes and IRQ reservation without moving any device settings. COM/LPT selectors use sorted display positions mapped back to existing saved encodings; their conventional port numbers accompany the addresses.

Unsuccessful comparison overrides were removed: forced HB59 and revision-04 HB61 changes, extra IBC46/47/55/57/A7 writes, top-down PCI BAR allocation, early VGA-routing replay and the additional IBC50 shadow step. These experiments did not establish a performance benefit. The established cache activation sequence is unchanged.

## Accepted VLB limitation

VLB graphics with ISA digital sound can corrupt the palette on both reported board revisions and with the original BIOS. CPU/external cache disable did not remove it. FM music, General MIDI and PC-speaker sound did not trigger it. Colors may change during sounds or level loading; Doom F11 restores the palette. Disabling floppy initially appeared to help, but also stopped sound effects, so that was not a successful repair.

The user swept every exposed Register Lab field through both states without finding a palette fix. IBC45 bit 3 improved crackle only. A board-level bus/buffering fault remains a hypothesis, not a demonstrated electrical diagnosis. Further experiments are deferred by the user's production-release request.

## Source research and diagnostics

Bounded original-ROM tracing established the PCI VGA tuple HB51.04 / IBC50.80 / IBC56.60, endpoint setup and the automatic clock handler. The handler writes IBC56's low nibble followed by IBC A4's low nibble, preserving upper bits. It selects /2 for its 40 MHz class and /1 for its 33 MHz class; no additional clock-latch pulse was found. The supported explicit bAIos divider remains under user control.

Original endpoint initialization requests command 011F after resource assignment, sets latency 40h and cache-line size 04h, and clears status with FFFFh. These differences did not justify indiscriminate bus-master enable. Other negative comparisons included RAM/cache policy, palette snoop, EBDA placement, PCI IRQ assignment, secondary IDE disable and endpoint state. Palette snoop affected the reliability of Landmark's display and gave a small repeatable Doom change; it did not explain the main gap.

The standalone sources remain in `m919/diagnostics/`. PCISTATE version 2 uses PCI BIOS services; its earlier direct-I/O version locked the test machine. S3STATE, VGA I/O, refresh and bounded DAC/wait tools supported the comparison. Generated vendor disassembly, captured dumps and original-byte replay output remain private under `build/research/`. They are not public source or proof of electrical behavior.

Production checks are declared in `m919/validation.json`. The startup regression executes cold/warm initialization with both saved-record layouts; the clock regression compares retained and explicit ratios; the IDE and Devices tests exercise actual Setup input, saved records and hardware owners. Emulator and fixture checks establish software behavior only.

