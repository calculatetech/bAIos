# ACC2168 registers and VLSI comparison

This is the working register map for the PB430, based on the supplied manuals, both reference ROMs, and physical results through 2026-10-16. It is an analysis reference, not a list of settings to write. Unknown fields remain unknown.

The ACC does pack several controls into one byte. Some controls use one bit. Others use two or more bits as an encoded value. A byte can also mix timing, memory routing, cache modes, and status. The VLSI VL82C481 in the Presario uses the same broad design pattern, but its addresses and field positions do not transfer to ACC.

## Sources and evidence levels

| Label | Evidence | What it establishes |
| --- | --- | --- |
| M | [ACC2168 AMI guide](../../reference/chipsets/acc/AC216811.txt), Advanced CMOS Setup and CMOS map | Named controls and some chipset bit positions. This is not a full chipset data sheet. |
| P | [PB430 instruction map](../reference/maps/pb430-m27c1001-f000-cfg.txt) and [stock behavior](../reference/maps/stock-behavior.md) | Actual PB430 operations, masks, tables, ordering, and consumers. A write alone does not name an electrical function. |
| A | [ACC386 instruction map](../reference/maps/acc386-f000-cfg.txt) and [complete source](../reference/maps/acc386.asm) | Meanings derived from Setup options and their code paths. This ROM identifies ACC2046, so these are comparison findings for ACC2168. |
| D46 | [ACC2046 revision1.2 data sheet](../../reference/chipsets/acc/ACC2046-rev1.2.pdf), pages23-35 | Manufacturer definitions for the chipset named by ACC386. These remain comparison evidence for ACC2168. |
| D87 | [ACC2087 revision1.1 data book](../../reference/chipsets/acc/ACC2087-rev1.1.pdf), printed pages75-86 | Later related-chip definitions. Some fields differ from D46. |
| H | User photographs and physical probe results, transcribed in [hardware evidence](hardware-evidence.md) | Values read on this board and measured effects for the reported workload. |
| V | [VL82C481 data sheet](../../reference/chipsets/vlsi/vl82c481.pdf), pages 18-24, and [searchable text](../../reference/searchable/chipsets/vlsi/vl82c481.txt) | Documented VLSI fields. These do not establish ACC field meanings. |

ROM addresses below use F000 offsets. PB430 file offsets for this region add `10000h`. ACC386 file offsets equal the listed offsets. All register numbers, masks, and byte values are hexadecimal. Binary strings run from bit7 on the left to bit0 on the right. `T` means a clock period in the cited timing definition.

Do not confuse CMOS option storage with chipset registers. The manual's CMOS36 bits7:6 select refresh, but the ACC386 consumer writes that choice into chipset05 bits1:0. PB430 Phoenix CMOS layout, this AMI manual, and the ACC386 ROM are not interchangeable layouts.

## Timing options at a glance

Baseline means the supplied2026-10-16 `ACCNOW.TXT`, with Fast Memory Writes and Slow Refresh enabled. ACCPROF restores that baseline between chunks and before DOS output. Its temporary profile is a separate column below. The user reports14.0MiB/s baseline and15.7MiB/s trial, a12.1% throughput gain. That result qualifies the combination as faster in this workload. It does not isolate the contribution of each field. The message did not separately report the third row, diagnostics, or long-term stability.

At33MHz,1T=30.3ns,1.5T=45.5ns,2T=60.6ns,3T=90.9ns,4T=121.2ns and5T=151.5ns. Field codes below are binary, before shifting into the register. They are not complete bytes to write. The source comparison later in this document supplies page references. **Common** means the2046/2087 definitions agree. **2087** means that definition is a working2168 hypothesis. **Conflict** means the two manuals differ. The trial column records intended decoding under this model, not measured pin widths.

### DRAM access timing

| Setting / register bits | Current baseline | Available encodings | ACCPROF trial / evidence |
| --- | --- | --- | --- |
|RAS precharge,0B[7:6]|00:2T,60.6ns|00/01/10/11:2/3/4/5T|Unchanged. Common. Already minimum.|
|Read RAS-to-CAS delay,12[7]|0:2T,60.6ns|0:2T;1:3T|Encoded value unchanged. CAS advance can move the effective edge to1.5T. Common.|
|Write RAS-to-CAS delay,0B[5]|0:2T,60.6ns|0:2T;1:3T|Unchanged. Common write definition.|
|Read CAS pulse,0B[3:2]|01:2T,60.6ns|00/01/10/11:1/2/3/4T|00 plus half-clock advance: intended1.5T,45.5ns.2T/3T corroborated by2168 guide and ROM. Unextended1T failed.|
|Write CAS pulse,0B[1:0]|00:1T,30.3ns|00/01/10/11:1/2/3/4T|Unchanged. Common. Part of the measured Fast Writes gain.|
|Write CAS precharge,0B[4]|0:1T,30.3ns|0:1T;1:2T|Unchanged.2087 explicitly calls this write precharge.|
|Read CAS precharge,12[6]|0: Setup labels this1T (inferred)|1:2T. Zero-state1T is an inference|Label changed from Short at user request; hardware value unchanged.2087 only;2046 reserves this bit. A half-clock advance can shorten the high interval.|
|Read CAS advance,16[1:0]|00:no advance|00/01:none;11:0.5T earlier;10:unspecified|11:15.2ns earlier.2087 model; tested as part of the faster combination.|
|Write CAS advance,16[3:2]|00:no advance|00/01:none;11:0.5T earlier;10:unspecified|Unchanged.2087 only. Not yet tried.|
|RAS timeout,01[4]|1:disabled|0:enabled;1:disabled|0:enabled. Common. Duration is not specified by this bit.|

### Cache and transfer controls

| Setting / register bits | Current baseline | Available encodings | Physical result or qualification |
| --- | --- | --- | --- |
|DRAM read burst,04[4]|1:enabled|0:off;1:on|Common. Clearing it locked the board.|
|L2-to-L1 read burst,04[3]|0:disabled|0:off;1:on|Common. Enabling worsened effective RAM reads to343ns.|
|L2 read wait,04[5]|0:zero wait|0:0wait;1:1wait|Common. Already the faster selection.|
|Uncached486 page-hit write wait,04[6]|0:one wait|0:1wait;1:0wait|Common. Zero-wait setting not yet tested. Its documented scope is uncached operation.|
|Posted-write buffer,04[7]|0:disabled|0:off;1:on|2168 guide names it and requires four245 buffers. Board support not established.|
|L2 write-hit zero-wait enable,14[6]|0:disabled|0:off;1:on|2087 only. Disabled-state wait count is not specified here. Not yet tested.|
|L2 X-2-2-2 burst,18[7]|0:disabled|0:off;1:force X-2-2-2|2087 only;2046 reserves it. Off-state burst schedule unspecified. Not yet tested.|
|Sampling/off-cycle delay,18[5]|0|2046:0=1T sampling delay,1=remove it.2087:1=add DRAM/ISA off-cycle wait|Conflict. S=20 trial gave no read gain, including with Fast Writes.|
|Posted/cache-write wait,18[4]|0;2046 calls this1wait|2046:0=1wait,1=0wait.2087:1=1wait for cache/post writes|Conflict. T=10 trial gave no gain. Posted writes currently off.|

### Refresh controls

| Setting / register bits | Current baseline | Available encodings | ACCPROF trial / evidence |
| --- | --- | --- | --- |
|Refresh interval divisor,05[1:0]|11:/8, nominal120us|00/01/10/11:/1,/2,/4,/8; nominal15/30/60/120us|Unchanged. F8 improved13.6 to14.0MiB/s.|
|Refresh RAS active width,19[7:6]|00:4T or5T,121.2 or151.5ns|2046 codes00/01/10/11:4/3/2/1T.2087 table:5/4/3/2T|Unchanged. Conflict;2087 default prose also disagrees with its table.|
|Refresh RAS precharge,19[5:4]|00:4T,121.2ns|00/01/10/11:4/3/2/1T|10:2T,60.6ns. Common. Tested in the faster combination.|
|Refresh burst count,19[2:0]|000:one|000..111:1..8 refresh cycles|Unchanged. Common.|
|Burst refresh enable,18[1]|0:disabled|0:off;1:on|2087 calls it hidden burst refresh. H=02 trial gave no gain.|
|Standard AT refresh,18[0]|0:enabled|0:on;1:off|Unchanged. Common. Disabling requires another working refresh source.|
|AT refresh burst count,16[5:4]|00:one|00/10:1;01:2;11:4 per request|Unchanged.2087 only. Separate from19's DRAM burst count.|

### Other speed controls and shadowing

| Setting / register bits | Current baseline | Available encodings | Scope |
| --- | --- | --- | --- |
|ADS delay,1A[7]|0:disabled|0:off;1:on|2168 guide recommends off. Already off.|
|8-bit AT-bus zero-wait,14[4]|0:disabled|0:off;1:on|2087 only. ISA access, not CPU DRAM timing.|
|16-bit AT-bus zero-wait,14[3]|0:disabled|0:off;1:on|2087 only. ISA access, not CPU DRAM timing.|
|Extra ISA wait,18[6]|0:no extra wait|0:none;1:+1wait|2087 only. Already the faster selection.|
|ROM zero-wait,16[6]|0:disabled|0:off;1:on|2087 only. ROM access, not extended RAM.|
|Shadow cacheability,02[6]|1:enabled|0:off;1:on|2168 guide and ROM corroborate. Already enabled.|
|Shadow write protection,02[5]|1:protected|0:writable;1:read-only|Global across shadow windows. Copying needs writable RAM.|
|F000 shadow,02[4]|1:enabled|0:ROM;1:shadow RAM|System BIOS.|
|E000 shadow,02[3]|1:enabled|0:ROM;1:shadow RAM|Current onboard VGA path requires this map.|
|D000 shadow,02[2]|0:disabled|0:ROM/device;1:shadow RAM|64KiB optional ROM window.|
|C800 shadow,02[1]|0:disabled|0:ROM/device;1:shadow RAM|32KiB optional ROM window.|
|C000 shadow,02[0]|1:enabled|0:ROM;1:shadow RAM|Current onboard video requires the copy.|

Bank arrangement, line size, cache sizing and clock-source routing are outside this menu. The legacy01[7:6,1:0] interleave wait fields are documented in the comparison table below, but are not established as active timing controls in the running page-mode configuration. No unused/reserved field is presented as an available speed setting.

The profile's14.0-to15.7MiB/s result corresponds to272.48-to242.97ns per four useful bytes, about29.50ns less. That is close to one30.30ns bus clock. This supports the shorter-cycle hypothesis without proving which changed field caused the gain.

## Captured register inventory

These are the 28 registers in the original ACCDUMP captures. The expanded reader also captures14,16,19, for31 registers total. The2026-10-16 live capture below supplies their readbacks. Unlisted registers are not known to be absent. The processor reports CR0=`00000010`, port78=`1D`, and port92=`FC` in both original captures. These are snapshots, not reset defaults or writable-bit masks.

| Register | L2 on | Bits7..0, L2 on | L2 off | Established role or remaining question |
| --- | --- | --- | --- | --- |
| `00` | `A9` | `10101001` | `A9` | DRAM topology in low nibble; bit7 has a post-shadow/remap-related consumer. P/A |
| `01` | `BF` | `10111111` | `BF` | Automatic configuration byte; PB430 writes92 during SRAM sizing and93 afterward. Electrical fields unresolved. M/P |
| `02` | `F9` | `11111001` | `F9` | Shadow windows, shadow write protection, and shadow cacheability. P/A |
| `03` | `10` | `00010000` | `10` | ACC386 parity and Weitek controls. Other bits unresolved. A |
| `04` | `15` | `00010101` | `14` | L2 enable, posted-write enable, and other configuration bits. M/P/H |
| `05` | `9C` | `10011100` | `9C` | DRAM mode/branch inputs; ACC386 refresh divider in low two bits. P/A |
| `06` | `B7` | `10110111` | `B7` | PB430 jumper-selected whole byte; ACC386 AT-bus-clock selection. P/A |
| `07` | `F4` | `11110100` | `F4` | PB430 preservesE0 and selects low bits14 or18. Meaning unresolved. P |
| `08` | `F0` | `11110000` | `F0` | Captured value; no field meaning established here. H |
| `09` | `0F` | `00001111` | `0F` | Captured value; no field meaning established here. H |
| `0A` | `04` | `00000100` | `04` | Bit2 set before the stock SRAM probe. Meaning unresolved. P |
| `0B` | `15` | `00010101` | `15` | CAS read width in bits3:2; other bits belong to automatic configuration. M/A/H |
| `0C` | `0C` | `00001100` | `0C` | Part of cache-dependent range programming0C-11. P |
| `0D` | `80` | `10000000` | `80` | Part of cache-dependent range programming0C-11. P |
| `0E` | `00` | `00000000` | `00` | Part of cache-dependent range programming0C-11. P |
| `0F` | `00` | `00000000` | `00` | Part of cache-dependent range programming0C-11. P |
| `10` | `00` | `00000000` | `00` | Part of cache-dependent range programming0C-11. P |
| `11` | `00` | `00000000` | `00` | Part of cache-dependent range programming0C-11. P |
| `12` | `09` | `00001001` | `09` | Low two bits participate in DRAM topology; upper nibble is automatic configuration. M/P |
| `13` | `00` | `00000000` | `00` | Four two-bit bank-routing fields. P |
| `18` | `00` | `00000000` | `00` | Automatic configuration; bit5 also appears in SRAM prerequisites. Meaning unresolved. M/P |
| `1A` | `24` | `00100100` | `2C` | ADS delay, transient cache modes, and other configuration bits. M/P/H |
| `1B` | `10` | `00010000` | `10` | ACC386 uses bit0 in fast/slow speed selection. Other bits unresolved. A |
| `1C` | `FE` | `11111110` | `FE` | ACC386 bit3 controls the polarity used for1B bit0. Other bits unresolved. A |
| `1D` | `F0` | `11110000` | `F0` | PB430 qualified cache-size table. P |
| `1E` | `7B` | `01111011` | `5B` | Cache-size table plus late activation state in bit5. P/H |
| `25` | `02` | `00000010` | `02` | Captured value; no field meaning established here. H |
| `26` | `00` | `00000000` | `00` | Captured value; no field meaning established here. H |

Only04 bit0,1A bit3, and1E bit5 differ between the L2 captures. That is the combined stock cache-mode transition, not three independent tuning switches. A captured zero does not establish that a field is unused.

## ACC fields with specific evidence

| Register | Bits / mask | Kind | Meaning or exact observed behavior | Evidence and limits |
| --- | --- | --- | --- | --- |
| `00` | `3:0 / 0F` | Encoded topology | Low nibble of selected DRAM map byte | P98BC-9D60, table8D83. Together with12[1:0], not a wait count. |
| `00` | `7 / 80` | Conditional control | PB430 sets after shadow copy except mode2/map9; ACC386 Remap Memory option clears it when disabled | P94B1-94E7; A0805-0823,111E-1133. Exact PB430 address effect remains unresolved. Preserve its stock prerequisite. |
| `01` | `7:0 / FF` | Unsplit byte | Automatic configuration; actual writes92/93/90 in references | M auto list; P8FE0-8FEC,9142-914E; A0AE1-0AFE. See D46 comparison below for page-interleave fields. ACC2168 equivalence is unproved. |
| `02` | `4:0 / 1F` | Five window controls | Bits0/1/2/3/4 select C0000-C7FFF / C8000-CFFFF / D0000-DFFFF / E0000-EFFFF / F0000-FFFFF shadow windows | P shadow owners9325 onward and range consumers; A shadow setup. |
| `02` | `5 / 20` | Switch | Shadow write protection in the PB430 copy/map/protect sequence | P9325 onward; reset7EE2-7EF3 clears it. Does not mean all RAM write-protected. |
| `02` | `6 / 40` | Switch | Shadow RAM cacheable | A0BF2-0C0B; M names option. PB430 cache_ranges also sets40. |
| `03` | `4 / 10` | Inverted switch | Parity checking:0 enabled,1 disabled in ACC386 | A0BC8-0BD9 follows named Memory Parity Error Check option. Not physically exercised as a PB430 override. |
| `03` | `2 / 04` | Switch | Weitek present/enable in ACC386 | A0BD9-0BEF. Not a DRAM timing bit. |
| `04` | `0 / 01` | Switch in a sequence | External cache enable | P975E-9769, reset owners; H14->15. Must retain complete activation/flush sequence. |
| `04` | `7 / 80` | Switch with board prerequisite | Posted-write buffer enable | M POST Write; A1527-1533. Manual requires four245 transceivers between CPU and memory buses. PB430 wiring support is not established. |
| `04` | `6:4 / 70` | Unsplit configuration group | Remaining upper bits named under Auto Configuration | M/P table91EA/9232. Do not label each bit a wait state. Bit7 is separately documented above. |
| `04` | `4,2,1 / 16` | Size/hardware-correlated tuple | ACC386 clears17 with AND E8, then ORs17/13/05 according to cache size and05 bit6 | A13E6-1427. Bit0 is also included in that operation. This couples configuration to size and is not three decoded timing switches. |
| `05` | `1:0 / 03` | Two-bit selector | ACC386 slow-refresh divider:00 CLKIN,01 /2,10 /4,11 /8 | A0952-0967, named option2255. M gives15/30/60/120 microseconds. ACC2168 field location is inferred from the comparison ROM, not explicitly documented by M. |
| `05` | `4 / 10` | Mode-related switch | Set in PB430 mode1 DRAM setup and ACC386 geometry/page-sequencer path | P9909-99C6; A0F67-0FDD. Does not establish portable page-mode polarity. |
| `05` | `5 / 20` | Branch input | Selects ACC386 clock table and geometry path | A08F9-0907,0F52. Not proved to be page-mode enable. |
| `05` | `6 / 40` | Branch input | Selects ACC386 automatic configuration rows and posted-write branch | A0AD8 onward,1500 onward. Physical meaning unresolved. |
| `06` | Whole byte | Clock selector | ACC386 AT Bus Clock Source writes a table byte | A08EE-0951. PB430 E081-E0A7 selects13/33/B7 by port78. Do not apply ACC386's whole byte to PB430. |
| `07` | `4:0 / 1F` | Observed update mask | PB430 writes14 or18 while preserving bits7:5 | P91EA/9232. Mask alone does not prove a five-bit timing field. |
| `0A` | `2 / 04` | Prerequisite switch | Set before SRAM probing | P8F07 onward. Name and electrical effect unknown. |
| `0B` | `3:2 / 0C` | Two-bit selector | CAS read pulse: shifted field04/08 corresponds to the reference's2T/3T choices | M Auto Configuration/CAS; A0B84-0BA2; H19 slower than15. D46/D87 name00/0C as1T/4T. Neither is physically qualified on PB430. C1 tested00 and failed, then hard-locked. It is now withdrawn. |
| `0B` | `7:4 / F0`, `1:0 / 03` | Unsplit configuration groups | Automatic configuration parameters | M. P writes04/05/15. See the related-chip field table below. The manual for ACC2168 does not decode them. |
| `0C-11` | Six-byte group | Cache-dependent ranges | Absent all00;128 KiB:0B,40,0C,80,00,00;256/512 KiB:0C,80,00,00,00,00 | P9D63-9E41. Address encoding not independently decoded. Not DRAM timing. |
| `12` | `1:0 / 03` | Encoded topology | Upper two bits of the selected map byte | P98BC-9D60. Complements00[3:0]. |
| `12` | `3 / 08` | Probe-related control | Cleared at mode1 entry, set in intermediate0A map | P9909-99C6. Function beyond observed map sequence unresolved. |
| `12` | `7:4 / F0` | Unsplit configuration group | Automatic configuration | M. A0B2E-0B3D preserves0B and takes tableF4; bit2 therefore also needs separate investigation. |
| `13` | `7:6,5:4,3:2,1:0` | Four two-bit fields | For original bank i, lane i receives `(sorted_position-i)&3` | P bank-routing owner98BC-9D60; [port implementation](../src/hardware/memory.inc).00 is unchanged routing. These are route offsets, not four capacities. |
| `18` | `7:0 / FF` | Unsplit configuration byte | Automatic configuration; PB430 table preserves8C and supplies20 or00 | M/P. Bit5 set before SRAM probe. No proved RAS/precharge names. |
| `1A` | `7 / 80` | Switch | ADS delay:0 disabled,1 enabled | M explicitly names bit7; A0BA5-0BBE. Manual recommends disabled. |
| `1A` | `4:3 / 18` | Observed mode group |00 normal after activation;08 used around fill/holdoff;10 SRAM probing | P8F72 onward,9631/968E/9748-978A.18 not qualified. Treat as a sequence-controlled group, not two independent speed options. |
| `1A` | `6 / 40` | Preserved/unknown | PB430 table preserves it; AMI lists it under automatic configuration | M/P. Do not copy the emulator's L1 interpretation into hardware policy. L1 is controlled through CR0 in PB430. |
| `1A` | `5 / 20`, `2 / 04`, `1:0 / 03` | Unresolved | Common final value24; ACC386 timing consumer preserves bit2 | P tables; A0B52-0B7E. Bits5 and1:0 have no separate electrical definition here. |
| `1B` | `0 / 01` | Conditional switch | ACC386 fast/slow speed selection; polarity depends on1C bit3 | A0C9A-0CBB,0D06-0D25. Not a universal turbo bit polarity. |
| `1C` | `3 / 08` | Branch input | Selects polarity used for1B bit0 | Same A consumers. Other bits remain unknown. |
| `1D` | Whole byte, varying mask `0C` | Size encoding |128/256/512 KiB useFC/F8/F0; varying bits3:2 are11/10/00 | P927A/92CA. This derives the varying bits, not permission to use the missing01 code. |
| `1E` | `5 / 20` | Activation state | Set after fill, cleared by normal reset continuation | P9771-977C,E0E6 onward; H5B->7B. Electrical meaning not established. |
| `1E` | `1 / 02` | Size-correlated bit | Qualified128 KiB uses79;256/512 use7B | P size table. Bit7 is preserved. This does not establish an independent cache-size control. |

### Byte layouts that can be drawn without guessing

```text
ACC 0B:  [7:4 auto?] [3:2 CAS] [1:0 auto?]
ACC 12:  [7:4 auto?] [3 probe] [2 ?] [1:0 map]
ACC 13:  [7:6 bank3 route] [5:4 bank2 route] [3:2 bank1 route] [1:0 bank0 route]
ACC 1A:  [7 ADS] [6 ?] [5 ?] [4:3 cache mode] [2 ?] [1:0 auto?]
VLSI01:  [7:6 cycle start] [5:4 precharge] [3:2 RAS/CAS delay] [1:0 CAS]
```

ACC CAS is bits3:2 while VLSI CAS is bits1:0. Treating `04` as an independent CAS-enable bit would be wrong: the encoded two-bit value is01. A read/modify/write for a known field uses `(old & ~mask) | encoded_value`; that formula does not make an unknown encoding safe.

### ACC386 AT-bus and refresh encodings

These tables decode named ACC386 options. They are not proposed PB430 tuning values.

| AT Bus Clock Source option | Written register06 byte |
| --- | --- |
|14.3 MHz|00|
|SCLK/1|14|
|SCLK/1.5|13|
|SCLK/2|17|
|SCLK/2.5|12|
|SCLK/3|11|
|SCLK/4|15|
|SCLK/5|10|
|16 MHz|18|

The option record is217B and the byte table is092A. AUTOSYNC uses08D4 (`17 12 11 15 10 10 10`) when05 bit5 is1, or08DB (`14 14 13 17 12 11 15`) when it is0. Both use the16/20/25/33/40/50/66MHz clock categories. The PB430'sB7 value cannot be decoded by treating it as one of these whole bytes. No Internal MUX Clock option was found among the ACC386 ROM's44 Setup records. The AMI guide lists that control but does not establish its chipset field.

For refresh, ACC3860952-0967 does `(05 & FC) | choice`. The four choice values00/01/02/03 correspond to15/30/60/120 microseconds in the AMI guide. The physical PB43005=`9C` has choice00 under that interpretation. Slowing refresh is a separate retention-risk experiment, not an established explanation for the twofold L2 read penalty.

## Related ACC data sheets and the next read-timing probe

The original manufacturer PDFs are retained above. ACC2046 was retrieved from [Datasheet4U](https://datasheet4u.com/pdf/1562097/ACC2046.pdf). ACC2087 was retrieved from [MacDat](https://macdat.net/files/pdf/accmicro/208711p.pdf). The ACC2046 scan has handwritten page numbers that match its PDF page positions. ACC2087 references below use printed page numbers.

| Register / field | ACC2046 definition | ACC2087 comparison / PB430 consequence |
| --- | --- | --- |
|01[7:6]|Page-interleave write waits. Non-pipeline00/01/10/11=1/1/2/2. Pipeline00/01/10/11=1/0/1/1. D46p25.|D87 reserves these bits. Do not transfer this definition blindly.|
|01[4]|Disable RAS timeout when1. D46p25.|D87 retains this field. Programmed93 already sets it.|
|01[1]|Page-interleave RAS precharge:0=3cycles,1=2. D46p25.|D87 reserves it. Programmed93 already has1.|
|01[0]|Page-interleave read wait:0=1wait,1=0wait. D46p25.|D87 reserves it. D46 mode selection depends on12[3]. Under that model PB43009 selects page mode, which can explain R having no effect. This is an inference, not proof.|
|04[6],04[5],04[4],04[3]|Uncached486 page-hit write0wait enable; cache read1wait enable; DRAM burst enable; L1 cache-fill burst enable. D46p26.|D87p75 agrees. Current15 already has cache read wait clear and DRAM burst set. The separate bit3 experiment booted with1D but worsened RAM reads to343ns. Keep bit3 clear.|
|04[2:1]|Cache line size00/10=32bits,01=64bits,11=128bits. D46p26.|D87p75 agrees. Reference size handling changes these bits as a group with other cache controls. Do not change them as independent timing switches.|
|05[5:4]|Double/single-phase clock status; page sequencer enable. D46p27.|D87 changes these meanings to L1 write policy and reserved. Direct evidence of nonportable fields.|
|07[4:0]|Internal MUX clock source/divisor, not a RAM wait count. D46pp27-28.|D87 omits07. D46 maps14 toCLKSRC/5 and18 to external16MHz. PB430's source wiring and phase requirements are unproved. KeepF4.|
|0B[7:6]|RAS precharge00/01/10/11=2/3/4/5T. D46p29.|D87p78 agrees. Current15 already selects minimum00 under this model.|
|0B[5]|Write RAS-to-CAS delay0=2cycles,1=3. D46p29.|D87p78 agrees. Current15 already has0.|
|0B[4]|CAS precharge0=1cycle,1=2. D46p29.|D87p78 specifically calls this write precharge. Earlier15/05 retained the same read CAS, consistent with no measured read gain.|
|0B[3:2]|Read CAS pulse. The retained D46p29 scan prints1T for both00 and01, then3T/4T.|D87p78 gives1/2/3/4T. M and ACC3860B84-0BA2 identify01 as2T. Use that corroborated decoding. Current15=2T; measured19=3T is slower. The11=1T experiment failed and is withdrawn.|
|0B[1:0]|Write CAS pulse00/01/10/11=1/2/3/4T. D46p29.|D87p78 agrees. Earlier05/04 changes this write field, consistent with no read gain.|
|12[7]|Page-read RAS-to-CAS delay0=2cycles,1=3. D46p33.|D87p82 agrees. Current09 already has0. ACC3860B21-0B3D and tablesA6E/A75 only add80 at higher clocks.|
|12[6],12[2]|Reserved. D46p33.|D87 assigns read CAS precharge and a DRAM geometry control respectively. Do not infer ACC2168 support from those newer definitions.|
|12[3]|Page-mode memory selection when1. D46pp23,33.|Current09 has1. Changing it also changes00/12 geometry interpretation. It is not an isolated performance switch.|
|18[5]|Disable one-cycle sampling delay when1. D46p33.|D87p85 gives a different DRAM/ISA wait description. PB430 uses20 in SRAM prerequisites, then00. Remains unresolved for steady CPU reads.|
|18[4]|Posted-write0wait enable when1. D46p33.|D87p85 says1wait when1 for cache write-back or posted write-through. This is a polarity conflict, not just added context. Current04[7]=0 disables posted writes under both definitions. T is not a demonstrated read-timing lever.|
|1A[7:5]|ADS delay enable; L1 disable;386 pipeline disable. D46p34.|D87 retains7/6 but reserves5. Keep PB430's stock24.|
|1A[4:3]|Cache always-hit and always-miss controls. D46pp34-35.|D87 combines these differently. Preserve PB430's exact transient cache sequence.|
|1A[2:0]|Cache-match polarity; DMA delay2/3cycles; fast DMA clock choice. D46pp34-35.|D87 reserves2. The DMA fields are not CPU streaming-read controls.|

The withdrawn C1 experiment used register0B15/11/15. It changed only the read CAS field from01 to00. The explicit D46/D87 definition supplied the hypothesis for this experiment. The raw ACC386 table still does not establish a working zero-CAS configuration. The first physical C1 run returned the generic memory/register failure. The diagnostic build then hard-locked before reporting a cause. C1 is now refused before hardware access and stays out of the BIOS.

## Live timing snapshot and probable ACC2168 model

The user supplied `build/diagnostics/ACCNOW.TXT` on2026-10-16. This baseline capture had Fast Memory Writes and Slow Refresh enabled. The following transcription preserves it outside the disposable build directory. No new Setup policy was applied for this capture.

```text
CR0=00000010  P78=1D  P92=FC
00=A9 01=BF 02=F9 03=10 04=15 05=9F 06=B7 07=F4
08=F0 09=0F 0A=04 0B=04 0C=0C 0D=80 0E=00 0F=00
10=00 11=00 12=09 13=00 14=06 16=00 18=00 19=08
1A=24 1B=10 1C=FE 1D=F0 1E=7B 25=02 26=00
```

This table compares every requested register. It concentrates on timing. It excludes bank-layout changes from the tuning plan. A reserved field is preserved, not treated as a writable zero. Confidence labels apply to the proposed2168 interpretation: **direct** means2168 documentation or an observed function, **probable** means related-manual agreement, and **unresolved** means conflicting or single-chip evidence. These labels are evidence categories, not numerical probabilities.

| Register / field | ACC2046 | ACC2087 | Probable2168 interpretation and live state |
| --- | --- | --- | --- |
|01[4]|0 enables RAS timeout,1 disables, p25|Same, p74|**Probable:** disabled inBF. The combined probe writes83, clearing only this bit relative to stock93.|
|01[7:6,1:0]|Page-interleave waits, p25|Reserved, p74|**Unresolved:** not ordinary page-mode timing controls. Preserve stock programmed bits. R bit0 trial was neutral.|
|02[6]|Shadow cacheable, p25|Same, p74|**Direct:** enabled inF9. M p11 and stock cache owner corroborate.|
|02[5]|Global shadow write protection, p25|Same, p74|**Direct:** enabled. Copy operations must finish before protection.|
|02[4:0]|F000/E000/D000/C800/C000 windows, p25|Same, p74|**Direct:** F000,E000,C000 on, D000,C800 off. M p3 corroborates. This is ROM acceleration, not extended-RAM timing.|
|02[7]|Reserved, p25|Must be1, p74|Live1. Preserve it.|
|04[7]|Posted writes, p26|Same, p75|**Direct:** off. M requires external245 buffers. Do not enable from timing arithmetic alone.|
|04[6]|486 non-cache page-hit writes:1=0wait,0=1wait, p26|Same, p75|**Probable:** currently0. Does not establish a speed gain with L2 enabled.|
|04[5]|Cache reads:0=0wait,1=1wait, p26|Same, p75|**Probable:** currently the faster0 setting. This is cache-hit timing.|
|04[4]|DRAM burst enable, p26|Same, p75|**Probable:** on. Clearing it physically locked this board. Keep1.|
|04[3]|Cache burst into486 L1, p26|Same, p75|**Probable:** off. Setting it worsened main-memory reads to343ns. Keep0.|
|04[2:0]|Cache line selection and enable, p26|Same, p75|Preserve the working cache configuration. These are outside this timing-only change.|
|0B[7:6]|RAS precharge2/3/4/5T, p29|Same, p78|**Probable:**00=2T, already the smallest encoding.|
|0B[5]|Write RAS-to-CAS2/3T, p29. Zero-state prose also mentions reads.|Write RAS-to-CAS2/3T, p78|**Probable:**0=2T. Use12[7] for read delay.|
|0B[4]|CAS precharge1/2T, p29|Explicitly write CAS precharge1/2T, p78|**Probable:**0=1T write precharge.15-to05 did not improve reads.|
|0B[3:2]|Printed table repeats1T at00/01, then3/4T, p29|1/2/3/4T, p78|**Direct for01/10:** M and ACC386 resolve01=2T,10=3T. Live01=2T.00 caused a failed test and lock.|
|0B[1:0]|Write CAS1/2/3/4T, p29|Same, p78|**Probable, measured gain:**00=1T. Combined04 improved writes.|
|12[7]|Read RAS-to-CAS2/3T, p33|Same, p82|**Probable:**0=2T, already the smallest encoding.|
|12[6]|Reserved, p33|1 selects2T read CAS precharge, p82|**Unresolved:** live0. D87 does not explicitly state the zero-state width here. Preserve0 until measured.|
|12[5:0]|Other controls, including memory layout|Several definitions differ|Preserve live09 low bits. They are outside this timing-only change.|
|14[6]|No definition found|Cache write-hit0wait enable, p83|**Unresolved:** live0. A possible write control, not a read accelerator.|
|14[4:3]|No definition found|8-/16-bit AT-bus0wait enables, p83|**Unresolved on2168:** both0. These do not name CPU DRAM-read waits.|
|14[7,5,2:0]|No definition found|Bus width controls and reserved bits, p83|Live06 includes reserved readback bits. Preserve them.|
|16[3:2]|No definition found|Write CAS starts half a clock earlier at11.0x=no extension, p85|**Unresolved:**00.10 is unspecified. Earlier CAS extends its pulse. It does not inherently shorten a transaction.|
|16[1:0]|No definition found|Read CAS starts half a clock earlier at11.0x=no extension, p85|**Unresolved:**00. This is the most relevant remaining edge-timing hypothesis. The combined probe requires03 readback before selecting the shorter CAS pulse.|
|16[7:4]|No definition found|Bit7 must be1, bit6 ROM0wait, bits5:4 AT refresh count, p84|Live00 contradicts the D87 bit7 rule. Do not force bit7 high or infer the whole register exists from a zero read.|
|18[7]|Reserved, p33|X-2-2-2 L2 read burst enable, p85|**Unresolved:**0. D87 names cache burst pacing, not a DRAM RAS/CAS profile.|
|18[6]|Reserved, p33|Adds an ISA wait, p85|**Unresolved:**0. No proposed main-memory change.|
|18[5]|1 disables one sampling-delay clock, p33|1 adds a DRAM/ISA off-cycle wait, p85|**Unresolved, conflicting descriptions:**0. S trial was neutral, including with Fast Writes.|
|18[4]|1 selects posted-write0wait, p33|1 selects cache/post-write1wait, p85|**Unresolved, opposite wait descriptions:**0. T trial was neutral.|
|18[3:2]|Reserved, p33|Reserved, p85|Live00. Preserve.|
|18[1]|Burst refresh enable, p33|Hidden burst refresh enable, p85|**Probable burst-refresh control:**0. Hidden operation on2168 remains unproved. H trial was neutral.|
|18[0]|1 disables AT refresh, p33|Same, p85|**Probable:**0 retains standard refresh. Keep it.|
|19[7:6]|Refresh RAS active4/3/2/1T, p34|Table5/4/3/2T, but default prose says4T, p86|**Unresolved:**00 means4T or5T. Do not average the conflicting encodings.|
|19[5:4]|Refresh RAS precharge4/3/2/1T, p34|Same, p86|**Probable:**00=4T. A candidate for shorter refresh occupancy, not shorter foreground read cycles.|
|19[3]|Reserved, p34|Reserved with default0, p86|Live1. Preserve it. This differs from the D87 default, but does not alone prove different writable behavior.|
|19[2:0]|Refresh burst count1..8, p34|Same, p86|**Probable:**000=1. Changing count also changes refresh coverage and occupancy.|

The distilled working profile is therefore **RAS precharge2T, read RAS-to-CAS2T, read CAS2T, write CAS1T**, with write RAS-to-CAS2T and write CAS precharge1T. Its live bytes are0B=04 and12=09. This remains the current persistent baseline. The combined profile below now has a measured read-throughput gain. The combined experiment tests16[1:0] with a shorter read pulse,19[5:4], and enabled RAS timeout. The first concerns a read edge. The second concerns refresh occupancy.

The matching fields and live values support a combined experimental profile. Register16 bit7 and19 bit3 show why the profile preserves unrelated bits instead of copying whole2087 defaults. The D46/D87 disagreements at12 and18 stay out of this trial. Register19 changes08 to28, preserving bit3.

### Cycle budget at33MHz with60ns DRAM

Use the existing [Presario timing notation and method](../../presario-800/docs/fpm-dram-presets-25-33mhz.md): `RAS-precharge - RAS-to-CAS - CAS-read / CAS-write`. Transfer the time-budget method, not VLSI register encodings or its L2 display adjustment. The Presario33MHz/60ns target is2-1-2/1. The common ACC map cannot encode its1T RAS-to-CAS field. The closest established ACC profile is the live2-2-2/1.

At exactly33MHz, `T = 1000/33 = 30.303ns`. Half a clock is15.152ns. At33.333MHz, use30ns and15ns instead. The134MHz CPU-core estimate is not the memory-controller clock.

| Clock interval | Time at33MHz |
| --- | --- |
|0.5T|15.152ns|
|1T|30.303ns|
|1.5T|45.455ns|
|2T|60.606ns|
|3T|90.909ns|
|4T|121.212ns|
|5T|151.515ns|

A60ns label specifies row-access time, not every DRAM interval. For a concrete example, the [Micron MT4C4M4 family data sheet](https://docs.rs-online.com/5e47/0900766b80028aed.pdf), pages1,7-8, lists60ns row access,15ns CAS access,30ns column-address access,40ns RAS precharge and35ns page-cycle time for its-6 grade. This is a representative calculation, not identification of the installed chips.

Apply the minimum-time rule `cycles = ceil((required_ns + margin_ns) / T)`. Output delays, input setup time, board delay and edge skew consume the margin. Check row, column and CAS access constraints together:

```text
sample_time >= max(RAS_fall + tRAC, CAS_fall + tCAC,
                   column_address_valid + tAA) + receiver/board margin
RAS_high >= tRP
successive_page_cycles >= tPC
```

For that representative part,40ns RAS precharge needs2T before extra margin. Its35ns page-cycle minimum also needs at least2T in whole clocks. Neither calculation permits a30.303ns full page cycle. A15ns CAS-access specification alone therefore does not qualify1T CPU reads. The board's failed1T CAS trial remains stronger evidence than an incomplete chip-only budget.

The2087 AC tables on printed pages129-130 illustrate another missing part of the budget: CAS assertion can follow the clock edge by up to10ns, and memory-address outputs by up to18/19ns. These are2087 values, not measured2168 delays. They show why subtracting only15ns from one30.303ns clock is insufficient. A16[1:0]=11 experiment, if the2168 implements it, advances the CAS edge by about15.152ns. It can improve access margin without reducing the CPU-visible transfer count. It also consumes address-setup and RAS-to-CAS margin. The user selected a coherent combined experiment: advance CAS first, then reduce the programmed read width to1T. Under the2087 model, the resulting pulse is1.5T, about45.455ns. It differs from the failed unextended1T pulse. The resulting read RAS-to-CAS interval is also about1.5T if both fields share the documented edge schedule. Address setup and the actual2168 implementation remain physical-test questions.

If the original read CAS high interval is1T, advancing the next assertion by0.5T leaves a nominal15.152ns precharge interval. The representative Micron part requires10ns CAS precharge, leaving about5.152ns before edge skew and board effects. This is the tight part of the combined profile. It is an aggressive physical experiment with a coherent timing budget, not a guaranteed configuration.

For refresh, the common19[5:4] model offers4T to2T precharge:121.212ns to60.606ns. A40ns part admits2T before board margin, but not1T. Starting from live08, that isolated hypothesis gives `(08 & CF) | 20 = 28`, preserving bit3 and the burst count. Active-width00 remains unchanged because its two definitions disagree. The combined ACCPROF experiment implements this value and increased throughput to15.7MiB/s. Its separate contribution and long-term stability remain unmeasured. If exactly one such precharge occurs per120us refresh request, saving60.606ns removes only0.0505 percentage points of bus occupancy. At15us it removes0.404 percentage points. Actual refresh scheduling can change those estimates. This cannot plausibly explain the whole twofold streaming-read penalty by itself.

RAS timeout is also a separate hypothesis.01 bit4 is currently1. Enabling timeout requires programmed93->83, with expected readbackBF->AF under the observed reserved-bit readback. Closing an idle row can affect subsequent hits or misses. It is not a mathematically guaranteed speed increase. The earlierR probe changed bit0, so it did not test RAS timeout.

Finally, CACHECHK's271ns effective read time is about8.94 clocks at33MHz. A100ns effective target is3.30 clocks per reported four-byte transfer. These are throughput equivalents, not DRAM-chip access measurements. Keep them separate from CAS pulse width and from the16-byte burst notation3-2-2-2. The current evidence supports an extra controller/cache-miss cost, but does not yet identify a register that removes it.

## Four populated banks and interleave

The user confirms that all four memory banks are populated. ACC2046 supports two-way and four-way page interleave, but it also requires a compatible clock mode and memory wiring. Four banks alone do not satisfy those prerequisites.

D46 pages10-12 describe the difference. Double-phase operation assigns CAS signals by bank and combines them with byte enables through external logic. Single-phase operation shares byte CAS signals across the banks and supports ordinary page mode only. Pages23 and27 agree:05 bit5 reports the clock mode, and the page-sequencer control05 bit4 is read-only in single-phase mode. The current05=9C has bit5 clear andbit4 set. Under this related-chip model, it describes single-phase operation with the page sequencer enabled. ACC2168's exact wiring and clock-status equivalence are not independently proved.

The ROM paths corroborate the restriction. ACC3860F47-0F64 sends05 bit5 clear directly to page-mode setup0F67. Its optional interleave path0FE5 is reached only in the other clock mode. PB4309938-994A tests ROM byte8CF7=03, then05 bit4. Current9C selects mode1 at997F. Stock also contains mode0 at994E-997A, but its presence does not qualify that mode for this hardware state. The port retains the established mode1 mapper.

A mode change also changes the geometry decoder. D46 page23 assigns12 bit3=1 to page geometry and0 to interleave geometry. Current00=A9 and12=09 is a page configuration. Clearing12 bit3 alone leaves low nibble9 in00, which is reserved in the interleave table. For four equal4MiB banks, D46 assigns interleave code5. ACC386 tableE68 (`01 05 55 02 0A AA 03 0F FF`) independently places the matching four-bank patternAA at index5. This is supporting evidence for the alternative map, not a PB430 write recipe. Register13=00 describes unchanged bank routing, not enabled interleave.

The user authorizes an early-boot interleave experiment despite this unresolved clock/wiring constraint. The separate candidate uses the established bank probe and reference mode0 map, with readback and destructive checks before live firmware state. See [the trial procedure](hardware-evidence.md#early-interleave-experiment). This does not qualify a general software-only Setup toggle. Do not switch modes from DOS: existing data would be decoded with a different map. The supplied ACC2168 AMI guide names four banks but provides no interleave option or clock-phase exception.

## What the Presario's VLSI fields actually contain

The chip is VL82C481. Use its data sheet and current [chipset policy](../../presario-800/src/chipsets/vl82c481/policy.inc) and [field definitions](../../presario-800/src/chipsets/vl82c481/setup-data.inc). The older Presario FPM preset proposal cites VL82C486 and is superseded by the current [README](../../presario-800/README.md). Its display-only cache-offset interpretation is not authority.

VLSI uses index/data portsEC/ED. ACC usesF2/F3. On PB430, ED is used for an I/O delay, not to select VLSI data.

| VLSI register | Bits / mask | Field | Documented encoding |
| --- | --- | --- | --- |
|01 RAMTMG|7:6 / C0|Earliest cycle start|00 beginning firstT2;01 middle firstT2;1x end firstT2|
|01 RAMTMG|5:4 /30|RAS precharge|00/01/10/11 =1/2/3/4T|
|01 RAMTMG|3:2 /0C|RAS-to-CAS delay|00/01/10/11 =1/2/3/4T|
|01 RAMTMG|1:0 /03|CAS read/write width|Context-dependent table below|
|04 RAMSET|7:5 /E0|Interleave selection|000 none;001 banks0/1;010 banks0/3;011 banks1/2;100 banks2/3;101 pairs0/1 and2/3;110 pairs0/3 and1/2;111 unused|
|04 RAMSET|4 /10|RAS timeout disable|0 timeout enabled;1 disabled|
|04 RAMSET|3 /08|P24T mode status|Read-only:0 disabled;1 enabled|
|04 RAMSET|2:1 /06|DRAM drive strength|00 all12mA;01 MA/RAMW24mA,others12mA;10 all24mA exceptRAS12mA;11 all24mA|
|04 RAMSET|0 /01|Page mode|0 enabled;1 burst-only|
|05 NTBREF|7:5 /E0|Non-turbo added waits|000 full speed;001 adds2;through111 adds8|
|05 NTBREF|4 /10|TURBO pin|Read-only status|
|05 NTBREF|3:2 /0C|Refresh mode|00 synchronous;01 asynchronous;1x decoupled|
|05 NTBREF|1 /02|CAS-before-RAS refresh|0 disabled;1 enabled|
|05 NTBREF|0 /01|Refresh period|0=15.625 microseconds;1=125 microseconds|
|07 MISCSET|7 /80|Segment cacheability policy|Enable for secondary cache|
|07 MISCSET|6 /40|TAG pin|Status input|
|07 MISCSET|5 /20|Cache write-enable turn-off|0 late;1 early|
|07 MISCSET|4 /10|Fast internal RC#|Enable|
|07 MISCSET|3 /08|Primary cache|Enable|
|07 MISCSET|2 /04|Parity generation/check disable|Active-low ENPAR# naming|
|07 MISCSET|1 /02|Conditional wait state|Disable control|
|07 MISCSET|0 /01|Cache control clock adjustment|Disable control|
|19 CACHCTL|7 /80|SRAM banks|One/two-bank selection|
|19 CACHCTL|6 /40|Cache write wait|0=1 wait;1=0 waits|
|19 CACHCTL|5 /20|Tag width|0=8 bits;1=9 bits|
|19 CACHCTL|4 /10|Valid-bit enable|Independent enable|
|19 CACHCTL|3 /08|Dirty-bit disable|Independent disable|
|19 CACHCTL|2:0 /07|Cache size/mode|000 disabled;00132KiB;01064KiB;011128KiB;100256KiB;101512KiB;1101MiB;111 direct access|
|24 XCTL|6 /40|High-speed mode|Also changes CAS interpretation|
|24 XCTL|3 /08|Extra cache read wait|Enable adds a wait|

RAS selects a DRAM row. CAS selects a column within that row. Precharge is the time to prepare for another row access. These are different phases of a memory transfer, so changing CAS alone need not remove the full miss penalty.

VLSI RAMTMG CAS codes, from manual page18:

| Raw bits1:0 | Cache disabled and HSPD=0, read/write | Cache enabled OR HSPD=1, read/write |
| --- | --- | --- |
|00|1T /1T|2T /1T|
|01|1.5T /1T|2T /1T|
|10|2T /1T|3T /1T|
|11|2T /2T|3T /2T|

This is a real mode-dependent timing definition, not just a display adjustment. It also shows why two raw codes can produce the same timing. ACC has not been shown to use this same rule.

## Structural comparison and limits

| Property | ACC evidence | VLSI evidence | Conclusion |
| --- | --- | --- | --- |
|Several controls per byte|0B CAS plus automatic groups;12 map plus other controls|RAMTMG four two-bit fields;RAMSET mixed fields/status|Same broad packing pattern|
|Independent bit switches|04[0] L2;1A[7] ADS|RAMSET[0] page mode;XCTL[3] cache wait|Some bits are switches, not every bit|
|Encoded fields|0B[3:2] CAS;13 four route lanes|RAMTMG four timing fields|Decode groups, not isolated set bits|
|Context-dependent behavior|Cache entry order and ACC386 posted-write prerequisite change final bytes|CAS interpretation depends on cache/HSPD|Context matters in both; identical equations are unproved|
|Timing versus geometry|00/12/13 mapping and1D size are separate from known CAS|RAMCFG/RAMSET/CACHCTL also carry geometry|Do not sweep all bits as timing knobs|
|Readback versus programmed value|01 readsBF after reference-style93 writes|Some VLSI bits are documented read-only|ACC readback mismatch does not by itself identify reserved/status bits|
|RAS/precharge/cycle-start fields|D46/D87 decode0B and12 for related ACC chips|Explicit masksC0/30/0C in VLSI01|Use related ACC definitions as hypotheses, not VLSI field positions|

## Physical results and next deductions

| Trial | Reported rate | What it establishes |
| --- | --- | --- |
|0B15,05,15|13.6 MiB/s on all rows|Clearing bit4 did not change this read workload|
|0B15,04,15|13.6 MiB/s on all rows|Clearing bits4 and0 did not change this read workload|
|W5:0B15,05,15|18.7 MiB/s on all write rows|Clearing bit4 did not improve this write workload|
|W4:0B15,04,15|Trial21.6 MiB/s versus18.7 stock|About15.5% faster writes. Originally offered as Fast Memory Writes; now use the individual write timing fields|
|Fast Memory Writes enabled in Setup|180ns write /271ns read|Write time fell from218ns. Refresh choice was not reported, so the read change is not isolated|
|Earlier read pulse with read CAS1T; Earlier write pulse permits uncached0WS writes|User reports17.3 MB/sec and242/121ns read/write|Original throughput was13.6 MB/sec, a27.2% gain. Tested pairing on this board, not a universal2168 constraint or complete settings capture. Setup help describes both dependencies; individual choices remain available.|
|0B11 (C1)|Failed check, then hard lock with diagnostic build|Withdrawn; cause and failing phase remain unknown|
|0B19|12.2 MiB/s|Changing CAS field04 to08 slows the measured read path|
|01:93,92,93 (R)|13.6 MiB/s on all rows|Clearing01 bit0 did not improve this read workload|
|128 versus512 KiB L2|No RAM-throughput difference reported|The observed penalty is not specific to512 KiB on this board|
|05:9C/9F/9C (F8)|Trial14.0 MiB/s|About2.9% above the earlier13.6 baseline; now offered as Slow Refresh|
|18:00/10/00 (T)|No change reported|Keep the stock00 value|
|18:00/02/00 (H)|No change reported|Hidden refresh did not improve this workload|
|04:15 to1D, separate burst ROM|RAM up to343ns read /218ns write|Read time increased from280ns. No reported write gain. Keep15|

The earlier CAS report supplied the19 row; the surrounding stock rows were not repeated in that message. Using the previously reported13.6 baseline, throughput falls about10.3%. Average transfer time per four bytes rises from about280.5ns to312.7ns, a difference of32.2ns. This is consistent with roughly one additional bus clock near33MHz. It is not an isolated DRAM-chip latency measurement or a precise bus-clock measurement.

The current CAS field is therefore a real timing control. The unchanged05/04 trials are not evidence that the whole register is ignored. They leave other workloads, write timing, and context-dependent effects unresolved.

The related-chip manuals motivated the now-withdrawn0B CAS-read code00 experiment. They also identify plausible write-only controls and mode-dependent fields, which explains several negative read results. They do not establish that ACC2168 implements every field identically. Keep clock selection, memory geometry, and the full cache activation sequence unchanged.

No zero-CAS candidate follows from ACC386 tableA67. Its clock columns are16/20/25/33/40/50/66MHz. More importantly, the normal prior cache path sets04 bit7, and the timing consumer ORs05 into the raw table byte. Raw00 becomes05. Compare the complete sequence, not just the table. See [the traced prerequisite chain](hardware-evidence.md#cas-response-comparison).

The completed bounded utility experiment is [register01:93/92/93](hardware-evidence.md#register01-reference-comparison). ACC386 uses92 in its cache-enabled33MHz path, but also enables posted writes earlier. PB430 uses92 during SRAM sizing and93 afterward. The probe therefore tests an unverified combination with PB430's steady cache state; it does not transfer the ACC386 cache policy. Its electrical meaning remains unknown; the user measured no read-throughput change (13.6 MiB/s on all three rows). Keep bit0 set. The new RAS Timeout control changes bit4 separately, using83 or93. The probe accepts the reference128/512KiB register pairs without changing them. The user reports that256KiB is not a documented board size; its ROM table entry does not establish physical board support, and the probe refuses it.

The user measured higher overall performance with either tested L2 size than with L2 disabled. Keep L2 enabled; slow streaming reads do not establish that disabling it improves real workloads. No numerical overall-performance scores were supplied. The128/512 KiB comparison removes the proposed512 KiB-specific penalty as the current explanation on this board.

The Setup timing extension exposes these fields for physical experiments. Normal retains stock access timings; Fast uses the measured ACCPROF combination. Neither profile changes bank layout or cache geometry. The related-chip interpretations remain hypotheses where this table identifies uncertainty.

The user measured14.0 MiB/s with the register05 F8 divider and no change with register18:00/10/00. Refresh Period now offers the F8 interval as `120 us (Slow)`. Register18 stays at stock until a manual choice changes it. See [commands, source addresses and retention limits](hardware-evidence.md#slower-refresh-and-register18-trials). D46 names register18 bit4 as a posted-write wait control. This explains why it is a poor read-throughput target, but ACC2168 equivalence remains unproved. No ACC field is inferred from VLSI positions.

## Setup timing extension

The existing 24-byte CMOS record retains signature C2 and its checksum. Byte23=A3 identifies the extended record. An old record must still have Boolean bytes0..8 and zero bytes9..23; loading it preserves the first nine choices, supplies the new defaults, and selects Manual. Loading does not write CMOS. New records reject unused bits and invalid enum values.

| Record byte | Owner |
| --- | --- |
| 0..6 | Existing ADS policy, L1, L2, system/video shadows, ADS and Fast Boot |
| 7 | Refresh choice: 0=15us, 1=120us, 2=30us, 3=60us; old Slow Refresh codes retain their meaning |
| 8 | Legacy Fast Writes compatibility byte; no Setup control. Retained for old-record migration. |
| 9 | Inverted RAS timeout: 0 enables it with programmed01=83; 1 disables it with93 |
| 10..12 | C800, D000 and optional E000 shadow enables |
| 13 | Inverted shadow cacheability; 0 retains enabled |
| 14 | Profile: 0 Normal, 1 Fast, 2 Manual |
| 15 | Raw0B timing byte |
| 16 | Register12 maskC0 |
| 17 | Register14 mask58 |
| 18 | Packed16 controls: bits0/1 read/write advance, bit4 ROM zero wait; retired bits3:2 normalize to zero |
| 19 | Register18 maskF3 |
| 20 | Register19 maskF7; hardware bit3 is preserved |
| 21 | Register04 maskF8; low3 cache-enable/geometry bits stay owned by stock |
| 22 | Bit0 inverted shadow write protection; bit1 Cache Burst Writes; bit2 Cache Write X222; bit3 CAS Before RAS Refresh; bits6:4 ISA divider selector (0 jumper default, 1 /10, 2 /8, 3 /6, 4 /5, 5 /4, 6 /3, 7 /2; final divisors); bit7 reserved |
| 23 | Extension markerA3 |

Normal sets0B=15, clears12 timing bits and16 advance/AT-burst fields, restores19 timing fields to zero, enables RAS timeout, and selects15us refresh. Fast selects0B=00, read advance16[1:0]=11,19 precharge bits=20, RAS timeout, and120us refresh. Both leave independent cache, bus and ROM choices intact. Manual retains the selected values. Refresh Period edits also select Manual. The Fast Memory Writes shortcut is removed; the individual write width and precharge fields remain. These presets target the tested33MHz configuration; they do not claim that nominal60ns speed alone proves all DRAM constraints.

The timing owner runs before the early RAM test with both caches disabled, then again after the complete unchanged stock cache parent at its original late POST position. It requires jumper78 low bits5, L1 selected in Setup, qualified cache hardware, and stock04/0B live-table inputs. L2 may be disabled for comparison. It preserves unowned bits, establishes16 CAS advance before shorter0B CAS, and checks every advanced write. Shadow mappings are staged and copied before either call. Before the late cache parent, the existing timing restore owner reinstates all stock prerequisites. Optional37 write-burst changes require effective L2 enabled and therefore apply only after the late parent.

CMOS37=A7 is a transient marker, separate from all settings checksums and the existing CMOS36 recovery flag. It is written and verified before advanced changes. Normal reset restores0B=15 before removing16 advance, then restores the other owned fields and verifies them before clearing the marker. Normal startup always clears18[0] before reading RAM, and the timing restore owner also sets04[4], even without a marker. These restore AT refresh and DRAM read burst for startup; the saved DRAM Read Burst choice applies again before testing. Other fields are not restored without the marker. The stackless path retains BP, EDX and ESP. Direct B7 accesses keep NMI masked; shutdown05/0A service resumes bypass restoration. New timing and shadow POST codes are listed in [POST tracing](post-codes.md).

AT Refresh and Posted Writes are no longer editable. After validating an old saved record, all profiles normalize18[0]=0 and04[7]=0 in the in-memory record. DRAM Read Burst (04[4], record21 bit4) is editable again at the user's request, defaults enabled, and survives Normal/Fast/Manual profile application. The late policy enforces the same values. Loading does not write CMOS. AT Refresh Burst is also removed: packed record18 bits3:2 normalize to zero and hardware16[5:4] is zero. Refresh Period has one menu entry.

The requested fields are accounted for as follows. Related-chip meanings remain hypotheses for ACC2168 unless supported by physical evidence.

| Hardware field | Setup owner or fixed policy |
| --- | --- |
|04[3]|Cache and Memory: Cache Burst Reads (formerly Cache to CPU Burst)|
|04[4]|Cache and Memory: DRAM Read Burst; enabled by default, disabled available for comparison. Reset restores enabled before stock initialization.|
|18[7]|Cache and Memory: Cache Read X-2-2-2; editing and application require04[3]=1|
|18[1]|Refresh: Hidden Burst Refresh (formerly Burst Refresh)|
|19[7:6]|Refresh Active Time; editing requires Hidden Burst Refresh|
|19[5:4]|Refresh Precharge; editing requires Hidden Burst Refresh|
|19[2:0]|Refresh Burst Count; editing requires Hidden Burst Refresh|
|19[3]|Reserved, preserved|
|16[5:4]|Former AT Refresh Burst; forced to stock00|
|37[1]|Cache and Memory: Cache Burst Writes; enabling the experiment clears this bit|
|37[0]|Cache Write X-2-2-2; editing and application require the write parent|

All three19 fields retain their saved values while locked. The ACC2087 table calls them burst-refresh fields, which supports the requested menu dependency; this does not prove they have no effect in other ACC2168 refresh modes. Read/write X222 child choices also remain saved when their parent is off; the late policy suppresses the read child bit when04[3] is off. The existing write path already suppresses its override without its parent. The cache menu places each child next to its parent.

ACC2087 printed page97 describes register37 write bursts, distinct from18[7] read-cache burst timing. It defines37[1]=0 as cache burst write enabled, but the37[0] text inconsistently requires37[1]=1 for x-2-2-2. The experimental Setup controls follow the user's requested interpretation: enabling Cache Burst Writes clears37[1], and Cache Write X222 selects37[0] only under that parent. The child is locked otherwise; its saved choice is retained. Both default off, leaving chipset37 untouched. L2 must also be selected and the existing qualified33MHz timing gate must pass. The manual restricts cache burst writes to write-back implementations; these controls do not change CPU cache mode. ACC2168 support remains a physical experiment.

ACC2087 register03[6]=1 enables CAS-before-RAS AT refresh. The supplied03=10 dump has it off. The new Refresh option sets only that bit; default off retains the reference value. Normal/Fast preserve these independent choices. Before optional changes, CMOS37=B0..BF stores original37[1:0] in bits1:0, a37-change flag in bit2, and original03[6] in bit3. Reset restores only those saved hardware fields, converts the cookie toA7, then follows the existing timing restoration. Service05/0A resumes leave it alone. CMOS37 is an unrelated RTC storage byte, not chipset37. The old A7 path remains compatible. No settings-record size or checksum range changes.

CMOS36=AB marks an unfinished timing trial. It is armed before the early selected-timing RAM test, outside the stock cache transient window, and cleared after the RAM test, summary and clock synchronization return. Normal startup clears AB after restoring timings and preserves the saved record. An unfinished test alone does not prove a memory error. Only the shared comparison-failure path commits69=D2 and notice36=5A. The existing recovery notice acknowledges5A as1A; that retry guard is preserved until a complete verified Setup save. An intentional Ctrl+Alt+Del restores timings and clears only AB, so it retries the saved selection. Service05/0A resumes leave both markers alone.

The visible RAM test is back at the Presario location before peripheral initialization and floppy seek, on both cold and warm POST. Selected DRAM timings apply first. Both caches are disabled; the test rejects an unexpectedly enabled L2 rather than testing through it. The prior four conflict-read passes and their three-MiB minimum are removed. Constant patterns and address witnesses still verify DRAM and restore each tested block. Errors restore stock timings before the existing retry. DEL, Esc, Pause and Ctrl+Alt+Del retain the shared behavior. The late cache parent runs only after testing and the normal final Setup gate. This DRAM test no longer validates L2 behavior.

ISA Clock Divider uses register06[4:0], preserving bits7:5. The [stock-feature audit](stock-feature-audit.md#isa-clock-divider) records independent selector evidence, conditional frequencies, application order and CMOS-clear recovery. It applies after the late stock cache sequence; Normal/Fast leave the choice intact.
