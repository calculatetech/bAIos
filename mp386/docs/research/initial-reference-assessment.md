# Mitsubishi MP386/25 reference assessment

Research date: 2026-10-20.

This initial assessment used the then-reported MR BIOS boot as its startup reference. Later bench reports correct that identification: the OEM boots, including with the proprietary expansion card. MR memory methods do not support that card. The implemented port therefore uses the Mitsubishi OEM memory and cache sequence. MR remains a source for decoded timing labels and masks. See the current [port contract](../plans/MP386-001-port.md) and [timing notes](timing-controls.md).

The remaining sections preserve the initial research context. Their first-boot recommendations and open cache-capacity question are superseded by the current port contract and physical 32 KiB cache result. The complete TACT83000 programmer guide remains missing. No related chipset register map is established as a compatible substitute.

## Supplied ROMs

Interleave the low/even byte first, followed by the high/odd byte. Both resulting 64 KiB images have an additive byte checksum of zero. Reversing the lanes does not produce a valid reset entry.

| Input | Identification and role |
| --- | --- |
| `mp386even.bin` + `mp386odd.bin` | Mitsubishi V3.96H, 02/27/90. Reset jumps to F000:8000, then to offset 05C9. This is the board-specific reference. |
| `MRBIOS_EVEN_LOW.bin` + `MRBIOS_ODD_HIGH.bin` | MR BIOS V1.65, 04/18/94, platform identifier TACT302. |
| `V010B302.BIN` | Byte-identical to the interleaved MR BIOS pair. These are two representations of one ROM, not independent implementations. |
| `Similar ROMs/` | Eleven comparison inputs from Quadtel, AMI, ICL, HP and Mylex. A matching chipset does not establish matching cache wiring, peripheral decoding or configuration storage. |

The Mitsubishi combined-image SHA-256 is `573eae691f78fcfc2906acfb59abe3cf8ffb3d8cfc37d761318018b430f900e7`.
The MR BIOS combined-image SHA-256 is `5e0c0e389252ba6d2cb96398900d48fed0ba2d555ecc8f0d22b049a314729a14`.

The OEM Setup disk is unavailable. A correct substitute is not established by the supplied diagnostic names. The MR BIOS pair and V010B302 are one functional reference. Their cache behavior remains unqualified.

## Chipset documentation

The existing TI datasheet identifies the missing programmer guide as literature number **SRZU001**. Its first three printed pages establish the Tiger architecture and the configuration access protocol. They do not supply the configuration bit definitions.

The chipset has a TACT83443 AT bus interface unit, a TACT83442 memory control unit and TACT83441 data path units. A 386DX system uses two data path units. The TI datasheet explicitly supports an Intel 82385 or compatible cache controller.

Printed page 3 specifies 16-bit accesses. The default data port is 0024h and the default index port is 0026h. Software can relocate the pair. Mitsubishi ROM offset 1C6B uses `OUT 26h,AX` followed by `IN AX,24h`, which agrees with this documented interface.

Do not confuse that word-wide interface with Mitsubishi's byte-wide index/data helpers at 5Ah/5Bh. Those helpers are present at ROM offsets 23FC and 2407. Their register semantics still need a complete board-specific trace.

The closest TI material found during this search is the three-page **TACT82411 AT Chip Preview Bulletin**, document SRZT105. It describes a single-chip 286 design that also supports 386SX. It does not provide a usable programmer register map or establish Tiger register compatibility.

Later TI patents cite the Tiger guide and describe compatible interrupt, timer and RTC behavior. Their later memory-controller, PCI and power-management registers are not Tiger register definitions. TI486SXL/SXLC documentation describes processor controls, not this motherboard's chipset.

The search covered TI's SRZU001 document URLs, the Bitsavers TI directory and databook catalog, Internet Archive catalog search, and exact part and guide names. No complete digital SRZU001 guide was found. This is a search result, not proof that no scan exists.

## A lead for the actual guide

An [eBay listing for the 1990 TACT83000 user's guide](https://www.ebay.co.uk/itm/227212103403) retains eight photographs. The listing says it sold on September 11. It is not a currently available purchase.

The photographs establish that the book contains the missing programming sections. Its contents locate ATU configuration at 2-52, MCU configuration at 4-20, shadow controls at 4-26 and MCU port relocation at 4-29. The index/data defaults and index formats appear at 1-8 and 1-9. These photographs identify where to look in a recovered copy. They do not reveal the register bit tables themselves.

The eight [retained guide photographs](../../../reference/chipsets/ti/tact83000-guide-photos/) belong with the generic TI references. They are partial contents and index evidence, not a replacement for the guide.

## Intel cache controller

The [Intel 82385 datasheet](https://www.ardent-tool.com/datasheets/Intel_82385.pdf) is available in full. Its cover identifies December 1990, order number 290143-006. It documents the controller, configuration pins, cache policies, coherency and diagnostic behavior. The controller's board-level enable and flush wiring still require Mitsubishi evidence.

A [local Intel copy](../../../reference/controllers/intel/82385-dec1990-datasheet.pdf) and the [related TI preview](../../../reference/chipsets/ti/tact82411-preview.pdf) are retained under the shared reference owners.

The Mitsubishi [product brochure](../mitsubishi-mp386-25.pdf), page 4, specifies **32 KiB cache**, a 25 MHz 80386 and 2 MiB standard RAM. The supplied MP3220 layout also says 32 KiB. The older diagnostic handoff instead says 64 KiB. Keep that conflict open until the board's SRAM population and wiring establish its actual capacity.

The MR BIOS identifies itself as TACT302. The user identifies V010B302 as the alleged Intel-cache variant and confirms that it boots. This does not establish its cache behavior. Confirm the physical controller marking and SRAM population before selecting cache geometry. Do not use the filename or identifier as proof of cache compatibility.

## What the old diagnostic history establishes

Both supplied ChatGPT histories were recovered from their public share pages. The later handoff identifies the original Mitsubishi ROMs, 2 MiB RAM, a WDAC2420 disk and a removed 80387. Those are historical observations, not a fresh inventory of the current bench.

The histories report successful warm operation after restoring configuration, followed by cold starts with no visible POST. Later tests report that each individual proprietary NVRAM bank and each pair permits POST. Restoring all banks while deliberately invalidating one checksum also permits POST. This supports investigation of the cold-start path selected by a complete valid configuration. It does not prove bad cache, bad battery or a particular register defect.

The supplied fingerprint logs also contain proprietary configuration addresses 0200h through 02FFh. A conventional AT CMOS checksum alone cannot establish a complete or correct Mitsubishi configuration.

ROM offsets 9EB8 and 9ECB contain the proprietary port-48 write and read transactions. The read transaction includes command/address writes to port 48h. Describe the transaction precisely rather than calling every diagnostic with a read-only banner free of hardware writes.

## Initial diagnostic triage

The diagnostics directory contains 93 top-level COM files with 72 distinct byte sequences. Duplicate names do not represent separate evidence. This pass inspected selected files statically. No DOS tool was executed.

| Artifact | Source-backed assessment |
| --- | --- |
| `MP386P5F.COM` | Its code samples input port 5Fh and prints the result. It is a narrow candidate for later live observation. It does not prove which physical switch controls bit 7. |
| `MP386FP.COM` | Reads CMOS and performs the OEM-style port-48 command transaction. Its saved logs are useful comparison inputs. Reading all RTC registers and changing index/NMI state still need consideration before reuse. |
| `CMOSDUMP.COM` | Selects every CMOS register with bit 7 set at port 70h. It does not restore the index/NMI state. Do not treat it as a side-effect-free observer. |
| `MP386SET.COM` and archived `MP386SET.ASM` | The hex routine prints the high digit, converts the low digit, then returns without printing it. It also leaves NMI disabled. This version is not a reliable dump or Setup utility. |
| `MP386SPD2.COM` | Writes FFh and then 00h to index 92h through ports 5Ah/5Bh. It does not restore a captured original value. This matches the history's warning about destructive trials. Exclude it from initial bring-up. |
| Other Setup, restore, speed and trace variants | Remain unqualified. Their names and previous generated descriptions are not safety evidence. Preserve the originals for targeted analysis. |

Reading RTC status C acknowledges pending RTC interrupt state. A tool can avoid CMOS data writes while still changing hardware state.

## Recommended continuation

The user selects first boot before cache investigation. Reassemble the MR BIOS cold memory initialization and normal warm continuation. Keep OEM configuration repair outside that first candidate. This supersedes the earlier recommendation to complete the OEM cold-configuration map first.

Preserve each reference's separate assumptions and configuration format. The first adapter uses the MR ROM-default memory policy instead of its saved CMOS fields. It uses OEM port-48 transactions for bAIos configuration storage. Follow the [reference-first porting instructions](../../../docs/porting.md) and [cache sequence rule](../../../AGENTS.md#reference-cache-setup) for later cache changes.

The shared bAIos services and existing Setup interaction remain the reusable base. Check their instruction and hardware assumptions for a 386 target. Donor DRAM, cache, shadow, reset, clock and peripheral initialization remain outside the starting set until target evidence establishes compatibility.

Full hardware qualification must include cold POST, the actual cache configuration, Setup Save/reset and boot from the intended medium. The first candidate is a separate, earlier milestone. Synthetic execution or a boot with cache disabled does not establish full qualification.

## Sources

- [TI TACT83000 datasheet mirror](https://dosdays.co.uk/media/texas_instruments/TACT83000_Datasheet.pdf), printed pages 1-3. The supplied local PDF remains unchanged.
- [TACT82411 preview](https://dosdays.co.uk/media/texas_instruments/TACT82411_Preview.pdf), SRZT105.
- [TI guide photographs and sold listing](https://www.ebay.co.uk/itm/227212103403).
- [Intel 82385 original manufacturer datasheet](https://www.ardent-tool.com/datasheets/Intel_82385.pdf), 290143-006.
- [The Last Byte vendor chipset documentation](https://files.mpoli.fi/pub/pub/unpacked/software/dos/utils/misc/tlb_v252.zip/chipset.doc), section 2.26. Its Tiger support depends on the firmware retaining the default configuration ports.
- [TI patent US5710911A](https://patents.google.com/patent/US5710911A/en), references to the earlier Tiger peripheral guide. Later register tables have separate ownership.
- [First supplied diagnostic history](https://chatgpt.com/share/6ad2df64-79c8-83e9-8180-026be05c8917).
- [Second supplied diagnostic history](https://chatgpt.com/share/6ad2df4e-2584-83e9-ae84-39b6c047325f).
- Supplied Mitsubishi ROMs, board brochure, layout, switch table, diagnostic binaries, fingerprint logs and source archive.
