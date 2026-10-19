# Presario 800 bootstrap BIOS

Shared menu, layout, descriptor, and keyboard-diagnostic bodies live in repository-root [`shared/src/`](../shared/README.md). The original source paths forward to those maintained bodies. Keep the existing NASM `src/` include root when assembling this port.

Generic VHD, FAT16, floppy-image, and network helpers have the same root owner in `shared/tools/`. The original tool paths retain compatibility imports. Emulator source, stock ROMs, and common downloads live under repository-root [`tools/`](../tools/86box/README.md). Presario-specific collection overrides live in `reference/86box/`. Builds use that retained VGA input and write private adapters under `build/86box/`.

The physically approved pair uses the source pinned by local branch `presario-800-physical-approved`. Current source includes the pending CD-hook correction. Use a separate `build/` candidate directory when testing it. The existing emulator runner rebuilds the main directory, so use it only when that replacement is intended.

This project builds a new 64 KiB system BIOS for the Compaq Presario 800 platform. The physical image is 128 KiB.

The default build combines the current system BIOS, bus07 Cirrus VGA at nominal 60 MHz, and retained OEM resources.

The legacy `-Vga141` build uses the unmodified supplied Cirrus 1.41 VGA ROM under `build/vga141`.
It leaves the main release unchanged. See [the original VGA comparison](docs/vga141.md) for the retained adaptation details.

The physically validated bus07 reference is `reference/baios-presario800-vga141-bus07.bin`. Run `python -B presario-800/tools/build-vga-bus.py` from the repository root to reproduce it under `build/vga141/bus07`. Obsolete tuning outputs are purged. Git retains their source history.

## Current scope

The BIOS initializes the VLSI chipset, retained Cirrus VGA ROM, primary ATA disks, keyboard, PS/2 mouse, floppy controller, and legacy serial/parallel ports.
RAM detection handles bank 0 as onboard 4 MiB or 8 MiB with the slot-1 module. Banks 1–3 accept 4, 8, 16, or 32 MiB modules.
Physical slots 1, 2, 3, and 4 connect to banks 0, 2, 1, and 3. Slot 1 is the outermost slot.
Physical tests reached 64 MiB with all-FPM modules (`FD/DE`), including normal HIMEM/EMM386 boot and reliable warm resets.
Mixed FPM/EDO modules also passed at 64 MiB. A physical test above the selection limit confirmed that the additional bank is skipped.
The OEM DRAM baseline also corrected the tested bank-2 EDO instability and warm-reset failure.
Larger configurations remain unresolved. This is not a claim that the hardware cannot support them.

The BIOS supports CHS access and 28-bit LBA access. The 86Box test uses a fresh 8 GiB disk image.

The BIOS initially reserves a 1 KiB EBDA and reports 639 KiB of conventional memory. Disk services follow the BDA pointer when EMM386 relocates the EBDA. `INT 12h` reports the current BDA memory count.

The physical Presario 800 boots MS-DOS 6.20 from the tested 2 GB SD card. Physical keyboard input, locks, LEDs, and fast warm restart were confirmed.

HIMEM.SYS and EMM386 work with the physically tested 4 MiB onboard configuration. The BIOS supplies `INT 15h/AH=87h` block moves.
Detected extended memory is reported through `AH=88h`, CMOS `17h/18h`, and CMOS `30h/31h`. The AT CMOS checksum is updated.
The POST summary shows detected base and extended memory.
RAM defaults select Normal, 70 ns DRAM, and a configured 33 MHz profile clock: RAMTMG `96h`, raw 2-2-2/1.
RAMSET remains `16h`: interleave disabled, 24 mA drive, and page mode enabled.
The initial stack bootstrap still uses RAMTMG `BFh`. The L2 probe still uses `96h` before it restores selected timings.
Enabled interleave selects matching density/side codes automatically. It prefers mode 5, then the first eligible single pair.
The board permits modes 1, 2, 4, and 5 (`36h`, `56h`, `96h`, and `B6h`). Modes 3 and 6 are disabled after physical instability.
Diagnostic builds report eligible interleave modes and the actual RAMSET. Cold and warm POST apply the saved interleave policy.
Physical tests confirmed stable operation in the permitted modes and sequential fallback.

Chipset setup selects CPU speed, internal cache, RAM/cache timing, bus dividers, DMA controls, ISA windows, and ROM shadow/cache policy.
Defaults request both caches enabled, full CPU speed, Normal RAM timings, and the longest supported cache waits.
L2 stays disabled while Setup is reachable.
After the final Setup gate, the BIOS detects cache banks with the OEM direct-SRAM method and probes capacity from 32 KiB through 1 MiB.
The direct SRAM probe disables primary cache line fills. This fixes L2 detection on the physically tested Pentium P24T.
Normal tag initialization and the selected primary-cache policy are restored after the direct probe.
The original four-data-chip 128 KiB card is single-bank. Detected geometry remains intact when the BIOS applies cache write timing and policy.
The probe uses OEM RAM timing `96h` and cache phasing before it restores the selected controls. Failed checks leave L2 disabled.
Physical tests confirmed L2 with fast interleaved RAM. Similar read latency does not mean that L2 is disabled.
The read boundary at 128 KiB and the larger difference for moves show its effect. Larger third-party cards still require physical confirmation.
Cold and warm POST flush caches and disable L2, CPU caching, and chipset CEN before destructive RAM or shadow setup.
Warm restart preserves detected bank geometry and applies the selected CPU speed. Both POST paths mask DMA before changing the RAM map.
Valid shutdown continuations bypass POST and preserve the caller's chipset state.
These continuations clear the CPU cache-disable bits, as the OEM BIOS does. NSSI CPU detection no longer leaves the computer slow.

The BIOS provides APM 1.2 with real-mode, 16-bit, and 32-bit calling interfaces. New connections use APM 1.0 behavior until the driver selects a newer version.
An operating-system driver such as `CPQDOS/POWER.EXE` requests CPU idle. The BIOS halts CPU execution until the next interrupt.
Idle and Busy preserve the selected CPU speed, RAM/cache timings, and VGA settings. Disabled APM returns from Idle without halting.
APM state stays in the existing EBDA. It does not change CMOS settings or reserve more conventional memory.
The desktop reports AC online and no battery. Whole-system standby, suspend, software power-off, and timer/ring wake are unsupported.
The BIOS does not generate automatic inactivity requests. An idle wake does not produce a system-resume event.
The original Compaq Power Manager 1.00 passed driver installation, BIOS idle/wake, and DOS keyboard return in 86Box, with and without HIMEM/EMM386.
The physically approved ROMs include APM, CD boot, and the Windows/SI8 compatibility fixes. Power savings have not been measured. SI8 with POWER.EXE and EMM386 uses the OEM keyboard-polling flag contract described below.
Read the completed APM contract from Git with `git show 16cc596720aa769961c9812ad2d343c142a782ef:docs/plans/presario-800-apm.md`. The original specification lives in root `reference/standards/apm`; the Compaq driver lives in `reference/apm`.

The AT bus baseline uses chipset registers `06h=00h`, `08h=38h`, and `09h=30h`. This corrected the observed disk slowdown and sound interruptions.
The BIOS initializes the x87 and its IRQ13 path.

ATA services accept caller-owned HMA and EMM386 upper-memory buffers. They reject buffers that overlap the current EBDA or cross a segment boundary.
HDD services permit interrupts during transfers and preserve the upper halves of caller registers.
HDD and floppy services return with interrupts enabled, including status and parameter requests. This matches the OEM return contract.
Physical SI8 Disk Summary now works in safe DOS. Its disk benchmark completes. The tested SD adapter rejects seek commands.

Legacy HDD services include status, verify, format track, initialize parameters, long reads/writes, seek, alternate reset, ready, recalibrate, and controller diagnosis.
Long reads and writes transfer 512 data bytes as words, then four ECC bytes with byte-sized I/O.
Unsupported ATA commands return device errors, not fabricated success. CHS requests accept up to 128 sectors within one segment. EDD requests retain their 127-sector limit.
The BIOS publishes the primary drive count, last status, relocated INT 41h parameter table, and custom type-47 CMOS geometry.
INT13/AH08 reserves one cylinder in its reported maximum, following OEM. The fixed parameter table retains the full cylinder count.
Both primary IDE positions identify independently. Present ATA disks receive contiguous BIOS numbers starting at 80h.
ATAPI CD-ROMs appear during POST but do not receive ordinary hard-disk numbers. The BIOS reads boot CDs through ATAPI. DOS CD-ROM drivers retain normal packet access after boot.
IRQ14 acknowledges both PICs and supplies the OEM completion notification for chained disk drivers.

IDE setup provides controller enable and independent disk type, translation, block mode, and INT13 extensions for each position.
Defaults are controller Enabled, both positions Enabled, Auto type/translation/block mode, and extensions Enabled.
Numbered types use the Phoenix 1989 table: valid types 1–47; types 15,33,34,45 are reserved. User is type 48.
User geometry includes cylinders 1–65535, heads 1–16, sectors 1–63, write precompensation, and landing zone.
Precompensation 65535 means None. Precompensation and landing zone are parameter-table values, not modern drive-firmware controls.
Translation choices are Auto, Normal, Large, and LBA. Explicit geometry takes precedence over boot-sector geometry.
Block choices are Auto, Disabled, or 2/4/8/16/32/64/128 sectors. Auto uses up to 16 sectors when the drive supports multiple-sector commands.
Unsupported or rejected negotiation falls back to single-sector commands before data transfer. The next multiple request re-establishes negotiation after reset.
The controller uses 16-bit ISA PIO. DMA, 32-bit PIO, and programmable PCI timing are not available on this implementation.
The new IDE options require a physical checkpoint. The user deferred this test before the next device milestone.
Auto retains the previously tested disk mapping. Emulator results do not prove physical CMOS persistence or device timing.

Floppy services support 360 KB, 720 KB, 1.2 MB, 1.44 MB, and 2.88 MB media. They provide DOS reads, writes, verification, and formatting on A: and B:.

Devices setup selects the onboard serial address, parallel address and direction mode, and PS/2 mouse.
Serial choices are Disabled, 3F8h / IRQ4, 2F8h / IRQ3, 3E8h / IRQ4, and 2E8h / IRQ3. There is no second address-pair control.
Defaults are serial 3F8h / IRQ4 and parallel 378h in Printer mode.
Drives setup contains Floppy Controller. The floppy controller and PS/2 mouse default to Enabled.
The board has one serial connector. The unconnected UART B stays Disabled, and ISA serial discovery stays Enabled. Neither has a setup control.
Old valid device records load with those fixed policies and the standard 3E8h/2E8h pair. The next Save stores them without changing the CMOS schema.
Parallel direction mode is unavailable when the onboard parallel port is Disabled.

POST applies saved settings, initializes each detected UART to 9600 baud with 8 data bits, no parity, and one stop bit.
It leaves UART interrupts and modem outputs off. The summary shows detected COM/LPT bases. POST publishes their contiguous BDA tables.
Serial discovery checks the selected onboard port, then 3F8h, 2F8h, 3E8h, and 2E8h.
An ISA modem at COM2 can appear after onboard COM1. An absent modem does not create a second BIOS port.
It initializes every unique detected UART, but publishes only the first four. Parallel discovery publishes up to three detected ports.
The BIOS provides INT14h functions 00h–05h and INT17h functions 00h–02h with bounded PIT-based waits.
It does not activate inactive ISA Plug-and-Play cards, allocate card resources, provide a modem protocol, or supply DOS drivers.

Disabled floppy policy clears drive publication and rejects floppy BIOS requests without reopening the controller. Boot skips A: and keeps HDD policy unchanged.
Disabled mouse policy inhibits the auxiliary interface, masks IRQ12, removes callbacks, and rejects INT15h/C2h requests. Keyboard input remains available.
These policies remain active after BIOS reset and initialization requests. The user confirmed the onboard device options on physical hardware.


Floppy DMA buffers must remain below 1 MiB, outside the current EBDA, and inside one physical 64 KiB page. Verification has no caller buffer.

Valid CMOS drive types select the installed drives. Empty or invalid drive configuration defaults to A: 1.44 MB and B: not installed.
These defaults are settings, not automatic drive detection. Media-rate detection remains separate.

First, Second, Third, and Fourth Boot Device select Disabled, Floppy, Hard Disk, CD-ROM, or Other.
The defaults are Floppy, Hard Disk, Disabled, and Disabled. Disabled skips a slot and can repeat. Selecting an allocated target moves it to the new position and shifts the intervening slots. Saved non-disabled targets remain unique.

Hard Disk uses drive 80h through the installed INT13 handler, including a disk published by an initialized legacy ROM. Other invokes the INT19 chain captured from initialized option ROMs at its selected priority. A returning or absent ROM continues to the next target.
Failed reads and unsigned sectors advance to the next selected target. INT18 abandons the failed sector's stack and continues the same order.
After all targets fail, the BIOS displays `No boot device available`, then `Press any key to retry` on the next line.
Each failed fresh retry appends the same two lines, so its result is visible.
Retry resets the installed disk handlers and restarts the installed INT19 chain. It does not repeat POST or ROM initialization.

CD-ROM tries the enabled primary IDE positions in order. It uses the x86 Initial/Default El Torito boot entry. Invalid or unreadable discs continue to the next target.
No-emulation images use drive E0h and read-only 2048-byte extended reads. Floppy images provide read-only 1.2, 1.44, or 2.88 MB emulation through INT13.
During floppy emulation, the image is A:, physical A: becomes B:, and physical B: is hidden. The virtual drive works with the physical floppy controller disabled.
INT13/AH4Bh reports the boot packet or terminates emulation. Termination and boot continuation restore native drive mapping. No extra conventional memory is reserved.
If a bootloader keeps a disk hook above the CD wrapper during INT19, the next CD boot reuses that chain and its original predecessor.
Hard-disk CD images, alternate catalog entries, SCSI CD boot, and software re-initiation are not supported.

Timer interrupts and Pause release do not retry. Ctrl+Alt+Delete runs a full warm POST. Late Delete does not reopen Setup.

Optional POST floppy seeking defaults Enabled. POST checks motion and track-zero response without writing media.
Swap Floppy Drive defaults Disabled. Enabled selects the FDC37C661 hardware drive-and-motor swap. Setup keeps the physical drive types in their original order.
BIOS services use the resulting logical A/B types. Controller disable policy still takes priority.
The installed 86Box D824 model uses FDC37C651 without CR3. It cannot validate enhanced TDR swapping.

Both cold and warm POST blank video early, then rebuild the protected system shadow before VGA checksums. The retained VGA initializer restores output.

Keyboard input uses a US layout, translated scan set 1, the standard BDA ring, and the minimum DOS-facing `INT 16h` services. Caps, Num, and Scroll Lock update their state and LEDs. Num Lock XOR Shift selects keypad digits or navigation. Ctrl+Alt+Delete uses the OEM software warm entry, not an 8042 CPU reset.
F1–F12 use the standard plain, Shift, Ctrl, and Alt BIOS key codes. Alt takes priority over Ctrl, then Shift. This includes Shift+F8 for DOS step-by-step startup. Enhanced readers retain E0 navigation and keypad identity.
INT16/AH01h and AH11h return with IF set. Empty status sets ZF and clears CF. Ready status clears ZF and sets CF. This matches OEM E878h/E8A1h and prevents POWER.EXE polling from leaving interrupts disabled. Other caller flags and registers remain intact.
INT15/C0 reports the enhanced keyboard and EBDA capabilities. INT15/C1 returns the current EBDA segment, including after relocation. This lets Windows 386 Enhanced mode reserve the BIOS state page.
PS/2 reset, initialization, and streaming retain IRQ readiness independently. C205 preserves packet-length BX. The original Windows mouse driver completes registration and enables streaming.
Windows 32-bit disk-driver compatibility remains outside this release. The SYSTEM.INI 32BitDiskAccess entry controls checkbox presence. In Virtual Memory, a permanent swap file uses BIOS access and a temporary swap file uses MS-DOS access.
Boot Num Lock defaults On. Cold and warm POST apply the saved state to the BDA and keyboard LEDs.
A silent keyboard after successful controller checks produces a visible keyboard warning. Controller and A20 failures remain fatal.
Halt On defaults All Except Keyboard. All Errors also pauses for keyboard absence; No Errors continues after recoverable warnings.

The BIOS delays physical PIC initialization writes. IRQ0 also polls pending keyboard output, so input does not depend only on the IRQ1 signal.

The progressive POST screen starts after keyboard initialization. Pause suspends the interrupted caller until a fresh key resumes it.
The resume key does not enter the key queue. Ctrl+Alt+Delete clears pending controller input and the BIOS queue before warm entry.
The keyboard handler calls the `INT 15h/AH=4Fh` interceptor before decoding. This permits EMM386 to leave virtual-8086 mode before reset.
CPU-reset shutdown requests `05h` and `0Ah` resume through `0040:0067` before destructive POST. This supports NSSI's CPU detection.

The built-in PS/2 port uses the OEM VL82C114 mode, `INT 15h/C2h` services, and IRQ12 packet callbacks. IRQ0 calls `INT 1Ch` for DOS timer clients. Mouse and keyboard bytes have separate owners, including when EDIT chains IRQ1 after reading port `60h`.

The retained VGA public interrupt entry remains intact. A legacy ROM-identification token avoids a Speedsys 4.78 BIOS-scan bug that corrupts DS and the stack.
Chris's benchmark works when run directly. Its batch-launch buffer can cross a 64 KiB boundary in the retained VBE handler.
RTC services now supply INT 1Ah/AH=00h–07h, POST clock initialization, midnight rollover, and recurring daily alarms through IRQ8/INT 4Ah.
Public time/date fields use BCD. Native binary/BCD and 12/24-hour formats remain unchanged. Supported dates span 1980–2099, including the 1999 rollover.
Invalid clocks return errors until valid time and date setters repair the power-loss state. The century uses CMOS 32h.
The narrow VBE buffer guard remains deferred.
No VBE buffer patch is included.
The NSSI processor hotkey hang also occurs with the OEM BIOS. It is not a firmware correction in this milestone.

Delete during POST opens native 80x25 setup. Standard Setup edits date and time immediately after Enter confirms a valid form.
Esc cancels a form without changing the clock. F1 shows information for the selected page or field. F1 or Esc closes help in place.
The static header shows Setup version 0.1.0 and the ROM build date. Standard Setup displays the system clock in the body.
Time Format selects 12 Hour or 24 Hour. The default is 12 Hour. Dates use MM/DD/YYYY.
In a 12-hour time form, A/P selects AM/PM. The hardware RTC format stays unchanged.
The footer lists function keys. Chipset field pages also show the page keys.
The ROM supplies SMBIOS2.2 BIOS/system identification, its conventional date and AT model byte, and the existing INT15/C0 descriptor.
ROM identification and Setup share the version and release date. No PnP interface or device inventory is added.
Drives configures floppy types, the IDE controller, and both primary positions. Enter on a primary position opens its detailed settings.
Setup uses fixed label and value columns. Disk geometry follows Disk Type; transfer settings appear below it.
Settings within a group use consecutive rows. Blank rows separate groups.
Cacheable ranges use three ranges per page. Standard Setup shows all RAM sizes in KB. Exit actions appear at the top of the page.
Primary-position values have submenu arrows. Selected fields have padded, single-row highlight bars, and choice highlights include spaces.
Unavailable fields are gray and navigation skips them. Only User type permits geometry edits.
Enum fields open choice menus. The numbered-type menu supports Page Up/Down. Numeric geometry is editable only for User type.
F9 restores draft defaults. Discard leaves saved settings unchanged. F10 verifies saved CMOS bytes, then restarts POST. Verification failure shows an error and keeps the draft in Setup without restarting.
F4 selects the previous color theme; F5 selects the next. The footer shows `F4/F5 Theme`.
Nine themes start with the current default, Award Blue, Award Gray, AMI Purple, and AMI Teal.
AMI Classic, Monochrome Amber, Black & White, and High Contrast follow in that order.
F10 saves the theme. F9 selects the current default. Discard retains the saved theme. Close a popup or help before cycling themes.
The schema5 base settings occupy CMOS 38h-3Fh and include the drive types at 10h in their additive checksum.
Flags store Num Lock, seek, swap, Halt On, disabled primary-position policy, and 24-hour display in bit7.
CMOS 3Ch stores the first boot target in bits2:0 and theme0-8 in bits6:3. Bit7 must be zero.
CMOS 3Eh stores the second target in bits2:0 and the fourth in bits5:3. Bits7:6 must be zero. CMOS 3Fh stores the third target.
Boot codes are Disabled=0, Floppy=1, Hard Disk=2, CD-ROM=3, and Other=4. Undefined codes and duplicate non-disabled targets reject the record.
Valid schema1-4 records retain their original boot meanings and use Disabled for the fourth target. Schema4 retains its saved theme and display preference. Earlier schemas use the current theme, with schema3 retaining its display preference.
Only a confirmed save publishes schema5. Theme identities use the current order directly.
Schema2 still rejects its reserved bit7. Discard leaves the saved display preference unchanged; F9 selects 12 Hour in the draft.
Additive, versioned records use 40h–5Ch for IDE and 5Dh–68h for devices.
The chipset record uses signature `C2h` at CMOS 69h, checksum 6Ah, and 24 settings bytes at 6Bh–7Fh and 33h–35h.
Byte 10 stores Memory Timing in bits 7:6 and DRAM Speed in bits 5:4.
Timing codes are Normal=0, Compatibility=1, Manual=2, and Fast=3. Speed codes are Unknown=0, 60 ns=1, and 70 ns=2.
Byte 23 stores the profile clock in bit 1 (25 MHz=0, 33 MHz=1) and CPU Fast/Slow in bit 0.
Valid `C1h` records load as Manual/70 ns/33 MHz without changing hardware values or saved CMOS bytes.
Invalid selectors and inconsistent preset timing tuples use ordinary defaults. A verified save publishes `C2h`.
An absent additive record uses its defaults without changing other valid records. A malformed signed record produces a visible POST warning.
With a trusted base record and Halt On=No Errors, recoverable clock and extension warnings continue without CMOS writes.
Other recovery notices retain Enter to save defaults and restart, or Delete to enter Setup. An invalid base record always retains this recovery choice.
Progressive POST uses the summary's blue header and cyan labels. Each group appears when its existing detection owner completes.
The screen shows the processor, active L1, RAM Test count, banks and interleave, floppy drives, and both primary IDE device names.
The RAM count stays left aligned. Passed follows KB by two spaces. Escape skips the remaining bulk test and shows Skipped.
Mandatory firmware RAM checks remain active. Delete shows Entering setup... and opens Setup at the next safe checkpoint.
During the bulk RAM test, that checkpoint occurs every 1 KB. Setup discard restores completed groups and resumes POST.
L2 stays off until the final Setup gate. Its state appears after the late probe, followed by VGA BIOS and System BIOS states.
Shadow/cache labels describe the complete ROM extent and the active register policy. Partial coverage is explicit.
Cached means eligible through an active cache, not a measured cache hit. Conflicting primary-region policies can show Cache status unknown.
Only validated add-in ROMs appear under Option ROMs. VGA is separate. Every selected address and state appears before its initializer runs.
The four-row add-in list scrolls when necessary and retains a detected count. Messages remain below the hardware groups.
Simultaneous CMOS and clock faults share one warning line. RAM, floppy and expansion ROM warnings reuse the message rows and preserve the key hint.
New notices remove old message text.

The summary puts the blue header at row 0 and draws the cyan table in rows 1 through 11.
The model is at the left, bAIos is centered, and the ROM build is aligned at the right.
Paired right labels start at zero-based column 40. The IDE rows sit directly above the bottom border.
POST boots automatically when no error requires input.
Row 12 is blank. Messages start at row 13, or row 14 after a warning row.
Clock, floppy, settings, keyboard, expansion ROM, and RAM recovery warnings appear outside the table at row 13.
Later BIOS messages and OS output use normal full-screen scrolling. The summary can scroll off screen.
The table shows actual memory, installed bank indices, L2 state and capacity, logical floppy types, and all published COM/LPT addresses.
The bank list includes `Interleaved` when the chipset's active interleave mode is enabled.
Each primary ATA/ATAPI position uses one line, with its full 40-character model name followed by `[size MB PIO]` or `[ATAPI PIO]`.
The brackets use teal. Size, units, and transfer text remain white.
ATA size uses DOS-style MB (2,048 sectors per MB). Geometry, L1, and option ROM disk counts are omitted from the table.
The reset signature identifies supported processor models, including Pentium P24T. Unknown signatures show Unknown; CPU MHz is omitted.
The existing x87 check supplies FPU status.
Pause suspends the interrupted caller in IRQ1 until a fresh key resumes it. The resume key is consumed.
Timer interrupts still run. Code with interrupts disabled pauses when keyboard interrupts become available.
Setup and its exit use 80x25 text mode. All pages, editors, help and choice lists fit this screen.
The two-line Setup header shows the model and detected CPU at the left, bAIos Setup in the center, and version and ROM build at the right.
Page headings sit directly below the header rule. A single vertical line joins the two horizontal rules between the menu and settings.
The live date and time appear on the Standard page.
Invalid clock domains show draft defaults of 01/01/1980 and 12:00:00 AM (00:00:00 in 24 Hour).
Confirmed values remain visible while the other domain still requires repair, including after a display-format change.
An invalid clock produces a POST notice and one short beep. Halt On controls its pause when the base record is valid.
A fresh key continues a paused POST; Delete alone requests setup. Ctrl+Alt+Delete remains available.
After CMOS power loss, confirm both date and time to clear the warning.




After the final Setup gate and cache setup, POST scans C8000h–DFFFFh on 2 KiB boundaries for legacy expansion ROMs.
It validates the signature, nonzero 512-byte length, complete extent, and checksum before calling offset 3 once per POST.
It skips covered extents and does not initialize the retained VGA ROM again. The selected ROM shadow policy remains active.
A malformed recognizable ROM produces a warning controlled by Halt On.

A returning ROM can retain interrupt hooks and disk publication.
BIOS segments, flags, and stack are restored after its return. A non-returning card initializer retains control without a BIOS watchdog.
The BIOS captures card-owned INT19 behavior and dispatches it through Other. A card that chains into BIOS INT18 continues with the selected BIOS order. An initializer that boots without returning retains control.
PnP, BEV/BCV selection, named ROM targets, PCI, PMM, and E0000h scanning are not supported.
Disk Type None disables native detection and services for that IDE position. Its saved geometry remains available when re-enabled.
Keep Primary IDE Controller Enabled when an option ROM needs the onboard interface. None does not disable the shared controller.

The installed D824 model boots the retained Adaptec AHA-154xB ROM's SCSI-only drive 80h with default ROM shadow policy.
It reads distinct SCSI data. Saved C800 shadow-on boot remains unverified in this model.
The user confirmed NIC option ROM operation on the physical board. SCSI ROM validation is deferred.
Mixed ATA/SCSI access, saved SCSI shadow-on boot, and retained iPXE network payload success/failure remain unverified.

Chipset contains Memory, Cache, Clock, ISA Bus, DMA, and ROM Shadow categories. Related fields share pages with visible page numbers.
Up/Down and Page Up/Down reach all fields. CAS Width choices show separate `L2 Disabled | L2 Enabled` columns.
Values use the existing columns. F1 explains performance and side effects for the selected field. Configuration pages contain no explanatory prose.
The board's single oscillator uses TCLK2 dividers. Chipset defaults remain drafts until Save, and edits after F9 remain in the saved draft.
The first RAM page groups profile selectors and timing controls. The second groups refresh, configuration, and parity controls.
Normal and Compatibility select coherent FPM timings. Manual retains raw values.
Preset access timings are gray and unselectable. Select Manual before you change these five values.
Refresh, interleave, RAS Timeout, configuration, and parity controls remain independent of the timing profile.
Leave RAS Timeout Disabled unless the RAM requires a RAS time limit. Enabled can close RAM pages.
Fast changes only CAS from code10 to code01, which matches Normal non-L2 2T reads with L2 enabled.
Fast is available for 25 MHz/70 ns, 33 MHz/60 ns, and 33 MHz/70 ns, including Unknown aliases.
At 25 MHz/60 ns, Normal already uses non-L2 1T reads. L2 cannot match this width, so Fast is unavailable.
The choice order is Fast, Normal, Compatibility, Manual. Saved codes retain their meanings.
In Manual, changes to DRAM Speed or Timing Profile Clock retain raw values. Other modes apply their selected tuple immediately to the draft.
The profile clock is configured input. The BIOS does not measure or change the host clock or detect SIMM speed.
For clocks above 25 MHz through 33 MHz, select 33 MHz. Above 33 MHz, use Manual.
Onboard RAM is 70 ns. Unknown uses the 70 ns profile. The 60 ns choice is experimental with onboard RAM.
CAS values show raw read/write widths with L2 off and on. HSPD also uses the right column.
With L2 or HSPD enabled, CAS code 01 means 2T/1T. Cache selection does not change raw CAS bits.

POST checks firmware RAM before video, then shows progress while it checks free conventional and contiguous extended RAM.
Only a failed RAM comparison selects persistent Compatibility defaults. Ctrl+Alt+Delete and power-off during POST do not trigger recovery.
CMOS 36h retains a defaults-restored notice across resets until POST prints it. Visible failures print immediately without a keypress.
CMOS 69h=`D2h` selects Compatibility/70 ns/33 MHz: RAMTMG `A6h`, raw 3-2-2/1, interleave disabled, and conservative cache defaults.
Recovery rebuilds firmware state and preserves detected RAM banks and the one-retry guard.
The Compatibility selection survives notice acknowledgement and later resets until a verified save replaces `D2h` with `C2h`.
Unsaved F9 changes, canceled F10, discard, and failed save verification retain this selection.
A second comparison failure at defaults halts. A CPU hang before a failed-comparison branch cannot record a failure.
Enabled ISA windows limit contiguous memory reports. L2 setup temporarily disables their mappings while it uses installed DRAM scratch.
The final RAM check skips an eviction test when contiguous RAM cannot contain its scratch addresses. Recovery republishes both CMOS memory counts.
The summary shows actual L2 capacity, Disabled, or Not detected. Hardware POST codes retain the detailed probe result.


Runtime keyboard turbo switching, other keyboard layouts, and 1/2 MiB SIMMs remain outside this checkpoint.

CAUTION: Use a known recovery method for the first hardware test. 86Box cannot validate physical DRAM timing or SIMM slot wiring.

The [FPM preset guide](docs/fpm-dram-presets-25-33mhz.md) records the original design inputs. The current VL82C481 profiles, locked values, and Fast eligibility described above supersede its earlier proposals.

## Directory layout

This directory contains all Presario 800 files. Source is in `src`, guest checks are in `tests`, and commands are in `tools`.

Board manuals are in `docs`. Active port contracts are in `docs/plans` in this port. Reference ROMs and their permanent searchable disassemblies are in `reference`. Generated build files and 86Box assets are in the ignored `build` directory.

Current requirements live here and in the [CD boot contract](docs/plans/presario-800-cdboot.md). Read completed plans from Git with `git show 112b3ac58770e6a97b1ea0e9535f1a13cb34c45c:<repository-path>`; the APM contract is in commit `16cc596720aa769961c9812ad2d343c142a782ef`.

`build` is the only active approved build directory. Both VGA speeds share it, using the existing `baios-presario800-vga50.bin` and `baios-presario800-vga60.bin` names and one system ROM. A pending candidate uses one directory for both speeds. On physical approval, replace the main pair and remove the pending directory. Purge obsolete output; Git retains version history.

The entry source selects `BOARD_DEFINITION`, which defaults to `src/boards/presario800.inc`. This file owns board identity, ports, and chipset include selection. `src/chipset.inc` composes those selected includes with the shared menu.

Chipset files now have separate owners:

- `src/chipsets/vl82c481/policy.inc` owns register policy, saved-record validation, profiles, and RAM recovery.
- `src/chipsets/vl82c481/setup-policy.inc` owns field edits, profile locks, numeric choice formatting, and special-popup selection.
- `src/chipsets/vl82c481/setup-cas.inc` owns the L2-disabled/enabled CAS popup.
- `src/chipsets/vl82c481/setup-data.inc` owns field definitions, choices, labels, help, rows, and page groups.
- `src/setup/chipset-menu.inc` owns shared navigation, paging, drawing, and help. `src/setup/layout.inc` owns the existing screen columns and text macro.

Define a field with `chipset_field label,record_byte,shift,mask,count,values,help1,help2`. It emits the existing 14-byte descriptor. `record_byte` identifies a byte in the chipset policy record, not a hardware port. The selected policy owns its register mapping. Category and validation counts come from the field boundaries.

Ordinary `values` point to a table of string addresses. `CHIP_VALUES_FAST_REGION` and `CHIP_VALUES_CACHE_REGION` select the current chipset's calculated address choices. Page values and paged popups share the same formatter. All current labels, help, choices, saved encodings, and colors remain unchanged.

For another board, supply its definition and chipset includes, then select its definition with NASM's `BOARD_DEFINITION` define. The policy callbacks retain the current names and ABI. `chipset_ui_option_text` takes AX=index, SI=values, BH=color, and ES:DI=position; it preserves caller registers and segments. `chipset_ui_choice_draw` returns carry set after drawing a special popup, or clear for an ordinary enum. Early RAM and cache discovery still require board-specific implementation and validation. Selecting a definition alone does not establish support for a new board.

The build report shows used code/data, free bytes before the fixed `F065h` compatibility entry, free bytes after `F070h`, and combined available space. Address choices are calculated instead of stored as hundreds of strings. The focused integration check is `python -B presario-800/tools/test-modular-setup.py`; it also exercises a synthetic extra field through the real consumers. `src/apm.inc` owns APM dispatch, transient session policy, and CPU idle; its dispatcher is assembled for both instruction modes.

## Dependencies

Install NASM, 86Box, Python 3.9 or later, Poppler, and Tesseract. Then clone the official 86Box ROM collection:

```powershell
git clone --depth 1 https://github.com/86Box/roms.git tools/86box/roms
```

The D824 model requires `video/cirruslogic/5428.bin`. 86Box uses this file as an availability check for its onboard GD5428 model.

The emulator executes the embedded VGA region from the 128 KiB physical image. The build does not replace the official GD5428 file.

The boot runner and chipset screen captures select 1024 KiB for the D824 onboard GD5428. This matches the fixed video memory on the Presario board.

## Build and test

Run these commands from the repository root:

```powershell
./presario-800/tools/convert-docs.ps1
./presario-800/tools/disassemble-references.ps1
./presario-800/tools/validate.ps1
./presario-800/tools/run-86box.ps1 -KeyboardTest -TimeoutSeconds 120
python -B presario-800/tools/test-setup.py --86box
python -B presario-800/tools/test-ide-options.py
python -B presario-800/tools/test-ide-pair.py
python -B presario-800/tools/test-ports.py
python -B presario-800/tools/test-ports.py --case discovery --86box
python -B presario-800/tools/test-chipset.py --86box
python -B presario-800/tools/test-post-ui.py
python -B presario-800/tools/test-setup.py --case option-rom-discovery --case boot-retry
# SCSI option-ROM tests remain deferred.
python -B presario-800/tools/test-legacy-boot.py
```

The physically accepted firmware is the current approved main pair. The current source also corrects repeated CD boot with a retained bootloader disk hook. Its pending pair uses `build/review` until physical approval. The ordinary build compiles the current source and selects nominal 60 MHz VGA memory.
The user physically validated the approved main pair on the 33 MHz/70 ns board. Other profile inputs require their own physical timing checks.
The 50 MHz variant uses the same system ROM, bus settings, and OEM resources. The Cirrus monitor policy selects non-interlaced 60 Hz for 1024x768, including after a DOS or Windows mode change.
Only the VGA memory-clock byte and VGA checksum differ. Actual clocks are approximately 50.11 MHz and 60.85 MHz.
Obsolete builds and old archives are purged. The frozen bus07 input in `reference` remains unchanged.

Use the following commands to rebuild the main pair after physical approval. Native runners and actual-ROM checks use `build` by default.

```powershell
pwsh -NoProfile -File presario-800/tools/build.ps1 -VgaClockMHz 50
pwsh -NoProfile -File presario-800/tools/verify-rom.ps1 -VgaClockMHz 50 -SelfTest
pwsh -NoProfile -File presario-800/tools/run-86box.ps1 -VgaClockMHz 50 -VgaRegisterTest -TimeoutSeconds 120
pwsh -NoProfile -File presario-800/tools/build.ps1 -VgaClockMHz 60
pwsh -NoProfile -File presario-800/tools/verify-rom.ps1 -VgaClockMHz 60 -SelfTest
pwsh -NoProfile -File presario-800/tools/run-86box.ps1 -VgaClockMHz 60 -VgaRegisterTest -TimeoutSeconds 120
python -B presario-800/tools/test-chipset.py --case profiles --case profile-locks --case policy --case ui --case ram --case integrity
python -B presario-800/tools/test-chipset.py --case integrity --86box --vga-clock 60 --screen memory --screen ram-config --screen profile-popup --screen cas-popup --screen cas-help
```

The physical images are `build/baios-presario800-vga50.bin` and `build/baios-presario800-vga60.bin`, each 128 KiB.
Each release build also updates `build/baios-presario800.bin` to the selected version. Build 60 last to retain it as the main alias.
The shared system ROM is `build/baios-presario800-system.rom`.
Each clock has a wrapper under `build/86box/vga50/roms` or `build/86box/vga60/roms`. The generic `build/86box/roms` wrapper follows the last build. Both clocks can be verified after either build order, including the first build before its sibling exists.
Native screenshots are in `build/chipset-review/review.html`; 50 MHz captures use its `vga50` subdirectory.
Explicit `-Vga141` and `-VgaBus07` without a clock retain their separate legacy build routes.
Actual-ROM RTC, Setup, chipset, bank, and cache fixtures use `BAIOS_BUILD_DIRECTORY`; its default is `build`.

Run the retained APM regressions on the main pair:

```powershell
$env:BAIOS_BUILD_DIRECTORY = 'build'
python -B presario-800/tools/test-apm.py
python -B presario-800/tools/test-apm.py --86box
```

The native command uses disposable copies of the retained Compaq VHD. It keeps text results under the selected build directory's `apm-review`. Approved APM comparison results remain in `build/apm-review`.
Its driver checks use test-only idle/wake counters; those counters are absent from production ROMs.
The APM module retains its approved interfaces and CPU idle/wake behavior. The current source leaves 5,271 bytes free: 1,303 before `F065h` and 3,968 after `F070h`.

Both approved CD boot speeds use `build` with the standard `baios-presario800-vga50.bin` and `baios-presario800-vga60.bin` names. They share one system ROM. Current CD, VGA, and input comparison results remain under `build/diagnostics/cdboot`.
Run the focused checks and open the supplied Windows 98 SE ISO for native review:

```powershell
pwsh -NoProfile -File presario-800/tools/build.ps1 -OutputDirectory build/review -VgaClockMHz 50
pwsh -NoProfile -File presario-800/tools/build.ps1 -OutputDirectory build/review -VgaClockMHz 60
$env:BAIOS_BUILD_DIRECTORY = 'build/review'
python -B presario-800/tools/test-cdboot.py
python -B presario-800/tools/test-cdboot.py --preview --iso 'presario-800/reference/media/windows98se.iso'
```

The preview uses a fresh disposable HDD and CMOS. It leaves the source ISO read-only. Select `Boot from CD-ROM`, then `Start computer with CD-ROM support`. DOS must reach its prompt with MSCDEX assigning the CD drive.
The installed D824 model needs a saved L2-disabled configuration. This changes the emulator's configuration, not the candidate firmware. Physical tests confirmed CD boot, virtual A, IDE CD access, and displaced physical A at B with the floppy controller enabled.

The supplied startup disk loads IDE and SCSI CD drivers under the same `oemcd001` name. On the tested mixed IDE/SCSI system, skipping ASPI restored IDE CD access and physical B reads. The exact driver interaction is unresolved. `FLASHPT.SYS` produced the observed PCI read error. Use step-by-step startup to skip the unneeded SCSI driver stack when booting the IDE CD. The supplied ISO remains unchanged.

Preview and apply build cleanup after stopping emulators:

```powershell
pwsh -NoProfile -File presario-800/tools/clean-build.ps1 -WhatIf
pwsh -NoProfile -File presario-800/tools/clean-build.ps1
python -B presario-800/tools/test-build-paths.py --build
```

Cleanup retains the approved pair, the pending pair in `build/review`, dependencies, original card VHD and current review results. It deletes obsolete version folders, existing archives, completed VMs and scratch media. It creates no history copies.
Current Setup screenshots use `build/chipset-review/setup`. Cleanup also removes completed capture VMs under `chipset-review/vga50`, keeping the adjacent screenshots and HTML results.
Current serial screenshots, logs and NVR results use `build/chipset-review/serial-addresses`. The card-boot screenshot remains at `build/card-boot.png` and survives cleanup.
The retained SpeedSys input lives at root `reference/software/speedsys/4.78/SPEEDSYS-code.bin`. Cleanup removes completed analysis output from `build/tmp` and retains the empty scratch parent for existing commands.

For an untimed setup preview, close the existing IDE preview and run:

```powershell
python -B presario-800/tools/test-ide-pair.py --setup-entry
```

This invalidates only the disposable VM settings signature. The production CMOS recovery notice then waits for Delete.
The helper keeps the prior VM CMOS bytes in `nvr/setup-entry-backup.nvr`. The flash ROM is unchanged.

The validation command finds `86Box.exe` on `PATH` first. It then checks the existing WinGet location.

If 86Box is in a different location, supply its executable path:

```powershell
./presario-800/tools/validate.ps1 -EmulatorPath 'tools/86box/86Box.exe'
```

The build creates `presario-800/build/baios-presario800-system.rom` and `presario-800/build/baios-presario800.bin`.

Use the complete 128 KiB `baios-presario800.bin` image for the first hardware test. Do not program the 64 KiB system-only ROM by itself.

The validation command builds twice and compares hashes. It checks ROM structure and searchable manuals.
It also checks actual-ROM RTC, setup, IDE, devices, legacy-disk, RAM mapping, L2 probing, and chipset contracts.
The actual-ROM checks require the Python `unicorn` package.

It then runs 86Box checks for startup state, VGA output, missing disks, invalid boot sectors, and ATA command errors. It also checks CHS and LBA28 access on an 8 GiB disk.
The RTC guest checks cold/warm clock initialization, daily alarm delivery and cancellation, midnight rollover, and leap dates.
The device guest checks the retained VGA screen, real Save/warm restart, and saved-device cold reload in separate disposable VMs.
It uses the 3E8h/2E8h pair because the D824 emulator incorrectly models the target's 2E8h/2E0h pair as 3E8h/2E0h.
The actual-ROM device model checks all four datasheet address pairs. No firmware mapping changes accommodate this emulator limitation.
The chipset VGA checks retain screenshots in `build/chipset-review/review.html`.
86Box does not model VL82C481 L2 SRAM or tags. Its summary can show `Not detected` with this ROM.
The synthetic SRAM model checks bank, capacity, and register behavior. Neither model establishes physical electrical timing.

Run `presario-800/build/diagnostics/RTCCHECK.COM` for a read-only physical clock check. `SPRTC.COM` runs the original Speedsys rollover sequence and restores the saved clock.
Run `python -B presario-800/tools/test-rtc.py --dos-speedsys` for that sequence in a disposable clean-DOS backup copy.

The focused keyboard check injects set-1 bytes through the emulated 8042. It checks IRQ1, the BDA ring, `INT 16h`, modifier and lock handling, LED acknowledgements, OEM software warm entry, and explicit controller-reset contrasts.

It also leaves input pending at warm entry and exercises Pause/resume at two POST boundaries. The Pause check includes a pending byte with interrupts disabled, releases, ACKs, and a fresh function key after resume.

Run the mouse and EDIT checks on disposable copies of the retained backup:

```powershell
python -B presario-800/tools/mouse-test.py 'presario-800/reference/media/dos.vhd'
python -B presario-800/tools/mouse-test.py 'presario-800/reference/media/dos.vhd' --no-mouse
python -B presario-800/tools/mouse-test.py 'presario-800/reference/media/dos.vhd' --edit
python -B presario-800/tools/mouse-test.py 'presario-800/reference/media/dos.vhd' --edit --no-mouse
```

Mouse and floppy checks remove their temporary VMs after each run. Add `--keep-artifacts` to retain a VM for diagnosis. The platform runner removes its generated test disk unless `-KeepArtifacts` is set. Original backups remain unchanged.

Optional `build.ps1 -MouseDiagnostic` and `build.ps1 -KeyboardDiagnostic` builds use separate diagnostic directories. The keyboard diagnostic adds a ten-second POST input window and scan counters. The normal ROM contains neither diagnostic delays nor scan tracing. A diagnostic build also replaces the emulator wrapper. Rebuild normally before normal-ROM checks.

Preview build cleanup with `./presario-800/tools/clean-build.ps1 -WhatIf`. Run without `-WhatIf` after emulators stop. It purges obsolete output and preserves the current artifacts listed above.

At task handoff, remove completed test VMs and their disposable media, including chipset capture VMs and retained CD-ROM test copies. Keep the current PNG/HTML review and comparison results. A visible preview or a VM needed for the current diagnosis stays until that work ends. Run Python with `-B` to avoid bytecode caches.

It also checks CPU and chipset cache controls after each boot. Software warm-reset cases enter from both slow and fast states. The emulator does not implement the chipset's fast-clock command; physical speed needs a hardware test.

The timeout checks use an emulator-only BIOS build with a controlled ATA status seam. The delivered ROM does not contain that seam.

Use `run-card-vhd.ps1` to test a disposable dynamic VHD without fixed disk parameters. The emulator can write to this file. Never pass the original backup:

```powershell
Copy-Item 'presario-800/reference/media/dos.vhd' 'presario-800/build/card-copy.vhd'
./presario-800/tools/run-card-vhd.ps1 -ImagePath 'presario-800/build/card-copy.vhd'
```

The command reads the disk geometry from the VHD footer. It saves the emulator window to `presario-800/build/card-boot.png`.

The additional DOS memory checks use the retained card backup. Original command and fixture details remain at `112b3ac58770e6a97b1ea0e9535f1a13cb34c45c:presario-800/docs/plans/memory.md` in Git.
The expanded RAM checks add 8 MiB emulator runs and a 4 MiB XMS allocation with HIMEM-only and EMM386/LOADHIGH.
Run `python -B presario-800/tools/test-memory-banks.py` for the controlled bank decoder checks. This requires the Python `unicorn` package.
Run `python -B presario-800/tools/test-external-cache.py` for absent, valid, undersized, and corrupt L2 SRAM contrasts and reset-state checks.
Neither 86Box nor the controlled SRAM fixture proves physical cache-tag timing or coherency. Use hardware memory tests for those results.
Run `test-emm-reset.ps1 -ImagePath <backup>` for the disposable DOS reset check. Add `-KeypadDelete`, `-ProductionRom`, or `-NegativeControl` for its contrasts.
`test-speedsys-rom-id.py` requires the retained unpacked Speedsys 4.78 code at `../reference/software/speedsys/4.78/SPEEDSYS-code.bin`.
The script checks its SHA-256 before running the original scan against OEM and generated ROM bytes. That application fixture is not part of a fresh checkout.

## Hardware POST codes

The system BIOS writes these values to diagnostic port `80h`:

| Code | Last completed stage |
| --- | --- |
| `10h` | The reset vector reached the system BIOS startup entry. |
| `20h` | The chipset registers were programmed. |
| `11h` | The BIOS recognized a warm reset. |
| `30h` | The early low-memory test passed. |
| `21h` | The uncached bank-0 probe started with the optional side enabled. |
| `22h` | The extra side failed the independence check. Bank 0 uses onboard 4 MiB. |
| `23h` | Both probe patterns passed. Bank 0 uses 8 MiB. |
| `24h` | Software warm entry retained the RAM configuration. |
| `25h` | Bank 1 probe started. |
| `26h` | Bank 1 was accepted. |
| `27h` | Bank 1 was rejected. |
| `28h` | Bank 2 probe started; also reused when system shadow setup starts after RAM detection. |
| `29h` | Bank 2 was accepted. |
| `2Ah` | Bank 2 was rejected. |
| `2Bh` | Bank 3 probe started. |
| `2Ch` | Bank 3 was accepted. |
| `2Dh` | Bank 3 was rejected. |
| `2Eh` | A detected bank would exceed the 64 MiB selection limit; that bank was skipped. |
| `18h` | Sequential mapping selected because interleave is disabled or no eligible pair exists. The bounded firmware RAM check follows. |
| `19h` | Interleave mode 1 selected: banks 0 and 1. |
| `1Ah` | Interleave mode 2 selected: banks 0 and 3. |
| `1Bh` | Reserved for interleave mode 3 (banks 1 and 2); disabled on this board. |
| `1Ch` | Interleave mode 4 selected: banks 2 and 3. |
| `1Dh` | Interleave mode 5 selected: banks 0/1 and 2/3. |
| `1Eh` | Reserved for interleave mode 6 (banks 0/3 and 1/2); disabled on this board. |
| `12h` | The optional L2 card direct SRAM presence check started. |
| `13h` | The L2 capacity, independence, and SRAM data checks started. |
| `14h` | The SRAM test failed; L2 was disabled. |
| `15h` | The detected L2 card passed and normal cache mode was initialized. |
| `16h` | The L2 card did not respond; L2 was disabled. |
| `40h` | The retained VGA region was copied to shadow RAM and protected. |
| `48h` | Keyboard initialization completed. |
| `50h` | The IVT, BDA, PIC, PIT, Super I/O, and AT prerequisites are ready. The retained VGA initializer is starting. |
| `60h` | The retained VGA initializer returned. The BIOS installed and read back the retained video-handler segment. |
| `70h` | ATA IDENTIFY is starting. |
| `80h` | The primary disk is present. The BIOS is starting `INT 19h`. |
| `90h` | Ctrl+Alt+Delete requested an OEM-style software warm restart. |
| `91h` | The keyboard was released and ROM shadow controls were cleared. Warm entry is next. |
| `94h` | The dedicated warm entry was reached. No CPU reset was requested. |
| `A1h` | The legacy disk read used 16 heads and 63 sectors per track. |
| `A2h` | The legacy disk read used 32 heads and 63 sectors per track. |
| `A4h` | The legacy disk read used 64 heads and 63 sectors per track. |
| `A5h` | PS/2 mouse initialization started. |
| `A6h` | PS/2 mouse initialization succeeded. |
| `A7h` | No responding PS/2 mouse was initialized. Boot continues. |
| `A8h` | The legacy disk read used 128 heads and 63 sectors per track. |
| `AFh` | The legacy disk read used 255 heads and 63 sectors per track. |
| `B0h` | Reference-derived AT platform initialization started. |
| `B1h` | Both DMA controllers were reset. |
| `B2h` | The legacy CHS request was invalid. The BIOS returned an error. |
| `B3h` | The legacy ATA transfer failed. The BIOS returned an error. |
| `B4h` | The OEM keyboard power-on settle or first interface-disable command failed. |
| `B5h` | The OEM auxiliary-interface disable command failed. |
| `B6h` | The OEM controller-output drain failed. |
| `B7h` | The target MR BIOS output-port command `D1h` failed after controller self-test. |
| `B8h` | The target MR BIOS output-port value `CFh` failed. |
| `B9h` | The floppy controller, Port `61h`, and PIT channel 1 prerequisites were programmed. |
| `BAh` | The target MR BIOS output-port and A20 initialization completed. |
| `C0h` | Keyboard-controller initialization started. |
| `C1h` | The keyboard interface was disabled and its output was drained. |
| `C2h` | The keyboard-controller self-test passed. |
| `C3h` | The controller command byte was accepted. |
| `C4h` | The keyboard interface was enabled and settled. |
| `C5h` | The OEM keyboard reset transaction started. |
| `C6h` | The keyboard acknowledged reset. The BIOS is waiting for BAT. |
| `C7h` | The keyboard returned BAT success `AAh`. |
| `C8h` | BAT timed out. The BIOS is retrying the OEM reset transaction. |
| `C9h` | The keyboard interface was enabled after BAT success. |
| `CAh` | IRQ1 and the PIC cascade were unmasked immediately before boot. |
| `D0h` | The keyboard requested reset-command retransmission. |
| `D1h` | The keyboard returned an unexpected reset-response byte. |
| `D2h` | BAT timed out twice. |
| `D3h` | The keyboard reset command did not receive an ACK. |
| `D4h` | BAT returned an invalid byte. The CPU halted. |
| `E0h` | The system shadow comparison failed. The CPU halted in temporary RAM. |
| `E1h` | The early RAM test failed. The CPU halted. |
| `E2h` | The BIOS could not read back the expected `INT 10h` segment. The CPU halted. |
| `E3h` | No primary ATA disk was found. |
| `E4h` | All selected boot targets failed. The BIOS is waiting for a fresh retry key. |
| `E5h` | The embedded VGA ROM mapping check failed before the copy. The CPU halted. |
| `E6h` | The protected VGA shadow check failed after the copy. The CPU halted. |
| `E7h` | The initial keyboard-controller input wait or drain timed out, or a POST RAM comparison failed again at defaults. |
| `E8h` | The keyboard-controller self-test timed out, or the chipset reported a RAM parity error. |
| `E9h` | The keyboard-controller self-test did not return `55h`. |
| `EAh` | A command-byte write or keyboard-enable operation timed out. |
| `EBh` | The controller did not accept the keyboard reset command. |
| `EEh` | The warm-reset controller transaction failed. |
| `EFh` | The keyboard runtime command-byte or enable transaction failed. |

The retained VGA component is opaque. It runs during initialization, mode setting, and banner output. A final value outside this complete table shows retained VGA activity. It does not identify which call stopped or whether startup reached `60h`. A trace-capable observer is necessary to make that distinction.

If no code appears, the reset vector did not reach the startup entry or the observer did not receive port `80h` writes.

For a physical test, program the complete `presario-800/build/baios-presario800.bin` image. Cold-start the computer once. Record the final latched byte. The build checks the exact system-owned sequence. The physical card only needs to retain the final byte.

## Searchable manuals

The board jumper PDF/text remain in `presario-800/docs` and `docs/searchable`. Generic VLSI, SMC and Cirrus manuals live in categorized root `reference/`; their searchable UTF-8 text mirrors those paths under `reference/searchable`.

The conversion uses Poppler text extraction first. It uses Tesseract OCR for scanned or empty pages.

Native APM and RTC DOS checks read the source disk image from the `BAIOS_DOS_VHD` environment variable. Set it to your own DOS VHD; tests modify only disposable copies. The CD boot test accepts `--iso` and otherwise looks for `presario-800/reference/media/windows98se.iso`. These inputs are not distributed.
