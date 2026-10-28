# PB430 hardware evidence

Addresses below are offsets in the original F000 64 KiB system region, unless a physical file offset is stated. Observed writes are preserved without assigning names to unknown bits. Emulator register meanings are verification contracts, not physical mapping authority.

The [durable instruction maps](../reference/maps/README.md) preserve every byte of both supplied ROMs as reassemblable source. The [stock behavior map](../reference/maps/stock-behavior.md) covers cold prerequisites, both reset owners, complete cache callers, and the ACC386 differences. Static reachability and unresolved transfers are identified separately.

The [register and bit-field map](register-map.md) combines the31 captured registers, decoded masks and consumers, remaining unknowns, physical timing results, and the Presario VL82C481 comparison. ACC386-only meanings and VLSI-only definitions remain separate from established PB430 behavior.

## Inputs

| Input | Size | SHA-256 |
| --- | --- | --- |
| `reference/pb430-m27c1001.bin` | 131072 | `c0874e34b6439de784036c35dbb95d8b8a33ed855d1c402ea7763a1be6fc574a` |
| `reference/acc386.BIN` | 65536 | `0a6be5271310c4b72ff54fc47a6fc524b81bfdf3bc3aab97bb3063192b08fdd1` |

The first input supplies the PB430 Phoenix system BIOS and Cirrus GD5422/24/26/28 video BIOS 1.30. The ACC2168 manual is the searchable AMI guide in root `reference/chipsets/acc/AC216811.txt`. The ACC3221 data sheet is root `reference/controllers/acc/acc3221.pdf`, especially configuration pages 18-20. The second ROM identifies ACC2046 and is comparison evidence only.

## Configuration and startup

Both ACC owners use F2/F3. PB430 writes at 99A6, 9C09 and 9C6A insert OUT ED after the index and data. `acc_write` and the frame-free startup writes preserve these delays. The normal cold table selects mode 1 with register 05=18. Register 06 at E081 uses port 78 bits 2:0: case 4 writes 33, case 5 writes B7, all other cases write 13. It is not a CPU-speed estimate.

Ordinary cold reset first writes06=13 at E067-E06F, clears CMOS0F at E079, writes78=00 at E07B, then selects06 at E081-E0A7. F163-F19E writes the19-row table at F6AB and then00=20,12=4D,05=96. This precedes the21-row table at8CD1 and DRAM detection. The port retains both tables and their ordering. Shutdown service continuations still return before this destructive normal-cold work.

Stock E115-E131 establishes refresh and DMA cascade before DRAM work: 8F=00, 43=54, 41=12, clears0D/DA, then D6=C0 and D4=00. The port now retains these prerequisites before its mapper or warm state reads. Its later AT prerequisite helper retains cascade setup after clearing DMA. Earlier candidates initialized refresh only after memory work, SRAM probing, and shadow copying.

Stock3A3F reaches warm consumer9631 before8E5E. The port now retains963D-9687 before copying warm state: CPU cache off/INVD,1A clear, original fill, CMOS69/STI,04 off,1E bit5 clear,1A transient08. This consumer is separate from968E before the reset pulse. The caller uses a DI continuation and the retained0000:7C00 stack, then restores the saved CPU signature and masks interrupts while rebuilding vectors.

The startup include ends in `jmp .post_settings`. That local label belongs to `startup` and is supplied immediately after the include by shared `firmware/bios.asm`. No intervening global label may change its scope. The port constructs the BDA, 8 KiB EBDA at 9E00, vectors and the proven stack at 7000 before continuing. The frame-free low-memory pattern check includes the actual stack region before the first push.

Shutdown 05/0A consumes CMOS 0F and returns through BDA 0467 before cold initialization. PB430 398F-3998 acknowledges both PICs for 05; 0A sends no EOI. Normal warm classification requires both the 8042 system flag and marker 1234 at 0472. A stale marker with the system flag clear remains cold. Warm startup retains the map, physical count and onboard-provider flag across EBDA reconstruction. After keyboard initialization enables the 8042 A20 output and keyboard runtime arms successfully, the existing board handoff clears port 92 bits 1 and 0 while preserving its upper bits. The two A20 sources are ORed; releasing the temporary sizing gate lets legacy software disable A20 through the 8042. Shared RAM tests and INT15 block moves temporarily enable fast A20 and restore its prior state.

## DRAM

The OEM probe at 98BC-9D60 writes mode-1 bank views and derives raw codes 0-4. Code 4 is not a capacity: 8/16 MiB and other independently measured layouts can reach it. The port retains the six strict comparison pairs 0/1, 0/2, 0/3, 1/2, 1/3, 2/3. This network is not globally stable for equal codes. Register 13 stores `(sorted_position-original_bank)&3` in each original bank's two-bit lane. An unchanged permutation writes 00.

The 36 pattern words at 8D29 and map bytes at 8D83 are retained directly from the original ROM. Register 00 low nibble and register 12 low two bits take the selected map. Unmatched mode 1 in the original reaches the last entry because 9BA6 overwrites its search flags. The port accepts known matches and emits EA for an unsupported pattern. It does not copy this accidental fallback.

Mode1 entry at9909-99C6 writes13=00,12=(old&F7), enables A20 at92, reads05 for dispatch, then writes00=(old&F0)|09,12=(old&F0)|0A,05=old|10. The cold table already selects mode1. These intermediate writes precede the existing stackless probe.

The separate alias-aware count at 5730/57F1 tests each 64 KiB candidate against the low-stack witness before clearing it. The port retains that intent using its own flat descriptor and explicit DS addressing. It does not call stock bytes whose mutable GDT selectors and saved stack layout belong to the OEM. The conventional 640 KiB span is proved separately; the 8 KiB reservation publishes 632 KiB through INT12. Extended counts come from measurement and feed CMOS and INT15. There is no invented 4 MiB minimum. Current bank views/count are bounded at 64 MiB.

## SRAM and final timing

Presence at 8F33 is separate from size. Register 04=33 and masked 1A probe state precede the 55AA/0F0F witness. A successful presence branch writes 01=92. The 512/256/128 KiB candidates compare distinct aliases; their codes are 2/3/1. The final 32/64 KiB witness is ambiguous: OEM code 0 cannot qualify a size. The port retains its actual accesses and last-witness result, reports unknown, and leaves L2 disabled. All touched DRAM dwords are saved and restored.

The complete OEM continuation at 9142 writes 01=93. Let `s=clamp((port78&7)-3,0,3)`. Each row below contains four values selected by s. Whole writes use preserve mask 00; masked writes use `(old & mask) | value`.

| Register | Mask | Safe values | Qualified SRAM and CPU-cache values |
| --- | --- | --- | --- |
| 04 | 00 | 94,54,54,14 | 14,14,14,34 |
| 06 | 00 | 13,33,B7,12 | 23,33,B7,12 |
| 07 | E0 | 18,18,14,18 | 18,18,14,18 |
| 0B | 00 | 04,05,05,15 | 04,15,15,15 |
| 18 | 8C | 20,20,00,00 | 20,00,00,00 |
| 1A | 40 | 24,24,24,24 | 24,24,24,24 |

OEM 91BD-91E4 adds size rows under the same presence/CPU gate. Qualified codes 1/2/3 write 1D=FC/F0/F8 and 1E=(old&80)|79/7B/7B. Unknown-code calibration remains deferred. The cache-dependent ranges at 9D63-9E41 write registers 0C-11: absent/unknown all zero; 128 KiB `0B,40,0C,80,00,00`; 256/512 KiB `0C,80,00,00,00,00`. These are not RAM-timing controls.

Late owner 9706 repeats range setup. The CMOS 34 bit-6 gate at 9719 encloses both CPU and L2 activation. The port uses the existing saved processor-cache selection for that gate and additionally requires a saved L2 request and qualified size. It preserves unknown 1A bit 6; CPU cache uses CR0 CD/NW. Late activation masks 1A to `(old&E7)|08`, sets 04 bit 0, flushes, sets 1E bit 5 and clears transient 1A bits 4:3. The exact 9795 flush reads 3FFF dwords in each segment 0000-7000 with address-16 REP LODSD. The last read is 7FFF8, reaching the last cache line without crossing a segment limit.

The caller at4C45-4C53 selects SS:SP=0030:0100 with interrupts masked. CALL97C7, its saved AX, CALL9706 and the six-word frame leave SP=00EE before inline activation. The9795 frame reaches physical003D8. The port uses this stack and parent frame and keeps activation inline. It saves the established modular stack in private BIOS state, restores it after activation, and retains the caller's enabled-interrupt state when cache remains off. The compared cache hardware operations run with the stock interrupt order.

Stock972D loads DS from CS:D56F, whose word is0000. The port selects DS=0000 before the CMOS3D read and activation. The existing saved DS word restores its caller. Fill9795-97C6 is retained as50 original bytes, including its short relative branch. It has no absolute calls or CS data references. The proof checks byte identity and local offsets12 and1B. Original instruction placement and physical tag effects remain outside that proof.

The complete parent97C7-97D2 also calls97D3 and9808. The first selects CMOSB4, preserving its NMI mask, and forces AL=1. The second waits for input-buffer readiness, masks interrupts, sends commandC7 and data20, waits again, and restores entry flags. The port retains these operations through existing bounded controller helpers. OEM private4B5 writes are excluded. Both warm-reset paths7EDC and7F0B force the same controller transaction, without the parent's CMOSB4 read. The physical meaning of the affected P1 pin remains unproved.

The protected reset-pulse path calls968E before pulsing reset. The port's matching pulse producer now retains that owner's CPU/cache hardware order: CMOS34 CPU gate, CR0 CD/NW and INVD, CMOS3D L2 gate, transient1A, raw fill, CMOS70 and STI,04 bit0 clear, then1A transient clear. It never writes1E or issues WBINVD. bAIos uses its CPU request and qualified/requested L2 state instead of OEM private CMOS policy. The added saved FS word is an explicit ABI adaptation. Hardware and returned state are compared with the unmodified source; physical reset-stack identity is not claimed.

Pulse preparation7EE2-7EF3 then selects CMOS80 and writes register02&98, before BDA0472=1234 and commandFE. The port preserves the19-byte hardware block unchanged. F000 bit4 survives; C000 bit0 and protection bit5 clear. During the following video initialization, the port clears E000 bit3 before copying the retained physical provider, then remaps C000 and restores protection. Native mapped-memory tests cover this transition. The flat-memory controller fixture cannot qualify it.

The complete cache I/O comparison also retains reads and delay placement. Early reads at8F07,8F1D,8F4C,8F72 and90FC have no delay cycles. Executor9306-9323 delays after index selection, with no delay after its data read or write. Its1D size row reads the register even when the preserve mask is zero. Range owner9D63-9E41 performs two additional reads before selecting equivalent rows. Presence/size CMOS selections mask NMI. The port preserves those mask transitions through its private-state adaptation, and retains the late CMOS34/3D reads before the saved configuration gates. The executable proof compares chipset I/O and NMI transitions against the original code, including rejection of the previous013BF700 sequence.

## Shadow and video

OEM 9325 stages F000 before remapping the executing image. The port copies the full 64 KiB to 3000, executes its map/copy/protect transition there and returns far to F000. Saved System Shadow off/on uses the same staged method. The unused E800 setup resources are not BIOS services and are not copied.

The continuation at 94B1-94E7 reads register12 bits1:0 and register00. It sets register00 bit7 unless the mode is2 and register00's low nibble is9. In that exception it writes the original value. The port retains this conditional write after the initial system-shadow copy. The physical meaning of bit7 remains undocumented. This write was absent from the candidate that hard-locked at64.

OEM 94E9 distinguishes an external C000 provider from the embedded video input. The port retains the embedded first 32 KiB, stages it at 2000, maps/copies it to C000 and clears the unused E000 range. It verifies the full header/checksum, calls the actual provider, restores stack/segments/DF and installs the provider's video fallback. It resolves the returned far vector as segment times 16 plus offset and accepts the existing C0000-CFFFF physical handler window. Equivalent aliases are accepted. External and original-video providers retain the existing INT10-to-INT42 alias. The onboard VGA60 provider uses the guarded F000:F065 bridge at INT42. Onboard origin survives repeated warm reset. An external C000 provider can remain external when Video Shadow is Disabled. The onboard header must declare exactly 32 KiB. An external header can declare 1-128 units of 512 bytes, up to the 64 KiB C000 segment; validation checks its complete declared checksum. When external Video Shadow is Enabled, the existing staged copy covers only the declared bytes within the 32 KiB C000 window controlled by register 02 bit 0. The C800 window keeps its existing external mapping. A short provider does not cause a read or copy beyond its declared extent. Option-ROM discovery starts after the initialized video provider's full declared extent, rounded to the existing 2 KiB probe boundary, while retaining the board's selected first-segment floor. It does not interpret interior video bytes as separate option ROMs.

## ACC3221 and inherited services

Data-sheet reserved masks govern BE, DB, DC, DD, DE, FB and FE. UARTs are disabled before moving bases and sources. DE IRQ3 bits 7:6 and IRQ4 bits 5:4 use primary source 2 and secondary source 3. Same-IRQ onboard choices are rejected. The four standard bases are 3F8,2F8,3E8,2E8. Shared probing scans the complete collection and removes duplicates without truncating later candidates. Parallel BE bit 5 selects compatible/bidirectional operation. EPP/ECP is unsupported.

FB owns FDC enable and FE owns the primary IDE enable. The original Presario two-slot `ata_detect_primary` owner is retained, including channel reset, master/slave publication and IRQ14/cascade handoff. FDC VERSION 90 enables the existing enhanced commands; legacy 80 keeps conventional operation and rejects 2.88 MiB requests that need enhanced mode. A/B swap translates unit and both DOR motor bits.

Shared firmware continues to own the RTC, keyboard controller/IRQ1/INT16, PS/2 auxiliary commands/IRQ12, PIC/PIT, DMA transfers, floppy/ATA/ATAPI/EDD services, CD catalogs/emulation cleanup, option-ROM scanning, boot cursor, retry, Setup and display. No UMC, VLSI, PCI or M919 profile-state owner is included.

## Deferred meanings

ACC2046 CAS consumers correlate 2T with 04 and 3T with 08 in register 0B bits 3:2. That is not physical ACC2168 encoding authority; the PB430 OEM value remains. ACC2046 refresh selectors and AT-clock labels are also comparative only. The ADS consumer and the ACC2168 guide corroborate 1A bit 7; this is the supported Manual override. Turbo wiring, MUX, refresh encoding, wider cacheability controls and OEM-only POST Write remain deferred. No speculative selectors are exposed.


## Memory throughput and register capture

Build the DOS reader with `python -B pb430/diagnostics/build-acc-registers.py` from the repository root. Copy `pb430/build/diagnostics/ACCDUMP.COM` to the PB430. Run it in plain DOS without EMM386 or Windows. This utility targets the PB430 and does not detect the chipset automatically.

Run `ACCDUMP > BAION.TXT` immediately before CACHECHK with L1 and L2 enabled. Then disable only L2 in Setup and run `ACCDUMP > BAIOFF.TXT` before the same benchmark. Keep the boot media, memory managers, benchmark command, and other settings the same. Record whether each boot was cold or warm. The ACC386 ROM remains static comparison evidence, not a replacement ROM for this board.

The reader captures CR0, ports 78/92, and chipset registers00-14,16,18-1E,25,26. The2026-10-16 update adds14,16,19, covering every requested timing register. It writes only the F2 index selector and the ED delay port. It restores the index read from F2 before restoring the interrupt flag. It does not write F3, CMOS, cache controls, A20, or the reset port. Protected-mode DOS sessions return status 2 before chipset access. Output failure returns 1. Success returns 0. The focused builder checks the assembled COM program, including exact I/O order, output bytes, cache-state preservation, and DOS output errors. The V86 fixture provides DOS interrupt services directly and does not emulate EMM386.

Compare final register values, not just initialization tables. The PB430 reset continuation at E081-E0A7 replaces table register06 values with 13/33/B7/13 for jumper columns 0/1/2/3. For qualified 512 KiB L2 with L1 enabled, these are the expected final values after activation:

| Register | Jumper columns 0 / 1 / 2 / 3 |
| --- | --- |
| 01 | 93 / 93 / 93 / 93 |
| 04 | 15 / 15 / 15 / 35 |
| 06 | 13 / 33 / B7 / 13 |
| 07 | 18 / 18 / 14 / 18, plus retained bits 7:5 |
| 0B | 04 / 15 / 15 / 15 |
| 18 | 20 / 00 / 00 / 00, plus retained mask 8C |
| 1A | 24 plus retained bit 6 and any saved manual ADS delay |
| 1D | F0 |
| 1E | 7B plus retained bit 7 |
| 0C-11 | 0C 80 00 00 00 00 |

The column is `clamp((port78 & 7)-3,0,3)`. These expectations follow the qualified table at 9232, cold continuation, and late activation. They are not measured board values.

ACC386 auto-configuration at 0AAD uses a different selector, `(CMOS33 & 70h)>>4`, and a branch on register05 bit6. Its raw seven-column rows are:

| ROM offset | Bytes | Consumer |
| --- | --- | --- |
| 0A52 / 0A59 | 93 93 93 93 90 90 90 / 92 92 92 92 90 90 90 | Register01, cache selector false / true |
| 0A60 / 0A67 | 04 04 04 04 44 69 69 / 00 00 00 04 44 69 69 | Register0B, register05 bit6 set / clear |
| 0A6E / 0A75 | 00 00 00 00 08 08 08 / 08 08 08 08 08 88 88 | Register12, bit6 set / clear |
| 0A7C / 0A83 | 30 30 30 30 00 00 00 / 30 30 30 10 10 00 00 | Register18, bit6 set / clear |
| 0A91 / 0A98 | 04 04 04 04 04 04 04 / 24 24 24 24 24 24 24 | Register1A, bit6 set, cache selector false / true |
| 0A9F | 20 20 20 A0 A0 A0 A0 | Register1A, bit6 clear |

The consumers at 0AF0-0B7E also transform these bytes. Register01 gains bit7 when register05 bit6 is clear. Register0B gains bits2:0 mask05 when register04 bit7 is set. Register12 receives `(old & 0B) | (table & F4)`. Register18 receives the complete byte. Register1A receives `(old & 04) | (table & FB)`. The adjacent rows at 0A8A and 0AA6 are not selected by this mapped path.

ACC386 sets register04 bit7 at 1527-1533 after detecting L2, and conditionally again at DF00-DF17. PB430's qualified rows leave it clear. The ACC2168 guide identifies this bit as posted-write enable. It requires four 245 transceivers between the CPU and memory data buses. This is a concrete write-throughput lead, but it does not establish the cause of slow reads or authorize enabling it on PB430.

The CAS read-pulse field is register0B bits3:2. PB430 already uses field04 in every qualified column. ACC386's manual consumer at 0B84-0BA2 offers04/08, but its other timing fields are not documented for ACC2168. The ADS field, register1A bit7, is already clear under PB430 automatic policy. Compare live values before changing either setting.

The screenshot supplied on 2026-10-15 reports 15.0 MB/s main-memory reads, 44.7 MB/s L2 reads, and effective RAM read time280ns. Its 280ns value is four times the displayed70.0ns per byte. It includes the measured transfer path and does not directly measure a DRAM chip's access time. The 16 KiB and512 KiB breakpoints support the reported cache sizes, but do not explain the slow L2-miss path.

## Physical L2 comparison, 2026-10-15

The user supplied `withL2.jpg`, `noL2.jpg`, and `noL2speed.jpg`. Both dumps show plain DOS, `CR0=00000010`, `P78=1D`, and `P92=FC`. Of the 28 captured chipset registers, only these three differ:

| Register | L2 off | L2 on | Changed bit |
| --- | --- | --- | --- |
| 04 | 14 | 15 | Bit0 set |
| 1A | 2C | 24 | Bit3 cleared |
| 1E | 5B | 7B | Bit5 set |

The unchanged values are `00=A9 01=BF 02=F9 03=10 05=9C 06=B7 07=F4 08=F0 09=0F 0A=04 0B=15 0C=0C 0D=80 0E=00 0F=00 10=00 11=00 12=09 13=00 18=00 1B=10 1C=FE 1D=F0 25=02 26=00`.

P78 selects jumper column2. The captured06,0B,18 values match that reference column in both runs. Raw register01 readsBF in both runs. The earlier93 entry describes the programmed value, not a verified raw readback. Its difference fromBF does not establish a failed write or explain the L2-dependent slowdown. Fixed or reserved readback bits remain a possible explanation.

The changed bytes match the original late activation at9748-978A. The reset continuation leaves04=14,1A=2C,1E=5B. Declining L2 skips activation and retains those values. Activation selects1A mode08, enables04 bit0, runs the complete fill, sets1E bit5, then clears1A bits4:3. The physical enabled dump reaches the expected final15/24/7B state.

The guide does not define the electrical meaning of1A bit3 or1E bit5. No mapped normal enabled PB430 path supports leaving either bit in the disabled-state value. Do not label either as a burst, write-back, or wait-state control without further evidence. These captures compare the complete cache mode, not an isolated04-bit0 change.

The general timing table does not select by cache size. The128/256/512 KiB size rows use1D=FC/F8/F0 and1E=79/7B/7B. The256/512 KiB range rows and final activation are identical. Changing the size field is not an established timing optimization.

The new L2-off benchmark reports29.9 MB/s main-memory reads,140ns effective reads, and156ns effective writes. The earlier enabled screenshot reports15.0 MB/s,280ns, and218ns. L1 readings remain close at131.9 versus135.7 MB/s. Thus the supplied runs show roughly twice the read-transfer time with L2 enabled. They do not establish that the penalty is unique to512 KiB. The exact image identity and cold/warm reset type were not supplied with these captures.

The [original CACHECHK v4 distribution](https://www.os2site.com/sw/dos/util/cachchk4.zip) includes the author's `CACHECHK.DOC`, dated2/7/96. It describes sequential32-bit memory accesses in protected mode, with reads and writes measured separately. Eachq shortens a measurement. Thet option selects the memory limit, not a different read instruction. These descriptions support investigating the cache-miss transfer path, but do not prove its cause. The executable in that distribution is PKLITE-packed; its exact timing loop has not been audited. The full transcription and calculated differences are retained in `build/diagnostics/memory-throughput-20261015.json`.

The user subsequently confirmed that performance matches stock and requested faster timing experiments. Stock parity is the baseline, not the performance target. No firmware timing or cache-control code changed for this result. Do not use the ACC386 ROM as a PB430 flash image.

## Temporary timing trials

Build with `python -B pb430/diagnostics/build-acc-timing.py`. Copy `pb430/build/diagnostics/ACCPROBE.COM` to the PB430 DOS disk. Use the normal BIOS. Each command changes one register: F2/F4/F8 test05, H/S/T test18, R tests01, and C/5/4/W5/W4 test0B. W5/W4 measure writes. Other supported commands measure reads. C1 and D are withdrawn and refused. It restores the stock programmed value before each interrupt window and all DOS output.

Boot plain DOS with F5, with L1 and128 or512 KiB L2 enabled. Do not load memory managers or programs that use extended memory. The probe overwrites physical1-5 MiB as scratch space. It rejects protected mode, an installed XMS driver, insufficient reported memory, and an unsupported register state. In addition to the two supported cache-size encodings, unrelated-register trials accept Fast Memory Writes (0B=04) and Slow Refresh (05=9F). They preserve both choices throughout the test. The displayed size comes from a checked register pair: 1D=FC with1E=79 means128 KiB; 1D=F0 with1E=7B means512 KiB. Mismatched pairs are refused. This is not an independent test of installed SRAM capacity. The user reports that256 KiB is not a documented board size and has installed128 KiB. The ROM has a256 KiB table entry, but that does not establish board support. The probe now refuses that encoding. These guards qualify the expected PB430 configuration, not arbitrary ACC boards.

The original first trial remains available:

```dos
ACCPROBE 5
```

It prints three read rates: stock15, trial05, then stock15 again. Each phase also checks two memory patterns. The original second trial remains available:

```dos
ACCPROBE 4
```

This tests04 in the same sequence. Each command restores15 automatically. If the board hangs, use a hard reset or power cycle. Do not rely on warm reset to discard an experimental setting. If the utility reports a memory or register failure, stop testing that setting.

PB430 ROM table F000:920E supplies register0B values04/05/05/15. Table9256 supplies04/15/15/15. The current jumper selects column2, whose triples are `0B 00 05` at9214 and `0B 00 15` at925C. The table executor uses `(old & mask) | value`. Thus05 is an exact alternate table value for this column. It clears only bit4 of the current15. Trial04 also clears bit0 and has weaker support for this configuration: PB430 uses it in column0, and ACC386 contains it in its own tables. The ACC386 consumer can also OR05 into its table value when posted writes are enabled.

Both trials preserve CAS field04 in bits3:2. The guide groups the changed bits under Auto Configuration but does not explain their electrical meanings. These values are candidates, not established faster timings. Runtime changes with L2 active also require physical validation. These 0B trials leave cache activation, cache size, address mapping, refresh and clock controls unchanged. It does not write CMOS or the ROM.

Each phase writes and checks two address-dependent patterns across4 MiB, reads16 MiB through four sweeps, then checks the final pattern again. Work uses16 KiB blocks with interrupts disabled. Each block restores the stock programmed value and checks its readback before returning to real mode and allowing interrupts. The probe preserves the descriptor table, A20 control, parity mask and chipset index. Before extended writes, it checks that A20 is enabled and restores both witness locations. A failed restore retries the stock write without calling DOS.

The rate uses sequential32-bit reads and latched PIT channel0 counts. The utility requires binary mode3 and does not reprogram the timer. Mode3 decrements the count twice per timer clock, as specified in the [Intel8254 data sheet](https://www.cs.cmu.edu/~410/doc/8254.pdf). The result is MiB/s and is intended for comparison within this probe. It is not numerically interchangeable with CACHECHK's MB/s or effective access-time estimate. A passing pattern check does not establish long-term stability.

Exit status0 means all phases completed,1 means a memory/register/timing check failed,2 means the environment or argument was refused, and3 means normal output failed. The builder exercises the assembled program with synthetic devices. Cases cover both trials, rejected environments, readback failure, memory corruption, failed A20 witness and DOS output errors. Synthetic rates are test fixtures, not physical performance results. Results are in `build/diagnostics/acc-timing-checks.json`.

The first utility (1440 bytes, SUM32 `00020157`) reset the physical board with both arguments. Its first stock measurement wrote the accumulator through CS, the protected-mode code segment. A code segment is not writable. The error handler also wrote its flag through CS. The processor can fault and reset before reaching either trial, so these runs do not establish whether05 or04 is stable. The earlier Unicorn checks did not enforce this processor restriction.

The corrected utility uses the existing writable data descriptor for local state and a flat ES segment for extended memory. The builder now rejects executed protected-mode writes through CS. It also replaces each corrected store with its former CS override and requires both normal and failure paths to fail that check. The exact original binary fails the new check at offset03EE, its first accumulator update. This corrects a utility defect, not a BIOS timing setting.

The user then reported13.6 MiB/s on every row of both corrected trials. Thus15/05/15 and15/04/15 completed without a displayed throughput change. This is physical evidence that these two changes did not improve this read workload. It does not show their effect on writes or other workloads. Keep15 as the BIOS baseline. The utility reports MiB/s, even though the user described the unit as MB/s.

### CAS response comparison

Run `ACCPROBE C` from the same clean DOS environment. It prints stock15, alternate19, then restored stock15. Compare the middle row with both surrounding rows. This changes only CAS bits3:2, from04 to08, while retaining all other bits. The AMI guide describes2T/3T and the ACC386 manual consumer at0B84-0BA2 writes04/08. This trial is a slower reference setting used to test whether the measured workload responds to this field. It is not an established speed improvement. Stock restoration, memory checks and hard-reset recovery remain the same as the original trials.

Do not infer a usable CAS00 setting from raw ACC386 tableA67. Its columns correspond to16/20/25/33/40/50/66 MHz, as shown by the clock table at0637 and its consumer at064F-0660. PB430 jumper column2 does not mean ACC386 column2. More importantly, ordinary ACC386 POST calls cache detection atC916 before timing setup atC9B5. With Auto Configuration enabled and register05 bit6 clear, the cache finish at14EC-1533 sets register04 bit7. The later consumer at0B13-0B17 then ORs05 into the raw timing byte. A raw00 therefore becomes05, which retains CAS field04. The apparent zero-field candidate does not survive the complete reference sequence and was excluded from the original probe. The later C1 experiment below has separate data-sheet evidence.

If19 is slower, the result establishes that this CAS field affects the current measured read path. If19 matches15, that leaves timing sensitivity, hardware latching and workload effects unresolved. Neither outcome establishes a faster setting. The builder covers C/c arguments, alternate-field readback failure, memory corruption, and output failure after the trial, in addition to the earlier checks.

The user subsequently reported12.2 MiB/s for0B=19. Compared with the previously reported13.6 MiB/s stock result, the longer CAS field reduced throughput by about10.3%. This establishes a measured effect from bits3:2. It does not validate a zero-field encoding. The estimated four-byte transfer-time difference is32.2ns, consistent with roughly one33MHz bus clock, but includes the complete measured read path. The latest message did not repeat the surrounding stock rows. See the register map for the calculation and the VLSI comparison.

### One-cycle CAS read experiment

C1 is withdrawn. The first physical run returned a generic memory/register failure. The diagnostic build then hard-locked before displaying the failure. The exact cause and phase remain unknown. Do not run an older C1 utility again. The current utility rejects C1 before chipset access and exits with status2.

The hypothesis came from the [related ACC data sheets](register-map.md#related-acc-data-sheets-and-the-next-read-timing-probe). ACC2046 revision1.2 page29 and ACC2087 revision1.1 page78 define read CAS bits3:2 as1/2/3/4cycles. C1 tested0B15/11/15. The failed hardware results do not establish that this encoding is usable on ACC2168. Keep the stock15 in the BIOS.

The diagnostic revision also had an unsafe ordering: it saved failure evidence to local RAM before restoring stock timing. A new assembled-code check rejects that ordering and reproduces it in the previous diagnostic binary. This is a verified utility weakness, not proof of the physical lock's cause. The corrected path holds evidence in processor registers until stock timing reads back correctly. Recovery and initial register readback use inline I/O without a stack call. The normal timer accumulator is also updated only after restoration.

Supported probes retain their memory and environment guards. Errors identify the selected register/value, register readback bytes, RAM mismatch address/data, A20 failure, or a stopped timer. Diagnostics and DOS output cannot guarantee recovery from corrupted instruction fetches or failed restoration. A hanging restoration loop still needs a hard reset or power cycle. Do not keep exercising a setting that fails or locks just to obtain a better error message.

### Register01 reference comparison

Run `ACCPROBE R` from the same clean DOS environment. It writes93, then92, then93 in three measured phases. Compare the middle read rate and RAM-check result with both surrounding rows. The test works with either supported cache-size configuration; it never changes the size or cache activation registers. Register0B remains15 throughout this command.

The candidate comes from the ACC386 normal POST path C9B5 ->0AAD. Its cache-enabled table at0A59 contains92 for33 MHz; the cache-disabled table at0A52 contains93. The consumer at0AFC-0AFE writes that value, and the preceding conditional OR80 does not change it. No later direct01 write was found in the mapped ordinary POST continuation. PB430 also writes92 at8FE0-8FEE during SRAM sizing, then restores93 at9142-9150.

This does not prove that92 is a normal PB430 setting. ACC386's preceding automatic cache finish enables posted writes through04 bit7. PB430 has that bit clear, and its own92 use is inside a temporary SRAM mode. The new trial preserves PB430's existing cache state. That combination is an experiment. The exact electrical meaning of01 bit0 remains unknown; do not label it a burst or wait-state switch.

The utility writes the exact reference values93/92. It requires readbacks BF/BE respectively, based on the captured BF baseline and the one-bit trial. The extra2C bits have not been decoded. This readback requirement is an experimental guard, not a claim that those bits are reserved or fixed. The utility never writes BF or BE. A candidate readback mismatch restores93 and stops; a restore mismatch keeps retrying93 without returning to DOS. Use a hard reset or power cycle if it hangs.

The focused assembled-code checks cover R/r, both size encodings, unexpected01 or size values, trial readback failure, RAM corruption, output failure, and a missed restore write. These are synthetic checks, not physical timing or stability evidence. The user subsequently ran R and reported13.6 MiB/s on all three rows:93/92/93. This establishes physical completion and no measured read-throughput gain for this setting in the reported configuration. It does not establish long-term stability or the effect on other workloads. Keep the stock programmed01=93. The probe changes no firmware, posted-write enable, refresh, clock, mapping, or cache-size policy.


### Physical comparison of128 and512 KiB

After installing128 KiB, the user confirmed no RAM-throughput difference compared with512 KiB. This contradicts the proposed512 KiB-specific cause on this board. The user also measured better overall performance with either cache size than with L2 disabled, despite the slower main-memory streaming result. No numerical overall-performance scores were supplied. Keep the streaming-read measurement separate from overall workload performance; the former is not grounds to disable L2.

The R probe completed with13.6 MiB/s on all rows. No faster setting has been established by the01 or0B trials. The remaining target is the memory-access cost common to the tested L2 configurations, not an assumed512 KiB-only defect. Cache-miss/refill overhead remains a hypothesis; these results do not isolate its electrical cause. The256 KiB population research remains an optional hardware question, not a demonstrated performance remedy.

### 256 KiB population and jumper deduction

The UKT Support page is titled "Packard Bell 430/440/440T Motherboard". Its cache table documents32,128,512 KiB, not256 KiB. The original Packard Bell service document [PB430.003, 1994-03-01, section3](https://www.barovelli.com/projects/computer/pb/pb430003.htm) agrees. It specifies four data SRAMs at U15/U19/U24/U30 and a combined tag/dirty SRAM at U35. The current physical configuration is128 KiB, per the user.

| Capacity | J30 | J31 | J32 | J33 | Evidence |
| --- | --- | --- | --- | --- | --- |
|128 KiB|1-2 closed|2-3|2-3|1-2|Documented|
|512 KiB|1-2 closed|2-3|2-3|2-3|Documented|
|256 KiB with compatible64Kx8 SRAMs|1-2 closed|2-3|2-3|2-3|Inferred candidate only; uses the512 KiB wiring configuration|

The reason for the candidate is chip pin compatibility, not an interpolation between jumper positions. Four64Kx8 chips provide256 KiB while retaining four8-bit data lanes. The original [ICSI IS61C512 data sheet](https://www.kontest.ru/datasheet/icsi/is61c512.pdf), pages1-2, identifies a5V64Kx8 part, offers a32-pin300mil DIP package, and explicitly states compatibility with128Kx8 devices. Its DIP pinout has NC on pins1/2, A15 on31, CE2 on30, WE on29, VCC on32, and GND on16. CE2 must be high when selected. This is a part-specific example, not permission to substitute every64Kx8 SRAM. Package, pinout, enable polarity, voltage, and speed must match the actual sockets and installed parts. A matched five-chip64Kx8 population, including U35, is the simplest inferred configuration; the correct smaller tag alternative has not been established.

The stock ROM also has a real256 KiB discovery branch, not just an unused table constant. After the512 KiB alias test, F000:9025-905E compares the20000 and40000 locations in temporary SRAM mode and records size code3 on success. The size tables supply1D=F8 and1E=7B. The port retains that discovery branch. Therefore a compatible64Kx8 population could be detected with the512 KiB socket wiring, without forcing the BIOS size field. This does not prove the motherboard routes every required signal correctly for that population.

There is no supported deduction that a different jumper combination alone converts the existing four32Kx8 chips into256 KiB. Their total data capacity is128 KiB. Nor should two128Kx8 data chips be treated as a substitute for the four data lanes. Do not invent a new J30-J33 combination from unused combinations in the table.

Remaining limit: the board traces and the user's exact SRAM part numbers have not been checked. The inferred256 KiB row is not a verified installation instruction. Physical acceptance would require correct POST size, the expected read-only register dump, memory integrity, and a256 KiB cache breakpoint. The delivered performance probe currently accepts128/512 KiB only; it does not enable or qualify this experimental256 KiB population.


## Slower refresh and register18 trials

Run these commands separately from the same plain DOS environment described above. Keep L1 and L2 enabled.

| Command | Programmed stock / trial / restored | Purpose |
| --- | --- | --- |
| `ACCPROBE F2` | 05:9C /9D /9C | Nominal refresh interval15 /30 /15 microseconds |
| `ACCPROBE F4` | 05:9C /9E /9C | Nominal refresh interval15 /60 /15 microseconds |
| `ACCPROBE F8` | 05:9C /9F /9C | Nominal refresh interval15 /120 /15 microseconds |
| `ACCPROBE T` | 18:00 /10 /00 | Compare the ACC38633MHz automatic byte |
| `ACCPROBE S` | 18:00 /20 /00 | Test the remaining sampling-delay hypothesis |
| `ACCPROBE D` | No writes | Withdrawn after a hardware lock; the command now refuses before hardware access |
| `ACCPROBE H` | 18:00 /02 /00 | Compare hidden refresh while ordinary refresh remains enabled |

Start with F2. If all RAM checks pass, compare the trial rate with both stock rows before proceeding to F4 and F8. Run T separately. Stop after a failed RAM check or lock. A lock requires a hard reset or power cycle.

The ACC2168 guide lists refresh periods15/30/60/120 microseconds. ACC3860952-0967 maps these choices to register05 bits1:0. The consumer preserves bits7:2. The trials retain the captured9C upper bits and leave register06 clock control unchanged. These are reference-backed experiments on PB430, not validated firmware defaults.

Each refresh phase adds one continuous one-second wait after each of the two pattern fills. A full4MiB read first evicts dirty cache lines. No scratch-memory reads occur during the wait. This prevents the benchmark's ordinary per-block restoration from hiding a retention failure. The probe then restores normal refresh and checks every pattern word. It repeats this for stock, trial and restored stock. Interrupts remain disabled during each wait, so the DOS clock can lose several seconds. A passing check covers this scratch region and short test duration only. Longer refresh intervals can corrupt other RAM before the program can recover.

The timing trial follows ACC386C9B5 ->0AAD. With05 bit6 clear,0B40-0B4F selects row0A83 and writes its33MHz column,10, to register18. PB430 uses00. The AMI guide groups this byte under automatic configuration without decoding its electrical fields. The ACC386 path also depends on its own cache and posted-write setup. This bounded00/10/00 comparison does not copy that entire policy or establish that10 is faster. The probe does not alter cache activation, mapping, posted-write enable or clock control.

Both command groups require baseline05=9C and18=00. They use the existing readback, pattern-check, restoration and output-error paths. No CMOS or firmware settings are saved.

For the sampling-delay comparison, use `ACCPROBE S` from the accepted normal BIOS, with Slow Refresh disabled and plain DOS started with F5. Keep L1 and L2 enabled. The S trial changes only register18 bit5. ACC2046 page33 describes removing a one-cycle sampling delay. ACC2087 page85 instead describes adding a DRAM/ISA off-cycle wait. These are competing definitions for related chips, not a confirmed ACC2168 function. PB430 uses20 during SRAM prerequisites; that does not establish its suitability for steady RAM access. The trial compares stock00, candidate20, and restored00 without changing memory mapping, clock selection, cache geometry, or cache activation.

The D trial attempted register04:15/05/15, clearing DRAM-read burst enable while preserving the other fields. The user reported a lock. No last phase or POST code was supplied, so the failing operation is unknown. The utility now refuses D before any hardware access. This result does not establish whether a non-burst configuration could work when initialized from reset. Keep register04 at its working value.

Run `ACCPROBE H` separately under the same plain-DOS and normal-refresh conditions. ACC2046 page33 and ACC2087 page85 both name register18 bit1 as hidden-burst-refresh enable. The H trial preserves bit0 at zero, keeping ordinary AT refresh enabled. It leaves register05, DMA, PIT programming, cache settings, and memory mapping unchanged. Neither reference ROM supplies a working hidden-refresh example; the possible benefit on ACC2168 remains unproved.

H first reads register19 and requires `(19 & F7)==00`. This retains conservative refresh timing and a single refresh per request under the related-chip definitions. The utility does not write19. If the guard fails, it prints the observed19 byte and stops before timing writes. Each phase includes the existing full scratch read, one-second retention wait, and pattern verification before measuring throughput. A passing scratch test does not establish retention or stability across all installed RAM.

Each phase prints the register and value, such as `Testing 04=05`, before changing timing. Port80 shows B0 for pattern writes, B1 for verification, and B2 for timed reads. Refresh trials also use B3 for retention and B4 for eviction. BE means the chunk restored stock timing; BF means a failure restored stock timing. The measurement and recovery paths use no stack calls while trial timing is active. The utility restores the stock byte and checks its readback before saving diagnostic data or calling DOS. A hard lock can still prevent restoration. Report the last Testing line and port80 code if that occurs; power-cycle before another trial.

## Presario60MHz VGA option

Build with `python -B pb430/tools/build.py --vga60`. The output is `pb430/build/vga60/baios-pb430.bin`. The main build now uses the physically accepted VGA60 provider. Use `--stock-vga` for an original-video variant under `pb430/build/stock-vga/`. Run the focused boot, display and clock-register check with `python -B pb430/tools/test-port.py --case vga60`.

The optional image uses the exact first32768 bytes of `presario-800/reference/baios-presario800-vga141-bus07.bin`, retained as `pb430/reference/gd542x-141-vga60.rom`. Its SHA-256 is `a055782154f63644da7f04038f0a163b8925f136172a55aca35960150da1b2a8`. The source is the Presario's Cirrus1.41 provider with its established bus07 changes: SR16=48, SR1F=22, SR17=00, plus the ROM checksum. SR1F22 selects approximately60.85MHz of video-memory clock. This is not a60Hz display-refresh setting. See the [Presario VGA record](../../presario-800/docs/vga141.md).

The installer at C000:271A writes INT42=F000:F065 and calls it at2745 before returning. PB430 therefore includes the existing Presario compatibility routine at that fixed address only in VGA60 builds. It accepts AH below1D and jumps to the1.41 INT10 entry C000:2897. After installation, PB430 validates the installed INT10 vector and keeps INT42 at F000:F065 for the onboard VGA60 provider. The bridge returns unchanged for AH1D and above. VGA1.41 sends unsupported calls through INT42 at C000:2930. Aliasing INT42 to INT10 therefore causes repeated entry into the VGA handler. Landmark6.00 and SI8 probe unsupported video extensions before drawing their interfaces, including SI8 AX=FE01. Preserve the guarded fallback after installation as well as during it. The VGA ROM bytes remain unchanged. The cache startup sequence remains unchanged.

The faster video-memory clock exceeds the nominal GD5428 clock specification. The user confirms that VGA60 works on PB430 and is measurably faster. The earlier no-video report was caused by an absent ROM chip, not a failed VGA candidate. Long-term stability across video modes remains unqualified.


## Slow Refresh in Setup

The F8 probe increased the reported read rate from13.6 to14.0 MiB/s, about2.9%. The user reports no change from the register18 T probe. Register18 therefore remains at its stock value.

Setup > Chipset > Slow Refresh selects the F8 interval. Disabled selects normal refresh. Enabled selects nominal120 microseconds by setting register05 bits1:0 to3. Both choices preserve bits7:2. The default is Disabled, and existing saved settings remain Disabled. The setting works in Auto and Manual modes. Save with F10 and restart to apply it.

The existing24-byte chipset record stores this Boolean in byte7, CMOS72. Byte6 remains Fast Boot. The unchanged checksum covers both fields. Old valid records contain zero in the new field. Values above1 are invalid, and bytes8-23 remain reserved.

Normal startup restores refresh before warm cache teardown, DRAM work and reference cache initialization. Service resumes keep the current refresh choice. The complete stock activation, fill, controller handling, stack restoration and timer restoration run first. The saved refresh policy then runs after the cache returns to normal mode. The policy also runs when L1 or L2 is disabled. Setup edits do not change refresh while the menu is open. Disable Slow Refresh before the ACCPROBE F2/F4/F8 divider comparisons. Other supported commands preserve its current setting.

## Early interleave experiment

The user authorizes a cold-start interleave experiment with all four banks populated. Build with `python -B pb430/tools/build.py --interleave`. The separate flash image is `build/interleave/baios-pb430.bin`,131072bytes. The normal build keeps the established page mode.

The user confirmed the physical bank order: onboard RAM is bank0; the inner SIMM socket supplies banks1 and2 with a double-sided module; the outer socket supplies bank3. The working16MiB population is4MiB onboard, an8MiB double-sided inner SIMM, and a4MiB single-sided outer SIMM. Reversing those SIMMs does not POST. Keep the working socket arrangement for this experiment. Four populated electrical banks do not require four SIMM sockets.

The candidate runs the existing page-mode bank probe first. It requires raw bank pattern3333 and unchanged routing, which identify four4MiB banks. Before the first persistent firmware state or stack, it selects the reference mode0 map:12low bits clear,00low8 as the intermediate map,05bit4 clear, then00low5. The12 maskF4 also clears the page-mode geometry extension left by the first probe. This adapts PB430994E-997A to an already identified topology. Map5 comes from PB4308D71/8DA7 and is independently corroborated by ACC386E68. No instruction from the defective dormant mode0 matcher is reused: its9BA6 comparison destroys the preceding match flag before9BB0 consumes it.

The candidate attempts05bit4 clear even though the related-chip clock-status evidence predicts that this can be read-only. This is the explicit experiment. It does not write the clock-mode status bit, clock selectors, CAS timing, cache line size, or burst controls. It verifies the mode/map readbacks, then writes and reads two inverse address-dependent patterns across all conventional RAM and1-16MiB. The video/ROM hole is excluded. All addresses are filled before verification, so bank aliases cannot pass merely by matching the most recent write. It then runs the existing RAM count, clearing and first-stack test. Fast Boot does not skip this early check.

| Early code | Meaning and next observation |
| --- | --- |
|2F|Four4MiB banks accepted; mode transition begins|
|31|Mode/map readbacks accepted; destructive16MiB validation begins|
|32|Both address-pattern passes completed; existing count/POST resumes|
|E2|Register05 bit4 stayed set after the clear write. Page mode was not disabled.|
|E4|Register00 low nibble did not read back as5.|
|E5|Register12 bits selected by mask0B did not clear.|
|E3|Detected bank pattern/routing differs from the qualified four4MiB layout. No interleave write is attempted.|
|E6|Memory verification failed after the mode switch. Candidate stops before creating firmware state.|

On a successful boot, run ACCDUMP and a memory benchmark. Expected mode fields after normal shadow completion are00low5,12low0,13=00, and05bit4 clear. With the previously captured upper bits and Slow Refresh disabled this is00=A5,05=8C,12=00. Slow Refresh enabled changes05low2bits only. A passing readback does not by itself prove electrical interleave or a speed gain.

The candidate deliberately stops on failure. It does not attempt a late map rollback after memory access. Power off before the first flash trial and keep the accepted normal image available. Warm reset preserves an accepted live map through the existing owner. The cache source, hardware operation order, tables, and transient windows remain unchanged.

ACC2046 pages11-12 require different CAS wiring for its double-phase/interleaved configuration. That definition remains comparison evidence for ACC2168. The experiment tests the board rather than treating the related-chip restriction as a confirmed ACC2168 prohibition.

## Burst timing notation

A label such as3-2-2-2 gives the clock count for the first transfer and each of the following three transfers in a burst. It is not another spelling of the0B CAS field. ACC2046 pages17-18 describe cache burst enable, line size, and memory reads on a cache miss separately. Its five-cycle128-bit cache-line fill is consistent with2-1-1-1-style capability in the documented configuration, but does not establish PB430's present burst timing.

Related-chip definitions place DRAM burst enable at04bit4, cache burst enable at04bit3, cache line size at04bits2:1, and cache read wait at04bit5. Current15 enables DRAM burst but leaves cache burst clear and selects a32-bit line under that model. ACC2087 page85 additionally defines18bit7 forX-2-2-2 cache reads, while ACC2046 reserves that bit. No reference proves the newer selector exists on ACC2168. There is therefore no verified PB4303-2-2-2/2-1-1-1 preset yet. Keep those controls separate from the interleave trial so its effect can be measured.

## Cache-to-L1 burst experiment

Physical result: the board booted with `04=1D`, and the user reported effective RAM access times up to 343 ns read and 218 ns write. Earlier values were 280 ns read and 218 ns write. Read time increased about 22.5%, while write time was unchanged. The user reported that L1 and L2 remained reasonably fast, without numerical cache rates. All other registers shown in the new dump match the earlier enabled-cache dump, including `05=9C`, `18=00`, `1D=F0`, and `1E=7B`. The size pair reports the 512 KiB configuration. It does not establish the currently installed chip population independently.

Keep burst disabled in the normal BIOS. Restore `build/baios-pb430.bin` before using ACCPROBE. The result does not qualify a different cache-line size or posted-write configuration. The retained experiment below documents the rejected setting.

Build `python -B pb430/tools/build.py --cache-burst`. The separate flash image is `build/cache-burst/baios-pb430.bin`,131072bytes. The default build retains the accepted behavior and VGA60 input.

This candidate sets only register04 bit3, changing15 to1D after the complete stock cache parent returns. ACC2046 page26 and ACC2087 page75 name this bit as cache-read burst into the486 internal cache. The existing line-size bits, DRAM-burst bit, cache enable, cache size, and tag mapping remain unchanged. ACC2046 pages17-18 describe larger cache lines and their physical tag organization. They do not establish a performance benefit for this board's current32-bit line encoding. This candidate tests that uncertainty without also changing the geometry.

The existing late-memory-policy hook first applies the saved refresh choice. The burst helper then requires enabled L1, qualified/enabled L2, at least4MiB of extended RAM, and the working04=15 value. It saves caller state, disables and invalidates L1, and writes an address-dependent pattern through the stock cache path across1-5MiB. It sets04=1D and checks readback before restoring L1 and checking every word. It repeats with the inverse pattern, returning to04=15 while writing the second pattern. These are the same address-dependent patterns used by ACCPROBE. Fast Boot does not skip this check. Scratch RAM is overwritten before option-ROM discovery and boot.

The complete stock cache source, tables, fill sequence, timer handling, and temporary tag window remain unchanged. The experiment has three explicit adaptations outside that window: the late helper; a stackless clear after normal startup disables L1; and a clear before warm-reset teardown or chipset-policy reapplication. Service resumes05/0A preserve the active state. The helper preserves normal flags, registers, CR0, segment registers, descriptor table, A20 state, and parity control on success. A failed check clears the experimental bit with L1 held off and halts. A failed clear halts separately.

| Code | Meaning |
| --- | --- |
|7A|Stock pattern written; burst enable write follows|
|7B|Burst control readback accepted; L1 enable follows|
|7C|L1 enabled; cached read verification begins|
|7D|Both pattern checks passed|
|7E|Experiment skipped because cache policy or memory size does not qualify|
|E9|Experimental burst bit could not be cleared|
|EC|Burst-enable readback rejected; stock control restored|
|ED|Cached read failed; stock control restored|
|EF|Unexpected starting CPU or cache-control state|

Power off before flashing. Use the current working SIMM arrangement. If POST completes, run ACCDUMP and CACHECHK with L1 and L2 enabled. Register04 should read1D. Compare the main-memory result with the same Slow Refresh choice used for the baseline. ACCPROBE intentionally refuses this changed cache-control baseline. A hard lock can occur before a diagnostic is printed; keep the accepted normal ROM available.

## Write throughput comparison

Restore the normal BIOS before this test. Disable Fast Memory Writes and Slow Refresh, then boot plain DOS with F5. Keep L1 and L2 enabled. Run `ACCPROBE W5`. If it completes without an error, run `ACCPROBE W4` separately. These commands use the same guards and scratch area as the read probes. They overwrite physical 1-5 MiB, so do not load a memory manager or another program that uses extended RAM.

W5 compares register0B values15/05/15. W4 compares15/04/15. Both sequences previously completed the read probe without a speed change. The related ACC2046 and ACC2087 manuals identify the changed fields as write precharge and write CAS width. The physical write results appear below. Neither command enables posted writes or changes cache activation, mapping, clock, or refresh settings.

Each phase first checks two address-dependent memory patterns. It then times four sequential4 MiB writes with `REP STOSD` and checks the final data. The output labels these rates `Write`. Compare the middle row with its two stock rows. The rate includes the existing cache policy and is not an isolated DRAM latency measurement. The program restores stock timing before each interrupt window and all output, including failure reports. The existing read commands retain their read workload.

These results cannot establish faster reads. The purpose is to measure the write controls that earlier read-only comparisons did not exercise. Stop after any failed check or lock. The C1 and D commands remain withdrawn.

The user corrected the first report: W5 stayed at 18.7 MiB/s, while W4 reached 21.6 MiB/s. The W4 gain is about 15.5%. This supports the combined tested value `0B=04`. It does not establish that changing bit0 alone gives the same gain. The earlier read trials showed no improvement with04 or05.

### Fast Memory Writes in Setup

This section records the original shortcut implementation. The shortcut is now removed. Its equivalent controls are Write CAS Width 1T and Write CAS Precharge 1T. Existing timing records and legacy migration remain supported. Current timing and recovery behavior is described in the port README.

The Chipset page offers Fast Memory Writes, disabled by default. It uses the existing menu, save, and restart behavior. Enabled applies the tested04 value after the complete stock cache sequence. Disabled retains stock15. The choice works in Auto and Manual configuration. It requires both caches enabled, qualified active L2, the tested jumper value, and the stock04/0B baseline. If those conditions do not match, the firmware skips the optimization.

The choice occupies the previously reserved ninth byte in the existing chipset settings record, at CMOS73. Valid older records contain zero there and therefore keep the option disabled. Defaults, invalid settings, and the existing recovery path also leave it disabled. The stored value is limited to0 or1.

Normal startup and controlled warm reset restore15 before cache teardown or initialization. Chipset-policy reapplication does the same. This keeps the reference cache sequence at its stock timing. Shutdown service resumes retain the running state. No instruction or diagnostic is added inside the temporary cache window. The burst experiment remains disabled in the normal image.

POST76 marks the timing write,77 confirms its readback, and78 means the enabled option could not be applied. E8 in this timing path means a write or restoration readback failed. A successful readback does not establish RAM stability. Use ACCDUMP to confirm `0B=04` with the option enabled and `0B=15` with it disabled. Run CACHECHK and normal workloads, then test Ctrl+Alt+Del and a cold start. Only ACCPROBE commands that test register0B require Fast Memory Writes disabled. Other supported commands preserve it.


## Read trials with Fast Memory Writes enabled

With the Setup toggle enabled, the user reported 180 ns effective write access and 271 ns read access. The earlier write result was 218 ns. This is about 17.4% less write time. No Slow Refresh choice was supplied with this result, so do not attribute the smaller read-time change to Fast Memory Writes alone. Reset reliability and long-term stability were not reported in this message.

The user tested both S and H with Fast Memory Writes and Slow Refresh enabled. Every row returned 14.0 MiB/s. Both comparisons are neutral in this configuration. Slow Refresh accounts for the increase from the earlier 13.6 MiB/s baseline. Keep register18 at its stock value.

The new starting-settings line must show `0B=04`. It also shows `05=9C` for normal refresh or `05=9F` for Slow Refresh. Both are accepted for S/H/R/T. F2/F4/F8 accept either write timing but require Slow Refresh disabled because those commands test the refresh divider itself. The0B commands C/5/4/W5/W4 still require Fast Memory Writes disabled. Unknown write/refresh values and the rejected burst configuration remain refused.

The earlier S and H results were neutral with stock write timing. These tests check the combinations, not newly established faster read settings. The one-cycle read-CAS and DRAM-burst-disable commands remain withdrawn. Posted-write buffering and different cache-line sizes still lack qualified board prerequisites. No new BIOS image is needed for these DOS comparisons. The probe still overwrites1-5 MiB scratch RAM.


## Address-order diagnostic

Build with `python -B pb430/diagnostics/build-acc-order.py`. Copy `pb430/build/diagnostics/ACCORDER.COM` to the DOS disk. Keep the normal BIOS, L1 enabled, and the current Fast Memory Writes and Slow Refresh choices. Boot plain DOS with F5 and no memory manager, then run `ACCORDER` without arguments. The utility overwrites scratch RAM from 1 MiB to 5 MiB. It uses the existing ACCPROBE admission, A20, timer and machine-state restoration code. It does not write chipset configuration registers or change cache policy.

The three rows are Linear, 4K-column, and Linear again. Each row follows one pointer per 16-byte line through the same 4 MiB span. Linear visits adjacent lines. 4K-column visits successive 4 KiB offsets before moving to the next line offset. Links are built and checked before timing. One untimed traversal precedes four measured traversals. Both orders use the same bounded pointer-load loop, with pointer range and alignment checks. A full traversal reads 1 MiB of useful pointer bytes. Each row measures 4 MiB of useful reads.

The reported useful-byte MiB/s includes pointer checks and loop overhead. Compare these rows with each other, not directly with ACCPROBE or CACHECHK. A slower column row establishes an address-order penalty. It does not identify a physical DRAM row or prove a particular timing field. Similar rows do not prove that every address pattern has the same cost.

The fixed 16-byte spacing avoids multiplying CPU line fills in only one order. AMD documents 16-byte cache line fills in the Am5x86 [data sheet, page 16](https://www.amd.com/content/dam/amd/en/documents/archived-tech-docs/datasheets/19751.pdf). ACC2046 pages 10-11 describe page-hit and page-miss costs, but the PB430 address multiplexing is not fully decoded.

ACCORDER also accepts the supported L2-disabled register states. To compare L2 states, change the existing Setup choice, reboot with F5, and run the same command. Keep Slow Refresh unchanged. The banner prints the actual L2, write-timing and refresh state. The BIOS applies Fast Memory Writes only when both caches are enabled. For a comparison that changes only L2, disable Fast Memory Writes for both runs. The normal configuration can be restored through Setup afterward. No ROM flash is needed.


### Physical address-order result

The2026-10-16 photograph reports Linear3.9,4K-column3.5,Linear3.9 usefulMiB/s. All pointer checks passed. The banner shows L2 enabled, the512KiB configuration,0B=04 and05=9F. Column-order throughput is about10.3% lower, with about11.4% more time per traversal. This is not a direct DRAM latency measurement or proof of a particular row mapping.

## Combined33MHz/60ns timing profile

The user's live `ACCNOW.TXT` supplies14=06,16=00,19=08, with01=BF,04=15,0B=04,12=09,18=00 and05=9F. The [register comparison and calculation](register-map.md#live-timing-snapshot-and-probable-acc2168-model) retains the complete capture and the probable2168 field table. Bank layout is outside this experiment.

The user selected a combined faster profile rather than more isolated conservative trials. Build `python -B pb430/diagnostics/build-acc-profile.py`. Copy `pb430/build/diagnostics/ACCPROF.COM` to the DOS disk. Keep the current normal BIOS and enable L1, L2, Fast Memory Writes, and Slow Refresh. Boot plain DOS withF5 and no memory manager. Run `ACCPROF` without arguments. No ROM flash is needed. This program overwrites scratch RAM from1MiB to5MiB, as ACCPROBE does.

| Register | Programmed baseline | Trial | Intended effect under the probable map |
| --- | --- | --- | --- |
|01|93, readbackBF|83, expectedAF|Enable RAS timeout|
|0B|04|00|Reduce programmed read CAS from2T to1T. Keep fast write fields|
|16|00|03|Advance read CAS by half a clock, extending the1T pulse to1.5T|
|19|08|28|Reduce refresh RAS precharge from4T to2T. Preserve bit3, active width and burst count|

At33MHz, the intended read pulse and read RAS-to-CAS interval are each about45.455ns under the2087 edge model. RAS precharge remains60.606ns. This is a coherent hypothesis, not proof of2168 edge timing. It differs from the failed C1 experiment, which had no CAS extension. The normal C1 command stays withdrawn. Register04 remains15 throughout, preserving the working DRAM-burst and cache policy. Register12 remains09. Slow Refresh stays9F, and the fast write widths remain at their working values.

ACCPROF uses the existing ACCPROBE engine: two address-dependent patterns, retention waits, four timed4MiB reads, final data verification, and baseline/trial/baseline output. It checks all profile prerequisites before touching extended RAM.16=03 must read back before0B=00 is written.19 and01 also need matching readback. Every chunk restores0B=04 first, then16=00,19=08 and01=93. It checks every restoration before a diagnostic store, interrupt window, BIOS call or DOS output. A rejected prerequisite cannot reach the shorter CAS write. Restoration retries retain the existing fail-closed behavior.

The result rows identify0B=04 for the baseline and0B=00 for the whole trial profile. The banner lists all four writes. A readback failure names the failing register and expected/actual values. POSTB0/B1/B2/B3/B4 retain their existing pattern-write, verify, measurement, retention-wait and eviction meanings. BE marks a restored successful chunk andBF a restored failed chunk.

The host checks execute the assembled COM with synthetic devices. They cover both supported cache sizes, every profile readback rejection, ignored restoration writes, incompatible starting fields, memory failure, A20 failure, timer failure, protected mode and DOS output errors. They require all baseline register values at every interrupt and output boundary. The normal ACCPROBE and ACCORDER binaries remain byte-identical. These checks do not establish physical stability. A hardware lock can prevent restoration and require a reset or power cycle.


### Combined profile result

The user reports that ACCPROF increased read throughput from14.0 to15.7MiB/s. This is12.1% faster, or10.8% less time for the same useful data. The equivalent four-byte transfer time falls from272.48ns to242.97ns, about29.50ns. This is close to one33MHz bus clock and supports the shorter-read-cycle hypothesis. It does not identify the separate effects of RAS timeout, CAS advance, CAS width and refresh precharge. The third row, individual diagnostics and long-term stability were not separately reported.

The normal BIOS still uses the captured baseline after the utility restores it. The [current-versus-available timing menu](register-map.md#timing-options-at-a-glance) lists every relevant field, its present value, available encodings, intended trial state and prior measured results.
