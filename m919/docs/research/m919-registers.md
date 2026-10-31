# M919 register evidence

All numbers are hexadecimal unless a unit is shown. This ledger includes historical M919 adapters and the expanded reference study below. Earlier adapter descriptions are retained evidence, not a description of the replacement cache implementation. An AMI table value proves a write, not a correct register meaning. Earlier physical DOS boot, floppy operation, HIMEM/EMM386 loading and keyboard input do not establish the replacement implementation's cache stability.

## Tuning omissions in candidate 0.5.3

This report originally compared candidate0.5.3 with the four original M919 AMI releases and the retained AMI, Award and Phoenix research. It covers tuning and device configuration. It does not reproduce every vendor password, keyboard or POST presentation choice.

On 2026-10-30, the user confirmed that host-to-PCI posting, burst writes and the post-write buffer are present. The user accepts the measured PCI performance as consistent with other users' results. This is the physical result for the reported configuration. It does not qualify every tuning combination. The 0.5.3 host-header change produced no reported performance gain. The0.6.0 follow-up completes the four-device state and service work described below; its physical qualification remains separate.

The current menus expose45 chipset controls. Shared Setup separately supplies Fast Boot, boot order, IDE block mode, translation and EDD controls. M919 also exposes32-bit ATA transfers and individual PIO mode limits. The items below remain absent, automatic, incomplete or excluded. A missing control is not necessarily unsafe or unsupported.

### Features with implementation work remaining

| Feature | Current behavior | Reason and evidence |
| --- | --- | --- |
| Faster IDE PIO modes | Version0.9.2 offers Auto/PIO0/PIO1/PIO2/PIO3/PIO4 limits and reports the accepted result. Auto selects the fastest permitted device mode. | The enabled, usable673A PCI IDE function is required. No exact sibling revision or33MHz setting restricts its supported modes. Valid device IORDY capability, cycle time and accepted completion permit modes3/4. The original board recipe owns all seven fields through4Fh. Physical position order is43h shifts6/4/2/0, with masters in the high nibble and secondary registers at+1. PIO4 is physically confirmed on the revision3.4 test unit. Margins at every supported clock remain unmeasured. |
| Game-port enable | Removed in0.9.0 because this board has no game port. The decoder is forced off. | The old C_CHIP22.0 bit remains opaque packed compatibility data. It does not enable C0.20. ECP DMA selection retains C_CHIP22.1 and its existing meaning. |
| Parallel-port DMA channel | Implemented in0.8.0, moved to Devices after Parallel Port Mode in0.9.4, with sorted choices1/3 and default3. The five-field Devices page retains this choice while LPT is disabled or outside ECP mode. | Original option52, BD0E..BD4B, gates C3.40 on enabled ECP. Set selects DMA1; clear selects DMA3. C_CHIP22.1 retains the choice while inactive. Other C3 bits and all C4 remain unchanged. No new ECP DMA transfer engine or physical qualification is claimed. |
| Complete parity configuration | Implemented in0.8.0 using the existing Memory Parity selector. Reporting stays Off until initialization completes. | Original B3AF..B3E7 coordinates HB5A.10, HB05.01 and inverse IBC41.40 in that order. Byte writes preserve PCI status. Full, Fast Boot and Esc seed required memory before enabling these controls and finally unmasking parity at port61; IOCHK/speaker state is preserved. Physical parity memory remains unqualified. |
| Four simultaneous IDE device records | Implemented in0.6.0 through shared discovery, ATA-only numbering, IRQ14/15, channel reset, CD boot, Setup and POST. | All four physical records have independent full persistent policies. The saved format remains unchanged, and version0.9.7 binds every policy to its fixed physical connector. The first/second detection-order rebinding is removed. Runtime identity and policy ordinal are separate. Physical four-device operation still needs bench confirmation. |
| System BIOS cacheability | F-segment shadowing exists. A System BIOS Cacheable switch does not. | Award binds HB55.20 to this feature. Older AMI UD-486-GRN uses HB55.30 for Main BIOS Cacheable. The manual also associates HB58/HB59 with the cacheable extent. These observations are not a completed, qualified implementation for the current shadow owner. This remains unfinished work rather than a finding that the feature has no value. |
| Regional ROM cacheability | C8000, D0000, D8000 and E0000 cacheability switches do not exist. Six optional C8000 through DFFFF shadow controls do exist. | MGV994 descriptors bind these cacheability controls to HB55 masks02,04,08,10. The full saved-value path, electrical ranges and silicon applicability remain unclosed. Shadowing and cacheability are different functions. Video BIOS Cacheable is already implemented. |

### Vendor selectors replaced by automatic or fixed policy

| Vendor control | Current replacement | Why there is no matching switch |
| --- | --- | --- |
| Auto Configuration Function | Individual DRAM waits, cache burst, PCI ratio, ISA divider and keyboard-clock controls. | The original automatic table combines measured CPU classes with timing and clock fields. The user reports its unwanted PCI20 MHz result at a40 MHz bus. Importing that table would defeat the explicit PCI-ratio owner. The current firmware does not claim automatic optimal timing. |
| L1 Cache Mode, WT/WB | Internal CPU Cache remains selectable. CPU recognition supplies the qualified AMD modelE/modelF host protocol choice. | A generic WT/WB switch needs coordinated CPU and chipset support. The original AMI path has CPU-descriptor conditions. The port does not offer a switch that only changes HB51.02 or assumes that enabling CR0 cache selects the requested write policy. Wider selectable L1 policy remains unfinished. |
| Alternate tag bit / dirty-bit configuration | The cache engine owns tag format, measured geometry and the supported cacheable extent. | Award labels include Alt Bit in Tag SRAM and Ext-Cache with Dirty Bit. Exposing their raw HB51.01 selector independently would change the cache engine's address/tag contract. The current WT/WB sequence is preserved. |
| Cache size and bank population | Runtime qualification establishes the installed SRAM organization. | These are detected hardware properties. A bench configuration is not a permanent board value. |
| Video C0000 shadow disable | The selected VGA provider determines the required shadow extent. | Its retained ROM contents must survive later ROM discovery and provider-decode changes. There is no independent off switch for a shadow required by the active provider. |
| Explicit disable for optional ROM shadows | The six extra regions offer Auto/Enabled. | Auto retains copies required by detected providers. There is no override that forbids a provider's automatic shadow. Enabled adds a copy. |
| VGA residence on PCI or VL bus | The selected provider automatically controls the normal VGA bus tuple. | The actual PCI provider selects HB51.04, IBC50.80 and IBC56.60. This policy was added in0.5.2 and improved physical performance. It is not a missing buffer switch. |
| Host PCI cache-line size and latency | The qualified UM8881 host receives cache-line04 and latency40 automatically. | These are normal header policy, not exposed tuning sliders. They were added in0.5.3. Endpoint bus mastering is not enabled indiscriminately. |
| Programming Auto/Manual and IDE-card slot/location selectors | Super I/O policy and positive PCI IDE discovery select the usable controller. | Original options4C and56 through58 offer manual policy, slot and interrupt-pin overrides. The port does not reproduce those overrides. Its current IDE path requires a supported, resource-qualified compatibility controller. |
| Secondary IDE enable and drive-count overrides | The qualified controller enables both legacy channels and probes every physical position. | Original options59 and5F allow manual secondary-channel/count policy. The current top-level controller enable and detected records replace part of this behavior. Four-record policy is implemented; independent channel-disable switches remain absent. |
| NCR SCSI slot selector | Generic option-ROM discovery can run a supplied adapter ROM. | Original option62 selects the slot for the embedded NCR ROM. bAIos does not bundle that vendor ROM or reproduce its slot selector. |

### Deferred or insufficiently established controls

| Feature or source label | Disposition | Reason |
| --- | --- | --- |
| Chipset power management | Deferred by user direction. | Doze, standby, suspend, green timers, video power control, SMI/SMRAM and activity/wake monitors need a complete hardware power-management owner. Shared APM remains present. APM availability does not claim chipset suspend support. |
| Keyboard emulation | Not imported from Award's IBC57.08 descriptor. | The source label does not establish a compatible implementation for this board. No required emulation runtime is implemented. Ordinary keyboard handling and keyboard-clock selection already exist. |
| Memory hole | No user-selectable hole. Startup clears the documented hole-enable bit. | The pinned manual describes HB56/HB57 fields. The current RAM map and public memory services do not implement a reserved-hole policy and its dependent cache handling. This was not needed by the reported hardware. |
| Burst Copy-Back auxiliary bit | HB53.40 DRAM Burst Writes is exposed. The older Award companion HB60.10 is not added. | Eight Award cores associate the two fields through visible and hidden descriptors. The full saved-policy path is not closed, and one core gives them different defaults. The evidence does not establish a mandatory paired write on M919. |
| PCI Master Retry Timer | No selector for the older Phoenix Disabled/16/32/64 PCICLK choices. | The retained source binds the label at EE71:142A to IBC41.18 through selector F000:4CDB. Numeric encoding and applicability to this UM8886BF remain unqualified. |
| DMA Page Register Alien | No selector for this exact older Phoenix label. | The source binds EE71:1412 through selector F000:4CCB to IBC41.80. The electrical meaning and M919 applicability remain unresolved. |
| Older Phoenix IRQ-trigger labels | Excluded pending chipset/revision qualification. | That source associates host fields with meanings that conflict with the later DRAM register map. Its bridge-address interpreter was checked, so this cannot be dismissed as a swapped-address parser error. The names are source-specific evidence, not established M919 controls. |
| Additional VLB timing names | No guessed level/edge or retry control added. | The four original AMI Setup modules have no separate VLB tuning group. The recovered Edge/Level option belongs to PCI IDE IRQ triggering and is implemented. Local Device Sampling, DRAM Resource Lock and Device Number Mapping are already exposed. Other source labels still need a qualified hardware binding. |
| CAS-before-RAS or additional refresh modes | No additional selector. Normal/Slow refresh is implemented. | The retained evidence does not establish another usable selector and encoding for this board. A feature name from another chipset is not a register binding. |
| Additional Cyrix tuning | No generic collection of CPU speed switches. | The port implements positively guarded Cyrix Linear Burst and AMI load/store tuning. No further source-qualified CPU/chipset sequence is established by the retained tuning inventory. This does not mean that Cyrix has no other features. |
| IDE FIFO and bus-master DMA | Disabled in the current BF controller path. | The pinned manual describes a60-byte FIFO with direction, drain and completion management. It requires a specialized transfer/IRQ owner. BF bus mastering also lacks scatter/gather and has alignment constraints. Adding a flag to the PIO driver would not implement these transfers. |
| PCI IRQ6 | Not offered for PCI routing, even though an original Setup descriptor names it. | The original board routing mask DEB8 excludes IRQ6. The current routing owner retains that positive mask and also reserves active ISA-device interrupts. A menu descriptor alone does not establish that this board can route a PCI link there. |
| PS/2 mouse and AUX initialization | Intentionally unavailable. | The user reports no connector and confirmed that AUX initialization locks this board. Serial mouse operation remains available. |
| Other-board unknown bits and transients | No raw register editor or guessed performance switches. | Daewoo host76/77/79, conflicting Phoenix host61 meanings, IBC A3.20 pulses and unresolved low-level fields lack a complete board-qualified contract. Their observed writes remain research evidence. |

### Follow-up priority and evidence limits

Shared PIO0–4, the ECP selector and coordinated parity controls are implemented. The nonexistent game port is removed. Generic hosts require working IORDY, and M919 retains controller identity/function/usability checks; its former revision0D and33MHz vetoes are removed. System and regional ROM caching remain blocked by the HB55.20 shadow/write-protection prerequisite and conflicting HB58/59 range encodings: the manual gives0F/00, while MGV994 givesFF/0F. Current mandatory shadows finish with HB55.C0 protection. Power management remains deferred. The user accepts PCI throughput, so the current results do not justify further speculative PCI performance changes.

The current source owners are `chipset-data.inc`, `timing.inc`, `chipset.inc`, `cyrix.inc`, `rom-tuning.inc`, `pci.inc`, `pci-tuning.inc`, `sio-core.inc`, `parity.inc` and `ata-core.inc` under `src/hardware/`. Shared IDE policy remains in `shared/src/firmware/ide.inc`. Generated vendor decodes remain private under the research directory linked below.

Outside throughput tuning, the original standalone typematic-rate, memory-test tick sound, DEL-message display, extended BIOS RAM-area placement, numeric-processor-test and password-policy switches lack independent equivalents. Shared Fast Boot covers the RAM-test policy. Num Lock, boot order, error-halt policy and floppy swapping already have shared controls. Award's Monitor VL-Bus Card is a power-management activity monitor, not an additional VLB timing control.

This report checks source and retained research. It runs no new firmware tests, native correctness review or hardware measurements. It does not claim complete semantic resolution of every decoded ROM byte. Older sections below retain historical findings. The current report supersedes their statements that implemented controls such as PCI lock method, Cyrix linear burst or the VGA bus tuple are still entirely unbound.

## Expanded reference study and upstream proposals

The 2026-10-29 collection contains 29 distinct physical ROM images. Full raw-byte listings cover each image. Compressed Award, AMI and UMC-era Phoenix modules are extracted before their code and Setup resources are interpreted. The supplied modern coreboot image is a separate source lineage. Shared Award code does not count as independent hardware confirmation.

The generated [corpus inventory](../../build/research/other-roms/expanded-inventory.json) records each source size, SHA-256 and compression signature. The retained [research directory](../../build/research/expanded-roms/) contains extraction scripts, decoded components, full linear listings, Setup bindings, static paths and source excerpts. A linear listing covers bytes. It does not establish that data is executable or that every indirect call is resolved. The [upstream annotation proposal](../../build/research/expanded-roms/upstream-proposal.diff) applies cleanly to the pinned manual. It is not applied or submitted.

The [pinned reverse-engineered manual](../../../reference/chipsets/umc/um888x/UMC_chipset_technical_reference_manual_RE.md) has SHA-256 `cda96be6a3848a84a7bd843e7971d18e39c92495ea1df0ecf66cc9e8a28c2e12`. It remains unchanged. Findings below are proposed annotations for upstream review. A firmware label and a verified register write establish software intent. Electrical behavior and silicon coverage require separate evidence.

### Coverage and reproducibility

- Award: 21 distinct main cores contain 3,482 decoded Setup records, including hidden rows, full record bytes, CMOS masks, defaults and choice pointers. Fourteen main cores are expanded from LH5 members. Seven are uncompressed. Every extracted member passes its LHA header checksum, declared length and CRC16. Shared option-ROM payloads are identified by hash. See the [extraction manifest](../../build/research/expanded-roms/award/manifest.json), [Setup bindings](../../build/research/expanded-roms/award-legacy/register-bindings.json) and [interpreter evidence](../../build/research/expanded-roms/award-legacy/findings.md).
- AMI: three reference images have decoded POST, runtime, Setup and embedded option-ROM components. The images' native decompressors run with bounded input, output and instruction counts. The older `UD 486 GRN.rom` uses a different native entry. Special directory entry81 points to upper-bank Setup resources in the two 10/10/94 images. See the [native manifest](../../build/research/expanded-roms/ami/manifest.json) and [normal register bindings](../../build/research/expanded-roms/ami/register-bindings.json).
- Phoenix: all four inputs have complete raw listings and native expansion of 12 compressed modules in total, including Setup and the resident prefixes. ROM reads and shadow writes remain separate during expansion. The merged images confirm that the chosen cache engine and named late prehandlers remain byte-identical. See the [native expansion manifest](../../build/research/expanded-roms/phoenix/expanded-manifest.json), [runtime byte binding](../../build/research/expanded-roms/phoenix/merged-shadow-binding.json) and [late POST operation paths](../../build/research/expanded-roms/phoenix/late-normal-operations.json).
- Modern image: `BIOS.bin` contains coreboot CBFS. Its own master header supplies file alignment. Bounded CBFS extraction recovers romstage, ramstage, postcar, payload, bootblock and ESCD. LZMA expands ramstage and the SeaBIOS payload. The [manifest](../../build/research/expanded-roms/modern/manifest.json) distinguishes stored and expanded bytes. Mixed 16/32-bit firmware retains separate decoding views.

The Daewoo `41054505.ROM` and `4105G.ROM` access host offsets76/77/79. This conflicts with the manual's unimplemented63-FF range. Their chipset identity remains unqualified, so their settings are excluded from the common UM8881 recipe. The accompanying COVER/R9FULCOM documents describe a Rhino9 Pentium compatibility test. They are not UMC register documentation.

The older Phoenix4v-04 source also needs a register-meaning qualification. Its actual Setup references call HB61 fields IRQ trigger controls. Native execution of its original table interpreter confirms host accesses at800080xx and IBC accesses at800090xx. This is not a swapped-bridge decoding error. The IRQ labels conflict with the later manual's DRAM definitions. Keep these meanings specific to that source ROM until chipset and revision applicability is established. They are not included in the upstream naming proposal.

Run retained scripts with `python -B`. Generated disassemblies and decoded vendor payloads stay in private research output. Upstream proposals use source identities, small instruction excerpts, register mappings and reproducible paths. No upstream submission is authorized by this research record.

### HB5A normal state and turbo controls

The chosen `8810AIO.32J` Phoenix reference initializes HB5A to04. Its normal cold POST record at F000:52BC calls prehandler2960 before function07CB. That prehandler unconditionally applies `HB5A |= 09` at29D1. The final value is0D, not the early table's04. The exact instruction bytes are `B0 5A E8 46 73 80 CC 09 E8 43 73`. The normal prehandler remains outside the expanded resident prefix.

The other Phoenix4v-04 image initializes00 and applies the same unconditional09 overlay at58A5. Therefore0D is a chosen-reference final state, not a universal fixed value for every board. Earlier bAIos comparison stopped at the initial table and omitted this final overlay. The replacement adapter now retains the chosen reference's0D during cold initialization and timing reapplication. Physical Quake stability remains unconfirmed.

`UD 486 GRN.rom` supplies named AMI bindings:

| Field | Setup meaning | Native evidence | Proposed manual annotation |
| --- | --- | --- | --- |
| HB5A.04 | DeTurbo Speed | Option33, descriptor022F, CMOS43.08, title atSetup0A0E, normal22F2-230A | Firmware selects0 for1/6 and1 for1/3. This is a deturbo ratio selector in this image. |
| HB5A.01 | Turbo Switch Function | Option12, descriptor013A, CMOS2D.01, normal2318-232F | Firmware enables or disables the turbo-switch function. Board pin behavior is not measured. |
| HB5A.20 | PCI Parity Check | Option31, descriptor0223, CMOS43.02, normal1D67-1D7F | Firmware labels this PCI parity checking. This is separate from HB5A.10 DRAM parity. |

The old AMI option reader uses defaults when CMOS is invalid. Executing that reader establishes default turbo-switch enabled, deturbo1/3, PCI parity enabled and DRAM parity disabled. Thus the low nibble0D has independent AMI corroboration. This does not name HB5A.08 electrically or authorize enabling PCI parity on every board.

Source `UD 486 GRN.rom` SHA-256 is `824b16755b7616c149e71147088bbae33f01fd0b0e97ce7b749bf36b7f023ea3`. Source `8810AIO.32J` SHA-256 is `7ddabc826f82e295086fe04e2f462145f20d8c51911864a77c2c74aaf079499e`.

### HB62 device mapping and linear burst

Decoded `03C8881I.ROM` joins normal POST consumers to actual Setup strings:

| Field | Option / descriptor | CMOS | Setup label and choices |
| --- | --- | --- | --- |
| HB62.01 | 31 / 0258 | 44.20 | Device Number Mapping Option, Disabled/Enabled. Title atSetup0A64. |
| HB62.02 | 32 / 0260 | 44.04 | Linear Burst for Cx5x86, Disabled/Enabled. Title atSetup0A81. |

The normal code at2020-2054 applies these fields with the existing revision and CPU guards. This improves the manual's description of62.01 as an early revision-E write. The label alone does not establish the exact device-number translation. Keep62.01 separate from cache timing. Do not enable62.02 on an AMD CPU as a generic speed setting.

The newer `am8887.bin` sets62.01 only on its valid-CMOS, host-revision04 branch. It separately sets61.04 on a late revision04 path. The late61.04 operation is independent of the EDO type and read-speed fields. Neither observation supplies a universal board setting or a name for61.04. A valid-CMOS guard is firmware policy, not evidence that a checksum controls the hardware function.

Source `03C8881I.ROM` SHA-256 is `32ba40b699da1e4b436c202b02e6c9b21ceb87746b648ab0fd55ef8febe33d33`. Source `am8887.bin` SHA-256 is `85ee46905f272eb4f12ed81a6058db98edf0ce03c1d8f889dd01e384a1ae6a08`.

### Additional shadow-region cacheability labels

MGV994's visible Setup descriptors attach four previously unnamed HB55 fields to ROM regions:

| Setup row | HB55 mask | Label | CMOS |
| --- | --- | --- | --- |
| 62EC | 10 | E0000H BIOS Cacheable | 38.80 |
| 6305 | 08 | D8000H BIOS Cacheable | 38.40 |
| 631E | 04 | D0000H BIOS Cacheable | 38.20 |
| 6337 | 02 | C8000H BIOS Cacheable | 38.10 |

Each row has hardware selector8055, flags2002 and default0. Existing system and video controls remain55.20 and55.01. The common early interpreter writes these defaults. Complete saved-value application for2000-class rows is not closed. Proposed upstream text must state that these are early Award label associations with unmeasured electrical range and silicon applicability.

Source `MGV994.BIN` SHA-256 is `2c53ebb7cfdd6ad3c6b71cdc0ec77d860805ee96ecb35fcaa79dac0de245e17c`.

### Burst copy-back uses hidden descriptors

Eight older Award cores pair a visible HB60.10 descriptor with a hidden HB53.40 descriptor. Both select CMOS38.02 and display Burst Copy-Back Option. The generic interpreter establishes each register selector and hardware mask. In1433 the visible row is56E2 and its hidden partner is56FB. Full record bytes are in the Award bindings.

This is a software association for the manual's unnamed60.10. It does not prove that60.10 electrically enables burst copy-back. Saved-value application of the entire chipset group is not fully closed. In `ch-880crev1.bin`, the visible default sets60.10 while the hidden default clears53.40. Newer cores expose53.40 directly. Therefore these records do not justify a mandatory paired write or a new M919 tuning option.

### Other final-state and parity observations

The chosen Phoenix POST9C prehandler unconditionally setsHB51.04. A second Phoenix image makes that operation conditional. All four original M919 ROMs initialize that bit clear, and their audited normal owners preserve it. The existing PCI/VLB write-path interpretation remains tentative. A register value from another board is not sufficient to change M919's bus policy.

Phoenix POST66 derives IBC50 from the actual HB54 shadow-region map. It maps E,C0,C8,CC,D0,D4,D8,DC to IBC bits0,7,6,5,4,3,2,1. It also setsIBC51.01. Final POSTC0 updates detected RAM-size bits while preserving that low bit. This establishes a firmware shadow-map record. It does not establish a hardware coherence prerequisite. The meaning of the adjacent IBC A3.20 pulse remains unresolved.

Original M919 normal parity code coordinates HB5A.10, HB05.01 and inverseIBC41.40, in that order. Version0.8.0 completes that ordered parity tuple. The earlier missing bridge fields were a policy gap, not a demonstrated cause of L2-sensitive corruption. The original M919 CPU table independently corroborates the replacement's AMD modelE/modelF HB51.02 choices. Its cache routines are excluded from the replacement implementation.

Decoded AMI Setup also names HB60.08 as the LDEV sampling point. The traced choices are0 for2T2 and1 for1T2. This is another proposed annotation for an unnamed manual field. The exact option, CMOS mapping, source instructions and Setup strings are retained in the AMI register bindings. The physical signal timing remains unmeasured.

The remaining unknowns include HB5D.20's electrical purpose, HB61.04, IBC41.02, complete auto-configuration and saved-value paths, unqualified Daewoo chipset identity, and physical timing margins. No generated listing, normal-state correction or emulator model establishes stable Quake operation.

The revision1.5 reported chips are UM8881F, UM8886BF and UM8663BF. The revision3.4 test unit instead has a reported UM8670F; the user has also seen UM8663 on other3.4 boards. The user's 09/15/1998 AMI host-bridge dump reports PCI revision 04. On the revision3.4 test unit, the read-only PIOSTATE snapshot reports IDE function1 revision10h and sibling function0 revision0Eh. The stock M919 emulator uses HB4, UM8886AF, and UM8663BF. Follow the user's direction to investigate differences only when an observed problem requires it.

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

The new recovery table continues C2=81,C3=08,C4=00. Runtime reads C2, sets mask81 and clears mask20, preserving other bits. The manual describes bit80 as probable sleep/wake control, bit20 as FDC disable and bit01 as an initialization value with unknown purpose. Both startup and late wake establish bit01, including from cold C2=7Eh; it is not modeled as an electrically proven enable signal. Stock86Box stores C2 without applying its wake behavior. The independent peripheral fixture gates actual FDC commands/DMA by awake and enable controls. Neither model establishes their physical effects. Runtime does not copy the unexplained C3/C4 values. The table loader is1ECCD..1ECFE, called at1E315; writer1ECFF..1ED24 shows unlock/lock order. Decoded baseline normal startup atBCB1..BCD9/C0E6 writes C0/C1 as whole-register seeds. Later values differ. Incoming C0/C1 preservation is not the startup contract. Keep configured0F/8F seeds, then preserve C0 upper nibble and C1 mask30 during saved routing.

The FDC VERSION result selects enhanced CONFIGURE/PERPENDICULAR commands only for90. An80 legacy result is drained and uses standard SPECIFY. The physical floppy worked after this correction; the exact failing enhanced command was not captured on silicon.

The configured-floppy tests check each drive's actual recalibration, disabled positions, and configured-but-absent failure. The independent SIO fixture also executes installed INT14 transmit/receive, INT17 strobes and IRQ6/DMA2 transfers. Empty, one-device, duplicate-prefix and later-standard-endpoint cases check complete BDA order/count and transactions. These results establish firmware order against external models, not physical UART/printer wiring.

## IDE controller configuration

AF access is 4A,6C unlock at 108; index/data at 108/109; 34 lock at 108. `src/disk/hdc_ide_um8673f.c` enables primary/secondary from B0. Its lock checks the previous index, which does not exactly implement the manual's immediate-lock description.

| AF register | Runtime | Model reset | Meaning and evidence limit |
| --- | --- | --- | --- |
| B0 | C0 | C0 | Masks 80/40 enable primary/secondary. |
| B2/B3 | 44 each | 00 | Manual PIO0 timing policy; model stores only. |
| B4/B5/B6/B7/B8 | CC each | 00 | Manual PIO0 timing policy; model stores only. |

The maintained BF PCI IDE adapter accepts class0101 and ID673A1060. ID673B1060 is not an accepted identity in this port. The native AMI module44 method atB84A..B887 derives `(PI & 0A) >> 1` and clears only those switchable mode bits. The runtime uses that method and reads PI back before assigning legacy ownership. It writes dwordsFF30C900 at40 andBBBB6666 at44 only after both channels read as compatible. Native, mixed, ignored mode writes and rejected I/O BARs retain an unusable hardware state. Discovery issues no AF-window writes or legacy task-file probes for those states. The saved Enabled request remains separate from usability.

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

The older complete-core harness checks all four first-present positions, the former two-record logical mapping, mixed ATAPI/ATA discovery, BPB geometry, multisector CHS, EDD read/write restoration, actual DOS6.22 and secondary-channel El Torito. Older partial-shell tests are not the maintained proof. Those older checks do not establish electrical PIO margins. `tools/ide_completeness_proof.py` separately executes four simultaneous devices, mixed ATA/ATAPI gaps, invalid BIOS numbers, later-disk geometry, both reset channels, secondary CD boot and full configuration save/reload. Its independent models do not establish physical timing margins.

### Faster-PIO reference decoding

The modern Biostar payload remains x86-BCJ encoded after LZMA expansion. Reverse that filter before following relative calls. The decoded stream identifies the per-device mode consumer and confirms the manual's A/B/C tables. Its SeaBIOS path ignores the SET FEATURES return code and does not itself prove an applicable host clock or IORDY gate. Do not copy that failure handling. The corresponding [project sources](https://github.com/alphaonex86/mb-8433UUD-A-BIOS) pin separate coreboot/SeaBIOS revisions and apply local patches; a version string ending in dirty is not an exact upstream source identity.

The coreboot setup writes the complete48h..4Fh base as well as43h..47h. Its N-host setup uses41h lowD/42h33, while the manual specifies low9/30 for the F host. The explicit PCI ratio remains authoritative. Faster-mode activation must qualify the host and device, check command completion, and restore conservative channel timing before reset. A mode request and the effective mode are separate state. FIFO and bus mastering remain disabled.

Original M919 AMI normal code233C..2445 supplies a stronger board-specific timing reference. Its BF branch selects this recipe on sibling function0 revision0D, while the older AF path uses indexed registers. That original branch is not a universal capability limit for the documented PCI interface. Table2328..233B gives A/B/C triples3/6/B,2/5/8,1/4/5,0/3/2,0/3/0 for modes0..4. It updates each device's two-bit field in43h, B nibbles in44/45,48/49,4C/4D and C nibbles in46/47,4A/4B,4E/4F. All four originals use the same triples: March1996 table231D/consumer2331..243A, May1996 table2328/consumer233C..2445, October1996 table2335/consumer2349..2452 and September1998 table2329/consumer233D..2446. The owner does not establish a numerical host clock or IORDY contract and does not call the generic EF03 negotiation helper. The first PIO0–2 bench restriction is superseded. Version0.9.2 uses all five mode tuples, device IORDY/cycle checks and checked EF03 completion. The user explicitly requires the officially supported modes on all controller revisions and board clocks through50MHz. No clock argument or frequency-specific tuple occurs in these original timing owners. IDE41 staysC9, with bit04 already clear as the pinned manual requires above PCI33MHz. The original module44 ownerB84A..B887 changes compatibility-mode bits only. Stock AMI can divide PCI at faster FSB settings; its FSB50 boot is not evidence for physical PCI50 margins. No new frequency formula is inferred.

Before EF03, the shared owner waits for BSY/DRQ clear without rejecting an older command's ERR. An optional C6 SET MULTIPLE abort otherwise suppresses negotiation. EF03 completion still rejects its own ERR, and a pending phase blocks the channel. PIOSTATE's revision10h/0Eh snapshot identified the removed revision veto; current diagnostic revisions are informational.

The current cache activation policy permits installed RAM beyond the selected tag range. It keeps successful cache qualification, geometry and the complete reference fill-span guard, and publishes all detected RAM. WT/WB fixtures preserve different values at102B60h and2102B60h across flush with256KB L2 and64MiB RAM. This models independent upper-range bypass; it does not prove the chipset's electrical behavior. The complete reference activation window remains byte-identical.

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

Measure physical bank organization and aliasing, HB/SB revision IDs, ISA/PCI clocks and jumpers, ROM decode/shadow behavior, flash-write protection, graphics identity, and slot interrupt wiring. Retain the accepted ROM until the cache candidate passes its checks. The user now reports a selected 512 KB SRAM population passing Memtest and running Quake with WB enabled. The user also confirms stable revision3.4 settings, PIO4 and working VLB with version0.9.2. Relaxed Setup timing temporarily restored its floppy, but the recurring fault remains unresolved. Further PCI tuning is deferred. Broader timing margins and DMA measurements remain unobserved.

The earlier measurements did not establish an upstream correction. The expanded study above now provides ROM-derived annotation proposals with explicit evidence limits. Earlier reproducer candidates include AF lock ordering, the HB5B status/write discrepancy, missing emulator DRAM mapping, and inferred SB57 protection. Public submission requires a user request.

## Physical cache diagnosis

The reported socket labels put Bank 0 (U20-U23) at the outside edge, Bank 1 at U11-U14, and TAG at U19. A 55AA55AA read became 57AA55AA while uncached RAM retained 55AA55AA. The differing byte is byte 3, D24-D31. Replacing U23 moved the first reported failure from Bank 0 byte 3 to Bank 1 byte 3 without changing Bank 1. Replacing U14 then restored 512 KB WT qualification. The later physical tests establish the complete Bank 0 map: U23=D24-D31, U22=D16-D23, U21=D8-D15 and U20=D0-D7. The remaining Bank 1 byte lanes are unverified. Tag, timing and socket faults can also cause data mismatches, so localization remains a suspect lane rather than an unconditional chip verdict.

The user's 09/15/1998 AMI snapshots show HB50/HB51=3C/F5 in manual mode and 0C/55 in auto mode. Both retain HB5A=0D and HB61=20. Those DOS snapshots do not by themselves prove the earlier qualification branch or effective external cache. CTCM's subsequent 8-KiB L1/16-KiB L2 classification and its dirty-tag detectability notice do not establish a working 512-KiB external cache. No runtime timing changes were made from these snapshots.

## Selected SRAM and ViRGE result

The user rejected twelve SRAM chips before selecting a full 512 KB population that passes Memtest and runs Quake in WB. Some rejected parts pass a TL866II or work in other boards. Two UMC parts were identified as faulty during random-sequence testing. Do not classify all rejected parts as dead, or either vendor as universally incompatible. The [Winbond W24512AK-15 datasheet](https://www.syntax.com.tw/upload/pdf/IC-W24512AK-15.pdf) and [UMC UM61512AK-15 datasheet](https://images.100y.com.tw/pdf_file/37-UMC-UM61512.pdf) have identical pin/control interfaces but different write-data and turnaround limits. Winbond requires 9 ns data-valid-to-write-end versus UMC's 7 ns, and permits output drive immediately after write end versus UMC's 5 ns minimum delay. No socket waveform or exact final die population was recorded, so these specifications do not prove the physical cause.

The user confirms S3 ViRGE compatibility. Reset screen corruption remains unresolved. Shared PCI aperture sizing reserves the full usable VGA ROM window, not just its legacy header. UMC shadow controls remain in the adapter. Disk IRQ14 acknowledgment is shared, as is the corrected delayed-completion/DRQ polling used by the composed firmware and Presario.

## Later reset, DMA and Setup corrections

Original normal reset code89A2 sets BDA72=1234 and enters F000:E05B. The protected branch atB4C9 tests PE, clears shutdown0F through EBEA, applies KBC D1/DF through ED12, then sends FE atB5C1. It avoids WBINVD and CR0 access. M9190.9.3 retains the real-mode flush path and uses those protected-state prerequisites before the pulse. Direct real/V86 fixtures and timeout cases establish software behavior. They do not reproduce a loaded Microsoft EMM386 session. Revision3.4 still hangs on Ctrl+Alt+Del with Microsoft EMM386, while OEM, XMGR and JEMMEX reset. Revision1.5 resets normally. The user accepts this unresolved compatibility limit for publication.

Startup and late FDC wake establish C2=(old & DFh)|81h. Bit0 is the reference initialization value, not a proven electrical enable signal. The focused reset/IRQ/DMA2 model now starts with bit0 clear as well as set. The revision3.4 floppy fault recurred after an apparent timing-related recovery. This remains unresolved despite the fixture result.

Version0.9.5 moves the existing AT cascade tuple before the shared FDC enable gate: C0 toD6, then00 toD2 andD4. Disabled FDC policy still issues no FDC commands or DMA2 transfer setup. All four compiled shared entry points pass an independent guest-DMA1 payload check. PB430 full POST already establishes this cascade in its refresh owner. The user confirms restored sampled sound with FDC disabled.

The VLB palette inversion and ISA sound crackle reproduce with the original BIOS on revision1.5, including both caches disabled. The current cards are Trio64 VLB and ESS ES1868 at IRQ5/DMA1. Sampled effects trigger the fault. Music-only, MIDI and PC-speaker effects do not. This supports a DMA/bus interaction hypothesis, but no register cure is established. Silencing sound by disabling the cascade had only masked the graphics symptom.

The current menu has45 chipset descriptors. ISA owns three rows. Its obsolete four-row view exposed Memory's first descriptor and is corrected in0.9.6. ECP DMA remains C_CHIP22.1 and appears in the five-field Devices page. Its choices1/3 map to the existing bit without moving the92-bit record. The unused game bit stays opaque. Floppy Controller belongs only to Drives. Assembled view/row/owner audits reject the preceding duplicate controls and verify the existing Drives save path. Physical UI confirmation is separate.

Version0.9.7 corrects the policy selector beneath the explicit channel labels. Each physical record selects the matching saved record, enable bit, requested PIO mode and data-width bit before discovery. Setup never probes devices or reorders its forms. The detected ATA disks still receive contiguous BIOS drive numbers. The preceding0.9.6 image fails the lone-Secondary-Master contrast because it gives that device policy0. The composed correction proof covers empty, single, mixed-hole, disabled and full inventories through actual Setup edits, save/reload and public transfers.
