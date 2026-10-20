# Stock feature coverage and ISA clock options

This audit compares the original PB430 Phoenix ROM, the ACC386 AMI ROM, the ACC2168 AMI guide, and current PB430 owners. These sources are not interchangeable. A Setup string proves that a resource exists, not that its hardware path runs on this board.

## Shadow and cache controls

Current descriptors are in `src/hardware/chipset-data.inc`. The Shadow submenu exposes all known register 02 controls:

| Control | Register field | Current coverage |
| --- | --- | --- |
| Video C000-C7FF | 02[0] | Video ROM Shadow. Required for the onboard VGA path. |
| Adapter C800-CFFF | 02[1] | Separate switch. |
| Adapter D000-DFFF | 02[2] | Separate switch. |
| E000-EFFF | 02[3] | Separate switch, constrained by the onboard VGA path. |
| System F000-FFFF | 02[4] | System ROM Shadow. |
| Global write protection | 02[5] | Shadow Write Protection. |
| Global cacheability | 02[6] | Shadow RAM Cacheable. |

System and video switches also appear in General. They edit the same saved fields, not independent mappings. No known register 02 field supplies separate cacheability for each window. The AMI guide's combined Shadow RAM Option is an alternative interface to the individual switches, not another hardware capability.

The port also exposes internal/external cache, cache burst reads and writes, separate read/write X-2-2-2 controls, cache-read wait, cache-write-hit zero wait, uncached-write wait, cache/memory wait controls and DRAM read burst. Cache size and qualification remain detected. The reference's transient tag modes and size tables are initialization state, not user timing choices. See [the register map](register-map.md) for each field and evidence level.

Posted Writes was removed at the user's request. The ACC2168 guide requires external buffers and says this option is for OEMs. Standard AT refresh stays enabled after the observed failures. Interleave remains unqualified after the failed early-boot trial. These are deliberate exclusions, not overlooked switches.

## Other stock features

Addresses below use the original ROM segments. The byte-exact source is `reference/maps/pb430-m27c1001.asm`.

| Feature | Original evidence | Current coverage or gap |
| --- | --- | --- |
| Basic Setup | E000:AD0A-B0E5 and CEF2-D487 | Time/date, drives, NumLock, UARTs, printer, floppy controller, IDE and cache controls are covered. |
| Cache sizing and cacheable ranges | F000:8F07-91E4, 9706 and 9D63-9E41 | Reference-driven detection, qualification and range setup are implemented. These are not missing user controls. |
| IDE automatic power-down | F000:95DE calls A2AA. A2C6 reads CMOS28. A2CB selects timeout table A2F7. A2DD/A2F0 send E3 to both drives. | Deferred global task BAIOS-006, very low priority. Disk spin-down is secondary and must default off. Current APM only implements CPU idle through HLT. |
| Video automatic power-down | E000:D60E label. F000:A2AA reads CMOS29. A309/A373/A3A0 configure a controller path using command CE and a timeout. | Deferred global task BAIOS-006. Monitor power saving takes priority over disk spin-down when that task starts. Exact controller timeout behavior still needs tracing. |
| Passwords | E000:D4AB, E6E4/E7BD/E898, F314/F3AF and F000:6DE0-6EAE resources | Deferred global task BAIOS-007, very low priority. Resources describe boot/setup and user/admin modes. Their complete runtime enforcement is not traced by this audit. |
| Alternate COM3/COM4 addresses | F000:3FD1/3FD9 and 4DF6/4DFA tables; 3FE4-400A and 4FFA-509E consumers | Devices exposes 338/238, 3E8/2E8 (default), 2E8/3E8 and 220/228. ACC3221 DC/DD receive the selected bases; IRQ3/4 conflict filtering remains active. |
| Language | E000:B0B5 resource and BB47 help | The stock choices select English, German, French, Spanish or Italian menus. Current menu translation is deferred. |
| Monitor type | E000:B05B resource; user hardware confirmation | Controlled by a physical jumper. No software selector is added. |
| Keyboard presence | F000:4612-4619 uses CMOS1F bit0 | Existing Halt On choices All and All Except Keyboard cover required versus optional keyboard behavior. |
| Parity errors | F000:D4DE/D4F0 messages | Current RAM test has parity-failure reporting at POST E8. A configurable parity selector is a separate question. |

The original Phoenix Setup resource has a Cache item at E000:B0E5. This audit found no shadow labels there. The port already exposes more shadow and timing controls than that stock interface.

The ACC2168 AMI guide also names Turbo/cache hotkeys, MUX clock, Weitek support, numeric tests, boot-sector protection and typematic settings. Those descriptions alone do not establish missing Phoenix features. Its stated 128 KiB cache maximum differs from the actual PB430 512 KiB sequence. Keep guide features separate from traced board behavior.

This is a source-backed feature inventory. It does not prove exhaustive equivalence for every dynamic stock-ROM path. The table identifies the remaining untraced owners explicitly.

## ISA clock divider

**Chipset > Bus and ROM Timing > ISA Clock Divider** offers /2, /3, /4, /5, /6, /8 and /10 in numeric order, with one entry per divisor. The resolved jumper default is marked on /4 or /3. The labels include the fixed final divide by two. The existing ISA zero-wait and extra-wait controls change transaction waits, not bus frequency.

Evidence:

- PB430 F000:E081-E0A7 selects register 06 as 13, 33 or B7 from port 78. The current jumper selection 5 selects B7. `startup-core.inc` preserves that selection. The stock cold-resume fragment repeats it.
- ACC386 F000:093A-094F reads its Setup choice and writes the byte at table 092A. The table is `00 14 13 17 12 11 15 10 18`. Its automatic branch uses separate clock-category tables at 08D4/08DB.
- ACC2046 revision 1.2, printed page 27, and ACC2087 revision 1.1, printed page 76, agree on register 06[4:0] for CLKSRC divisors. Both describe SYSCLK as half the selected AT clock source.
- The manuals differ outside that field: 2046 reserves 06[7:5], while 2087 assigns DMA timing divisors. The external source at 18 is 16 MHz on 2046 but 24 MHz on 2087. Preserve upper bits and do not expose an assumed external frequency.
- The 2087 table labels the low field `R`, despite describing programming it. The 2046 table and ACC386 writes support a writable-selector hypothesis. Physical ACC2168 readback and clock behavior still need confirmation.

For a 33.333 MHz CLKSRC, the related-chip model gives `ISA MHz = CLKSRC MHz / selector divisor / 2`. These frequencies are conditional, not measurements. Do not use the multiplied CPU-core frequency.

| Raw selector divisor | Low field | Whole byte with current upper bits A0 | Conditional ISA MHz |
| --- | --- | --- | --- |
| /5 | 10 | B0 | 3.33 |
| /4 | 15 | B5 | 4.17 |
| /3 | 11 | B1 | 5.56 |
| /2.5 | 12 | B2 | 6.67 |
| /2 | 17 | B7, current | 8.33 |
| /1.5 | 13 | B3 | 11.11 |
| /1 | 14 | B4 | 16.67 |

B3 is the first faster candidate. B4 is a much larger increase. A masked write is `(old & E0) | selector`; copying the ACC386 whole byte would also alter the upper controls.

The saved selector occupies chipset-record byte22 bits6:4. Selector zero retains the jumper default. Existing explicit selectors keep their hardware meanings. The popup maps the default and an equal explicit selector to one visible entry; confirming an unchanged entry preserves the saved encoding. Normal and Fast preserve it. The late cache continuation applies only register06[4:0], after the complete stock cache sequence and memory policy, before option-ROM discovery and boot. Earlier device detection uses the stock clock. Ordinary reset and timing restoration return the low field to the jumper selection before stock cache owners; service05/0A resumes leave the running clock alone. No writes enter the transient cache window.

The VGA is local bus. The user accepts the physical clear-CMOS jumper as recovery from an ISA clock lockup. No new automatic ISA recovery mechanism is added. Only a detected RAM comparison error starts DRAM recovery; an interrupted POST preserves saved settings. The final /3 menu value is the first faster comparison on the tested 33 MHz configuration.

Software checks exercise menu Save, Defaults, Discard, cold/warm reset and successful disk/serial transfers under the selected setting. They do not measure ISA frequency or electrical card tolerance. Physical qualification still includes clock measurement, floppy DMA, storage transfers with data comparison and installed ISA cards.

## CPU and SMI follow-up

Repository tasks BAIOS-004 and BAIOS-005 cover SMI/SMM and CPU-specific optimization after the queued shared-cache work. SMI is the interrupt that enters System Management Mode. Enabling it requires CPU support, controller routing, usable protected memory and a valid return path.

The current central processor reference is `reference/processors/amd/Am5x86-19751c.pdf`. Its WB/WT pin description states that reset selects write-back capability. Later fills also sample the pin. SRESET does not resample that pin or reset the cache-control state. A software option cannot supply absent board coherency wiring. Use the manual's cache, snoop, reset and SMM contracts together.

Cyrix/IBM 5x86 performance registers and Intel P24T enhancements remain separate vendor-specific work. Their datasheets were not present under `reference/processors/` at this audit. Do not apply one vendor's register interface to another CPU merely because both are called 5x86.
