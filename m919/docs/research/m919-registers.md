# M919 register evidence

All numbers are hexadecimal unless a unit is shown. This ledger covers the current M919 adapters. An AMI table value proves a write, not a correct register meaning. Physical DOS boot, floppy operation, HIMEM/EMM386 loading and keyboard input are confirmed on the reported baseline. Those functional results do not independently establish each register meaning or timing margin.

The reported chips are UM8881F, UM8886BF, and UM8663BF. The user's 09/15/1998 AMI host-bridge dump reports PCI revision 04. The southbridge revision remains unmeasured. The stock M919 emulator uses HB4, UM8886AF, and UM8663BF. Follow the user's direction to investigate differences only when an observed problem requires it.

Sources are the [local pinned UMC manual](../../../reference/chipsets/umc/um888x/UMC_chipset_technical_reference_manual_RE.md), the supplied AMI bytes, and local 86Box source at `6c935be21` under `tools/86box/source/`. [SOURCE.md](../../../reference/chipsets/umc/um888x/SOURCE.md) records the upstream commit and original hash. The running executable is 86Box 6.0, build 9001. Source-model claims remain separate from executable observations.

## AMI format and reset evidence

The four retained unique files are 128 KiB and start with `AMIBIOSC10/10/94`. The user removed the identical `9-15-98.rom` duplicate. Raw AMI core dates do not establish release dates. Native main-core bytes at 813A..8143 identify 03/06/1996, 05/06/1996, 10/16/1996 and 09/15/1998. The selected baseline remains `9190506.BIN` and agrees with the user's date.

| Distinct input | Uncompressed normal module base | Startup table, inclusive |
| --- | --- | --- |
| `9190506.BIN` | E770 | FEDE..FF4B |
| `3-6-96.BIN` | E770 | FEDE..FF4B |
| `9191016s.rom` | E770 | FEDE..FF4B |
| `9190914S.ROM` | E7A0 | FEEA..FF57 |

All reset vectors at file 1FFF0 are `EA 5B E0 00 F0`, targeting F000:E05B. The normal lower-ROM entry at E05B is `EA 5B 00 77 FE`; the later normal module uses segment FE7A. The recovery block masks the segment high byte with EF, selecting EE77/EE7A. This is why linear disassembly at the printed far segment is misleading.

The baseline startup loader is at F562..F598 and its XLAT register map starts at F52B. The later loader/map are F592/F55B. Startup table indexes 40..76 map through that table: the first 37 writes target the southbridge; the last 18 target the host bridge. The module header identifies the table bounds. Table values below use the translated register, not the encoded index.

The old recovery block in `9190506.BIN` and `3-6-96.BIN` is byte-identical over 1E000..1FFFF. The newer block in `9191016s.rom` and `9190914S.ROM` is byte-identical over that region. These are two independent recovery implementations, not four.

The baseline directory identifies compressed module 00 at 0030, module 02 at 5342, and module 44 at BB36. Packed/expanded lengths are 21266/28224, 26612/37120, and 8854/13344 bytes. Modules 00 and 02 reconstruct the F000 core at offsets 0000 and 6F00. Module 44 carries the AMIBIOSD resource and a directory destination field of 9000. Special entry 81 remains unresolved. Uncompressed module 03 at E770 supplies the native decompressor.

`shared/tools/ami94.py` runs the embedded decompressor in isolated Unicorn memory, with a 15,000,000-instruction budget per module. Directory/input/output bounds, native return, eight-byte signatures and the reset vector are checked. `python -B m919/tools/test-reference.py --native` also pins every decoded main-core hash and compares cache routines, helper bodies and GDT contents. A 16-bit LGDT loads only 24 base bits. No original per-module checksum was found. The earlier synthetic LH5 wrapper's `Data Error` is not a native decoding failure. ROMINFO/RETRIV execution compatibility remains unproven.

## Cache comparison across releases

The capacity/bank routine is byte-identical over FC7A..FD77 in all three 1996 originals and FCAA..FDA7 in the 1998 original. Its 254-byte SHA-256 is `ed43826bd55dee679ee3809f028a25008a8161c8479a298f18f0694f08b518c7`. Late cache-test starts are 29A0 in the baseline, 296D in March 1996, 297F in October 1996 and 297A in September 1998. After relocation normalization, instructions, PCI helper bodies and referenced GDT contents are identical. The 1998 image removes the full 36-byte CMOS F6-save/HB50-zero exit block, retaining the disabled discovered map. The 1996 exit also waits with CX=5802h between force-hit cleanup and the final map mask. These are discovery-exit differences; normalized late tests remain identical. This is routine-level evidence, not revision 1.5 compatibility.

The user separately reports successful revision 1.5 tests of `9191016s.rom` and `9190914S.ROM`. Their decoded dates are 10/16/1996 and 09/15/1998. This supplies physical boot evidence for the reported board. It does not prove every cache path, timing margin, or bAIos behavior.

The early routine enables HB5A force-hit 40 and programs a temporary large cache map. It writes markers 6 at 200000, 5 at 100000, 4 at 80000, 3 at 40000, 2 at 20000 and 1 at 10000. Reading address 0 classifies the alias. It separately probes bytes at 0 and 4 for bank organization. HB50 readback after discovery does not establish a power-on strap. Jumpers select the physical SRAM organization. Software must discover and program a matching map.

The late test loads ECX but decrements CX at five loops. Isolated execution shows 256 KiB of test writes for capacity codes 1 and 4. The no-cache branch skips a push but reaches a pop in isolated execution. Intent, caller reachability and material physical impact remain unproven. Do not classify these observations as established AMI defects or explanations for fake-cache boards.

The user reports fake-cache boards that announce 256 KiB without SRAM. A fixed synthetic response of 03 fools the single-marker classifier. This demonstrates a weak discriminator, not actual fake-board circuitry. A usable cache must retain opposing writable patterns and consistent independent aliases. Absent, floating and constant-data fixtures must remain off; real writable SRAM must qualify. Firmware reports presence and qualification without a fake-cache category.

AMI uses HB50.40 clear and HB51.01 set for write-through, preserving size/bank bits. Its late read drain starts at 1 MiB and reads the configured cache capacity. Ordinary drains do not establish tag invalidation. [AMD Am5x86 publication 19751, section 4.9 and Table 7](https://www.amd.com/content/dam/amd/en/documents/archived-tech-docs/datasheets/19751.pdf) defines WBINVD write-back/flush and INVD flush-only bus cycles. The pinned UMC manual also observes an L1 INVD effect on L2. Forced-hit test contents must be discarded before ordinary cacheable access. Actual UMC response and timing remain physical checks. The adapter retains the complete native early diagnostic protocol at FB32..FC18: nine low-64-KiB word-read passes, HB5A.80 set/clear, HB5B=55h writes and a final readback gate. The HB5A.80/HB5B meaning remains unresolved; the software fixture proves the transaction sequence without inventing an invalidation effect.

AMI's 65-byte floppy DMA routine is identical in all four unique decoded cores: baseline D8B4, March 1996 D8A6, October 1996 D8A2, and September 1998 D7C0. Its SHA-256 is `f3b5f3bec815bf1999c05b61cf529be50578b32e038c5aa7ca8a90955729e622`. It programs DMA2 mode, count, address and page, then unmasks channel 2. It contains no cache-flush instruction or helper call. The baseline floppy wrapper at CF3E..CFCA calls C31B, which is a plain return. The working Presario floppy path also contains no cache flush.

Keep that shared floppy behavior. The proposed unconditional WBINVD additions caused a native DOS 6.22/EMM386 regression and have no demonstrated hardware need. AMD publication 19751 sections 4.4.1, 4.7 and 4.8 distinguish CPU write-through from write-back and define bus-master snoop copyback and write invalidation. CR0 cache-enable bits alone do not select every cache line's write policy. The cache/DMA proof models both policies and coherent hardware master cycles, with unsnooped negative controls. This is a hardware contract, not a measurement of UMC wiring or a new software flush mechanism. Neither the local manual nor the emulator establishes a DMA-snoop enable bit; SB71.10 is an activity monitor. The HB51.02 polarity remains unresolved and must not be guessed.

## Access and ordering

PCI configuration uses type 1 at CF8/CFC. HB device is 10, SB device is 12, on bus zero. Byte offset selects CFC plus offset modulo four. Ordinary initialization writes full bytes; the early reset path also writes dwords spanning HB 50..5B. Its values force cache off and external ROM reads before changing DRAM geometry.

The current complete core starts at F000:0000. It flushes/disables CPU cache, disables external cache, clears shadow state, applies HB/SB startup tables, starts refresh/A20, and sizes RAM without a RAM stack. It then establishes the stack/state, qualifies SRAM with caches disabled between probes, and initializes AT glue, RTC, Super I/O, PCI and VGA. Keyboard arming precedes the donor settings and visible RAM test. Selected timing application precedes that RAM test. L2 qualification or certificate reuse follows it directly, before peripheral/device discovery. Final operational L2 enable remains after the last Setup gate. Native IDE/FDD, mouse policy, FPU, error gates, late L1/L2 policy, add-in ROMs, summary and FFh precede the saved boot order. The lower E000 image half is padding.

The emulator POST, warm-reset, memory and device fixtures exercise that sequence. They do not measure physical reset defaults or timing margins. Table reset values are emulator values. Physical register meanings remain unmeasured unless a separate observation is stated.

## UM8881F host bridge

AMI pair offsets below refer to `9190506.BIN`. Add 0C for `9190914S.ROM`. All four distinct AMI images have the same HB values. The reset column comes from `src/chipset/umc_hb4.c`, not physical hardware.

| Offset | Runtime values/mask | AMI pair offset/value | Model reset | Manual claim and uncertainty |
| --- | --- | --- | --- | --- |
| 50 | Measured size/banks; requested burst30 and WB40; qualified enable80 | FF28 / 00 | 00 | Native 1998 AMI25EA..25FA and2621..2630 confirm masked burst/mode selection. WT pairs with HB51.01 set; WB clears it. Manual documents four burst sequences. Physical 512 KB WT qualification is confirmed; new timing margins/WB are not. |
| 51 | Selected wait fieldsF0; tag bit01 set for WT/clear for WB; low0E preserved | FF2A / 00 | 00 | Native AMI25FC..2615 and2632..263D confirm waits/tag allocation. CPU-policy bit02 polarity remains unresolved. |
| 52 | 01 initially; both region codes 0..7 and assignment mask 08; selected posted-write80 | FF2C / 01 | 01 | Codes 1..7 mean 2..128 MiB per region; 0 is absent. Lower region is at least the upper size. Bit 08 swaps physical pair assignment. AMI264F..265D confirms posted-write80. The stock model does not implement mapping. |
| 53 | Measured lower/upper population, side and swap fields; selected burst/copybackC0 | FF2E / 00 | 00 | AMI2660..2678 confirms burst/copybackC0. Lower masks 01/02/10, upper masks 04/08/20. The independent DRAM fixture applies the fields; stock 86Box stores them only. Physical socket wiring remains unmeasured. |
| 54 | 00 then 02 through32 KiB VGA, 06 through48 KiB, 0E through64 KiB | FF30 / 00 | 00 | Bit02 selects C0000..C7FFF reads; bit04 selects C8000..CBFFF; bit08 selects CC000..CFFFF. The latter two regions are separate16 KiB chunks. The declared VGA extent survives provider decode disable and is excluded from later ROM scanning. |
| 55 | 40 reset; 00 while copying; C0 final | FF32 / 00 | 40 | Global internal reads/write protection. Switching global reads also exposes F shadow, so copy all F first. |
| 56 | 00 during reset; FF table | FF34 / FF | FF | Memory-hole base; no hole requested. Physical meaning untested. |
| 57 | 00 during reset; 0F table | FF36 / 0F | 0F | Hole control; low nibble meaning incomplete. |
| 58 | 00 during reset; FF table | FF38 / FF | FF | Cacheability relationship observed by manual; stored only in model. |
| 59 | 0F | FF3A / 0F | 0F | Cacheability evidence incomplete. |
| 5A | 00 at reset; diagnostic mask 80 set/clear in the AMI readback protocol; force-hit mask 40 only during SRAM probes, clear before ordinary accesses | FF3C / 00 | 00 | Selected parity10 composes with port61 mask04 and parity initialization. Force-hit/cache/parity controls. AMI explicitly clears mask 40 at FD9C..FDA3; stock 86Box does not model force hit. |
| 5B | 00 reset/table; early diagnostic writes/readback 55 | FF3E / 00 | 2C | Meaning unknown. Model ignores writes and retains 2C. |
| 5C | 00 | FF40 / 00 | 00 | SMRAM base; no SMM runtime provided. |
| 5D | 20 plus selected early-write80/slow-refresh10 | FF42 / 20 | 0F | Manual defines early-write80/slow-refresh10; native AMI26F3..26F9 clears slow refresh. Other bits are preserved. Refresh/SMRAM/cache controls. Bit 20 meaning unresolved. |
| 5E | 00 | FF44 / 00 | 00 | Unknown writable register. |
| 5F | FF | FF46 / FF | FF | Unknown writable register. |
| 60 | 00 | FF48 / 00 | 00 | SMRAM/parity controls. |
| 61 | 02 initially; measured lower 10/upper 20 on PCI revision 04; selected EDO C0 and burst08; preserve other bits | FF4A / 02 | 00 | AMI gates asymmetric trials on PCI revision 04. Other revisions receive no asymmetric writes. This is silicon revision, not the PCB version. Native AMI20EF..20FC confirms the C0 EDO selector; manual defines burst08. Other Cyrix meanings remain unresolved. |

AMI independently disables external-cache controls at FD84..FD8B (HB50 mask C0), FD9C..FDA3 (HB5A mask 40), and FDC0..FDC7 (HB50=00). Its RAM probe at FDD9 uses addresses 90000,190000,390000,790000,F90000,1F90000,3F90000,4090000 and opposing patterns. Candidate maps include HB52/53 values encoded as dwords 00070000,02070000,10070000,12070000,000F0000,020F0000,120F0000. Final commits are at F998..F9AD. Sorting at FA2B..FAD3 remains AMI policy, not a specification for this port.

The runtime measures each physical pair without a RAM stack and sorts the regions. It checks every address line within each interleaved bank and the last usable dword. It compares the first outside region's matching offset against the low anchor. That offset distinguishes an alias from additional RAM. It also checks that the upper region is independent of the lower region. Probes are restored. The independent DRAM fixture applies bank interleaving, side/asymmetric selection, capacity aliases and absent-region behavior to actual assembled I/O and memory accesses. It does not choose a firmware result.

Wide state reaches the actual RAM loop, POST, Setup, diagnostics, and the existing memory interfaces. AH88 and CMOS retain an explicit FC00h ceiling; reported totals and testing can exceed it. Native 8/16/128 MiB guests exercise real boot and presentation. The user separately reports faster physical RAM testing, responsive keyboard control, and working detection/bank layout, without identifying the flashed hash. These results do not prove every physical wiring or timing combination.

## UM8886 southbridge

AMI offsets are baseline offsets; add 0C for the later table. Reset values come from `src/chipset/umc_8886.c`. Values are whole bytes unless a mask is named.

| Offset | Runtime | AMI pair offset/value | Model reset | Manual claim and uncertainty |
| --- | --- | --- | --- | --- |
| 40 | 01 | FEDE / 01 | 01 | DEVSEL/posted writes. |
| 41 | 40 | FEE0 / 40; later 44 | 04 | Parity/parking controls. |
| 42 | 08 | FEE2 / 08 | 08 | Meaning unresolved. |
| 43 | 9A | FEE4 / 9A | 9A | High/low nibble route INTA/B to IRQ9/10. |
| 44 | BC | FEE6 / BC; later 28 | BC | High/low nibble route INTC/D to IRQ11/12. Later AMI routing differs. |
| 45 | 04 | FEE8 / 04; later 85 | 00 | Revision/mouse claims remain uncertain. |
| 46 | 1F | FEEA / 10; later A9 | 10 | Low mask 0F enables four PCI IRQs; high bits arbitration/PM. |
| 47 | 4F | FEEC / 40 | 30 | Low mask 0F selects level IRQs. Mask 40 disables flash writes per manual. Physical flash protection unmeasured. |
| 50 | 00 | FEEE / 00 | 00 | BIOS/video flags, uncertain physical behavior. |
| 51 | 02 | FEF0 / 02 | 02 | RAM-size/bootblock flags. |
| 56 | 00 | FEFA / 00 | 00 | Model uses PCI/3 ISA clock. Physical bus/jumper clock must be measured. |
| 57 | 24; reset OR20, AND3F | FEFC / 20 | 00 | Mask 20 enables E ROM decode; 80/40 control C/D decoding. Mask 04 write-protection meaning is inferred. |
| 70 | 0F | FEFE / 00 | 00 | Green timer/activity control, physical behavior uncertain. |
| 71 | 00 | FF00 / 00 | 00 | Activity monitor. |
| 76 | 00 | FF0A / 00 | 00 | SMI/flash/activity controls, uncertain. |
| A0 | 00 | FF16 / 00 | 00 | PM/SMI mask incomplete. |
| A4 | 01 | FF1E / 01 | 00 | Model uses PCI equal to CPU bus clock. Physical ratio unresolved. |

Baseline recovery instructions `B8 47 40` at 1ECC7 and `B8 57 20` at 1ECD6 establish early flash/decode writes. New recovery equivalents are at 1ED29/1ED38. Later normal AMI also changes unused SB55 from 00 to CB. Differences do not by themselves establish PCB-revision policy.

The four decoded native AMI main POST tables at9998/99A8/99B8 map slots0C/0D/0E to pin links ABCD/DABC/CABD. These offsets belong to main POST, not module44. Runtime writes each endpoint's IRQ at3C from its pin at3D and the explicit AMI table. SB43 routes A/B in its high/low nibbles; SB44 routes C/D. All four values come from the configured IRQ variables. Routing preserves unowned SB46/47 bits and both ELCR bytes. Defaults9..12 add mask1E to4D1 without clearing other level sources. The independent AMI-wired endpoint fixture observes assertion, PIC delivery, EOI, deassertion and reassertion. Stock86Box slot0E uses CDAB and differs at pins B/C/D. Neither model establishes the physical board's wiring.

## UM8663BF Super I/O

Access is AA unlock to port 108, index at 108, data at 109, and 55 lock at 108. The same index/data window also reaches the AF IDE controller under its different unlock sequence.

| Register | Runtime | Model reset | AMI evidence | Claim and uncertainty |
| --- | --- | --- | --- | --- |
| C0 | 0F | 0F | New recovery table 1ECC3 gives 0E; fallback at 1ECF8 writes 0F | Low bits enable FDC, COM1, COM2, LPT; SIO IDE coupling off. Reads randomize upper E0 in model. |
| C1 | 8F | 1F | New recovery table 1ECC5 gives 9F | Primary FDC 3F0, COM1 3F8, COM2 2F8, SPP LPT 378. Runtime differs deliberately from recovery LPT selection. |

The new recovery table continues C2=81,C3=08,C4=00. Runtime reads C2, sets mask81 and clears mask20, preserving other bits. The manual describes those selected bits as awake/FDC initialization/disable. Stock86Box stores C2 without applying its wake behavior. The independent peripheral fixture gates actual FDC commands/DMA by awake and enable controls. Neither model establishes their physical effects. Runtime does not copy the unexplained C3/C4 values. The table loader is1ECCD..1ECFE, called at1E315; writer1ECFF..1ED24 shows unlock/lock order. Decoded baseline normal startup atBCB1..BCD9/C0E6 writes C0/C1 as whole-register seeds. Later values differ. Incoming C0/C1 preservation is not the startup contract. Keep configured0F/8F seeds, then preserve C0 upper nibble and C1 mask30 during saved routing.

The FDC VERSION result selects enhanced CONFIGURE/PERPENDICULAR commands only for90. An80 legacy result is drained and uses standard SPECIFY. The physical floppy worked after this correction; the exact failing enhanced command was not captured on silicon.

The configured-floppy tests check each drive's actual recalibration, disabled positions, and configured-but-absent failure. The independent SIO fixture also executes installed INT14 transmit/receive, INT17 strobes and IRQ6/DMA2 transfers. Empty, one-device, duplicate-prefix and later-standard-endpoint cases check complete BDA order/count and transactions. These results establish firmware order against external models, not physical UART/printer wiring.

## IDE controller configuration

AF access is 4A,6C unlock at 108; index/data at 108/109; 34 lock at 108. `src/disk/hdc_ide_um8673f.c` enables primary/secondary from B0. Its lock checks the previous index, which does not exactly implement the manual's immediate-lock description.

| AF register | Runtime | Model reset | Meaning and evidence limit |
| --- | --- | --- | --- |
| B0 | C0 | C0 | Masks 80/40 enable primary/secondary. |
| B2/B3 | 44 each | 00 | Manual PIO0 timing policy; model stores only. |
| B4/B5/B6/B7/B8 | CC each | 00 | Manual PIO0 timing policy; model stores only. |

BF PCI IDE is discovered by class0101 and IDs673A1060/673B1060. The native AMI module44 method atB84A..B887 derives `(PI & 0A) >> 1` and clears only those switchable mode bits. The runtime uses that method and reads PI back before assigning legacy ownership. It writes dwordsFF30C900 at40 andBBBB6666 at44 only after both channels read as compatible. Native, mixed, ignored mode writes and rejected I/O BARs retain an unusable hardware state. Discovery issues no AF-window writes or legacy task-file probes for those states. The saved Enabled request remains separate from usability.

| BF register | Runtime | Source-model reset | Meaning and evidence limit |
| --- | --- | --- | --- |
| 40 | 00 | 00 | FIFO disabled. |
| 41 | C9 | C0 | Masks 80/40 enable channels; lower nibble uncertain. |
| 42 | 30 | 00 | Manual's HB-dependent setup; silicon unverified. |
| 43 | FF | 00 | PIO0 timing A for all four positions. |
| 44/45 | 66 each | 00 | PIO0 timing B. |
| 46/47 | BB each | 00 | PIO0 timing C. |
| 09 | `PI & ~((PI & 0A) >> 1)`, then readback | 8F | Stock source model ignores PI writes. Independent fixed/switchable/mixed/ignored-write cases continue through actual ATA discovery and installed INT19. Physical mode conversion remains unmeasured. |

The stock M919 path exercises AF and legacy taskfiles. Physical DOS boot uses the reported onboard PCI controller. That result establishes baseline operation, not the meaning or margin of each BF timing field. Native module44 supplies the BF PI algorithm above. Other manual-derived timing meanings remain hypotheses. Saved IDE Enabled/Disabled contrasts use real Setup keys, save, FE reset and reload, then actual ATA/BF application and the same installed INT19 boot consumer. They hold UART/LPT/FDC policy constant and execute a later UART transaction.

The complete-core harness checks all four first-present positions, the two-record logical mapping, mixed ATAPI/ATA discovery, BPB geometry, multisector CHS, EDD read/write restoration, actual DOS6.22 and secondary-channel El Torito. Older partial-shell tests are not the maintained proof. These checks do not establish electrical PIO margins or four simultaneous logical BIOS devices.

## Standard PC and PCI accesses

These accesses are architecture or endpoint operations, not additional UMC register interpretations:

- CR0 masks60000000 disable CPU cache during bring-up; WBINVD flushes transitions and warm reset. Port92 enables A20 for RAM sizing, then clears its reset/A20 bits after keyboard initialization. The 8042 output gate remains enabled until its owner changes it. INT15 memory moves save/restore that gate through the board adapter. Physical HIMEM/EMM386 loading and actual alias enable/disable tests confirm baseline ownership.
- PIT channel 1 uses command 54 at port 43 and reload 12 at 41. AMI normal instructions are F5AA..F5B6; recovery instructions are 1E14E..1E15A. IRQ0 uses channel 0 and shared PIC/PIT initialization.
- AT DMA reset/mode/mask uses ports0D,DA,D6,D4; port61 disables speaker and masks parity/IOCHK through low mask0F. Native floppy services use IRQ6/DMA2. ATA services use PIO.
- PIC 20/21,A0/A1, PIT 40..43, KBC 60/64, RTC 70/71, ATA 1F0..1F7/3F6 and 170..177/376, FDC 3F2/3F4/3F5/3F7 retain their standard register contracts.
- The [IBM AT Technical Reference6280070, September1985](https://www.minuszerodegrees.net/manuals/IBM_5170_Technical_Reference_6280070_SEP85.pdf), System Board1-66, defines the configuration checksum over CMOS10..2D, high byte2E/low byte2F. Its BIOS Test.12 listing at offsets0704/0706 selects10..2E exclusive (with NMI mask80). The runtime sums that range. Baseline fixture seeds have only floppy byte10 nonzero. A late-byte contrast adds07 at2D with stored checksum0047 for floppy type40, disproving a truncated sum. Clock/century fields are outside the range.
- Root `shared/src/pc/pci.inc` owns endpoint configuration, enumeration, resource allocation and installed PCI BIOS services. BARs10..27 are sized with decode off. Valid 32-bit I/O/MMIO and paired64-bit inputs must have contiguous masks, legal partners, safe arithmetic and configured pool bounds. Rejected resources disable their whole decode category. Command writes preserve unrelated bits and write-one-to-clear status; bus mastering stays off. Board VGA/BF special enables respect rejected categories. Expansion ROM BAR30 maps the first VGA ROM atC0000. Other endpoint ROM BARs are disabled. [PCI BIOS2.1](https://www-online.kek.jp/~yasu/Parallel-CAMAC/bios21spec.pdf) owns public register/error contracts; [PCI IDE1.0](https://www.isdaman.com/alsos/hardware/hdc/pciide.pdf) owns mode-bit semantics.
- The Cirrus GD5446 input is 32768 bytes with a valid ROM checksum. Its code at C000:31D4 reads expansion-ROM BAR 30 and clears enable bit 01 through PCI BIOS B10B at 31E2. Copying C shadow first allows that real ROM entry to return. The whole F reset segment is also copied because HB55 switches global reads.

## Remaining measurements and correction proposals

The user confirms no PS/2 connector, only serial mouse support. SB40=01 and SB45=04 leave the manual's reported PS/2 pin-selection bits clear. The adapter does not enable guessed pin bits. Its configurable AUX capability is false, so late mouse initialization and INT15/C2 cannot issue unsupported operations. The user confirmed that this restored keyboard input. The precise controller-level failure mechanism remains unmeasured; IRQ counts did not identify physical keystrokes.

Measure physical bank organization and aliasing, HB/SB revision IDs, ISA/PCI clocks and jumpers, ROM decode/shadow behavior, flash-write protection, graphics identity, and slot interrupt wiring. Retain the accepted ROM until the cache candidate passes its checks. The reported SRAM now passes bAIos qualification at 512 KB WT after U23 and U14 replacement. Post-repair independent cache-speed and DMA measurements remain unobserved.

No upstream correction is established. Candidate areas for a reproducer are AF lock ordering, the HB5B status/write discrepancy, missing emulator DRAM mapping, and inferred SB57 protection. Determine whether each difference is a manual omission, an emulator limit, or an AMI defect before proposing a change. Public submission requires a user request.

## Physical cache diagnosis

The reported socket labels put Bank 0 (U20-U23) at the outside edge, Bank 1 at U11-U14, and TAG at U19. A 55AA55AA read became 57AA55AA while uncached RAM retained 55AA55AA. The differing byte is byte 3, D24-D31. Replacing U23 moved the first reported failure from Bank 0 byte 3 to Bank 1 byte 3 without changing Bank 1. Replacing U14 then restored 512 KB WT qualification. This confirms the two byte-3 sockets; other byte/socket ordering remains unknown. Tag, timing and socket faults can also cause data mismatches, so localization remains a suspect lane rather than an unconditional chip verdict.

The user's 09/15/1998 AMI snapshots show HB50/HB51=3C/F5 in manual mode and 0C/55 in auto mode. Both retain HB5A=0D and HB61=20. Those DOS snapshots do not by themselves prove the earlier qualification branch or effective external cache. CTCM's subsequent 8-KiB L1/16-KiB L2 classification and its dirty-tag detectability notice do not establish a working 512-KiB external cache. No runtime timing changes were made from these snapshots.
