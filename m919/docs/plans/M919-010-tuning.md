# M919 tuning and IDE completeness


The port must expose the established, non-power-management tuning controls through the existing Setup screens. It must preserve the selected SRAM sequence, explicit bus ratios, saved settings and no-AUX policy. The user confirms acceptable PCI performance and the0.5.4 ViRGE reset display fix.

The T3 implementation base is public main `45af65632d5da21beda60c211c9cbe2f7d487f90`. Use one writable task branch, `task/m919-ide-completeness`, in the primary checkout. The preceding T1 checkpoint remains immutable. M919 owns its roadmap. The register report at `docs/research/m919-registers.md` records known omissions and evidence limits. The M919-009 specification owns the earlier shared-default, ATA completion and VGA aperture contracts.

## Owners and limits


Shared firmware owns disk services, generic ATA transactions, Setup and boot policy. The M919 adapter owns UMC register programming, board IRQ wiring, Super I/O and hardware reset. Vendor ROMs and full disassemblies remain private inputs. The physical evidence now covers selected revision1.5 and3.4 boards, with runtime hardware detection and explicit settings for variable configuration. Software fixtures do not qualify electrical behavior.

Chipset PM/SMM, unsupported PS/2/AUX, speculative field meanings and a replacement cache engine are outside this task. Shared APM remains present. The original AMI automatic timing table must not override the explicit PCI ratio.

## Subtasks


T1 publishes the confirmed tuning controls, shared IDENTIFY/data-width improvements and reset display fix. Its checkpoint boundary is the changes since71837dc. The final public-source review also includes the preceding unpublished checkpoint. The user requests review and publication before further feature implementation.

T2 adds supported faster PIO modes through shared mode selection/negotiation and a UMC timing adapter. T3 completes two-channel/four-position device policy and services, moving reusable state, discovery, selection and reporting to shared owners. Before T2/T3 implementation, derive their persistence, reset, ATA/ATAPI and compatibility boundaries from the current source and primary controller/ATA references. The T1 inventory below does not authorize an unexamined disk-state migration.

T4 completes other attainable items from the omissions report after the IDE priorities. It must distinguish known implementation gaps from unqualified hardware meanings. Power management remains deferred. Each independently useful feature requires its own validation and review boundary. Preserve the physically confirmed0.5.4 and published0.5.5 candidates while later candidates undergo bench testing.

## T1 boundary inventory and Scenario Proof


This inventory reconciles the physical iterations for checkpoint review. Per-candidate preflight was deferred under the repository's live-hardware rule. It does not claim that this document preceded those iterations.

| ID | Source and required result | Entry points and minimal contrasts | Named proof and oracle |
| --- | --- | --- | --- |
| B1 | User requires individual tuning choices, sorted unique lists and retained saved encodings. | Chipset and IDE UI parameters/commit/store plus chipset save/load. Exercise raw/display inversions, old57-prefix and expanded records, and invalid checked selections. | `manual_proof.tuning_cases`: exact masked writes,45 sorted chipset fields, both IDE records, and three real save/reload records. |
| B2 | CPU tuning requires positive identification. Host-coupled linear burst and device mapping additionally require the qualified host revision. CPU-only LSSER uses its CPU guard. | `chipset_cyrix_apply`, protocol probe and restore. Supported Cyrix contrasted with non-Cyrix, unsupported part, unavailable writable registers and another host revision. Captured PCR bit80 is restored from both initial values. | `tuning_proof.cyrix_cases`: exact qualified CPU/host writes, rejected paths issue no inappropriate CPU accesses, original state restored when disabled. |
| B3 | Explicit PCI clock selection and complete cache sequence survive new tuning. | `chipset_apply` through late cache activation, VGA bus policy and host-header owner. WT/WB and explicit1:1 ratio with selected fast timings. | `tuning_proof.host_cache_cases` and separate `final_state_cases`: actual composed activation retains the selected ratio, VGA tuple and host header. The unchanged raw cache engine reuses M919-009 qualification evidence. |
| B4 | PCI interrupts follow board wiring and avoid active ISA conflicts. | Runtime routing across three slots/four pins, Auto/manual conflict, display palette policy and IDE trigger selection. Reassigning a PCI interrupt to an active onboard ISA device restores edge triggering. Disabled IDE releases its interrupts. | `tuning_proof.irq_cases`: board-table links, allowed mask, selected endpoint lines and interrupt-controller state match the independent board table, including repeated apply and IDE enabled/disabled contrasts. |
| B5 | ROM shadows preserve providers and cache only the qualified video shadow. | `board_rom_tuning` plus `initialize_video` through later option-ROM discovery. Automatic versus added copies, L2 off/on and32/64KB apertures. | `tuning_proof.shadow_cases` and separate `manual_proof.vga_aperture_cases`: exact copied bytes/extent, protected shadow, effective video cache gate and one provider initialization. |
| B6 | Shared Fast Boot, APM and normal defaults remain available. | Visible RAM-test selector and INT15/APM query, plus default/load/save/boot dispatch. Fast Boot preserves published memory and separate cache qualification. Skipping extended tests must not skip required parity initialization. | `manual_proof.tuning_cases(shared=True)` proves the selected skip and unchanged memory publication/APM result. `shared.tools.checkpoint_proof.run` proves default and saved boot/cache policy through dispatch. `tuning_proof.parity_fast_boot_cases` follows Fast Boot completion into parity initialization and proves unchanged data is seeded before reporting is armed. Unchanged full-RAM methodology reuses its accepted prior proof. |
| B7 |32-bit transfers apply only to supported ordinary data operations. | Shared ordinary/MULTIPLE read/write helpers and public INT13 completion/IRQ ownership.16/32-bit selections, partial final blocks, delayed/error/stuck DRQ, and READ/WRITE LONG. | `shared.tools.ata_completion_proof.run` in both widths: exact payload, transfer widths, status and public IRQ delivery. LONG data stays word-wide and its four ECC bytes stay byte-wide through the actual direct and public paths. |
| B8 | Empty ATA slots return promptly without shortening real device or ATAPI startup waits. | `ata_identify_wait_drq` consumed by shared firmware and Presario. Ready-to-zero/floating ATA versus busy, non-progressing present ATA and known ATAPI. | `shared.tools.ata_identify_proof.run`: exact terminal flags/status/delay counts on the four compiled ports. |
| B9 | Reset must not expose stale VGA scanout and must restore usable video. | Normal startup, warm reset, controlled restart and AT shutdown-service continuation. Seeded sequencer clocks/indexes and the preserved service-resume branch. | `m919/tools/test-vga-reset.py`: blank before teardown/reset, only bit20 changes, selector/text/font and CPU identity retained, A20 reset handling preserved and service resume does not blank. `manual_proof.vga_aperture_cases` additionally proves explicit display restore through successful initialization. Physical user confirmation is separate evidence. |

Each named check establishes only its listed production path. Separate named checks do not substitute for a missing hop in another row. The ignored task record owns exact commands, output identities and reusable closure records. Final trace closure must identify any missing obligation before native review.

## Decisions


The original AMI is eligible evidence for PCI, Cyrix and ROM tuning. Its cache implementation is not an implementation source. The selected complete non-M919 cache sequence remains unchanged.

The explicit PCI ratio replaces AMI's CPU-derived automatic clock policy. The user accepts the resulting measured PCI throughput. Further speculative buffering changes are not required.

The0.5.4 reset correction owns only standard VGA blanking around hardware reconstruction. ROM aperture sizing and cache/timing settings stay with their existing owners.

The historical T1 publication target was0.5.5. Its parity and interrupt predicate repairs preserve the existing behavior contracts;0.5.4 remains the physically confirmed reset-display baseline.

The user prioritizes faster PIO and complete dual-channel support. FIFO and proprietary DMA are separate transfer engines and must not be approximated with an enable bit in the PIO driver.

## Current contract and historical scope

The user first approved version0.9.2 for final review/publication after confirming PIO4 and stable revision3.4 settings. That unit has a reported UM8670F; the earlier UM8663 identification was corrected. Relaxed timing temporarily restored its floppy, but the fault recurred. Microsoft EMM386 Ctrl+Alt+Del also remains unresolved on that unit. The user accepts both limits for publication. VLB was physically validated and much faster than PCI in that setup. Further PCI tuning is deferred. These observations do not qualify all supported bus clocks.

The [shared PIO plan](../../../docs/plans/BAIOS-010-pio.md) owns the current B1..B22 inventory. It supersedes only the historical T2/T2a mode, exact0D/33MHz qualifier and clock-selector restrictions below, and the historical T4 Game Port feature. Current modes0..4 depend on the enabled, usable673A function, accepted device capability and completed command. The full fixed seven-field recipe remains; there is no IDE timing-clock menu. Its saved bit remains opaque compatibility data. Chipset field count is45. Devices has five fields, with ECP DMA immediately after Parallel Port Mode. Floppy Controller belongs only to Drives. The three-field ISA view cannot render Memory descriptors. Game Port is absent and its decoder remains disabled.

New bounded corrections cover previous-command ERR before EF03, cold FDC bit01 initialization and cache activation with installed RAM above the tag range. Qualification/failure and minimum reference-fill guards remain. These changes do not add a new cache protocol. Shared stale-ERR behavior is retained in PB4300.2.2, Presario0.2.2 and MP3860.3.2. Their later patch also places the global AT DMA cascade before the optional FDC gate. PB430 already supplies that cascade earlier in full POST. The user confirms restored sampled sound with FDC disabled on M9190.9.5.

Version0.9.7 is the later publication candidate. The user supersedes the historical detected-order policy with fixed physical Setup positions. B22 owns that correction. Direct reset fixtures cover real/V86 branching and controller timeouts, not a confirmed EMM386 cure. The shared cascade fix restores digital sound, but the OEM-reproduced VLB palette fault remains. All-cache-off and music-only controls separate that accepted limitation from the cache engine. The0.9.7 UI and policy changes still lack a separate physical confirmation.

The following accepted preflights describe their original checkpoints. Their current supersessions are stated above; they are not requirements to restore removed controls. Preserve the existing T1/T2B/T3B/T4B identities and valid unchanged evidence for review. T2B1 now follows shared B3, T2B6 follows B9, and the Game portions of T4B1/T4B7/T4B8 follow B12. B13..B16 add the earlier correction and diagnostic boundaries. B17..B21 cover protected reset, Devices mappings, independent DMA cascade, single menu ownership and explicit IDE identities. B22 replaces detected-order policy selection with fixed physical settings.

## Fixed physical IDE policy correction

The user explicitly supersedes the historical detected-order policy contract: Setup does not depend on attached devices. Each of its four entries always owns Primary Master, Primary Slave, Secondary Master or Secondary Slave. This also applies before discovery and with the controller disabled. No Setup probe, migration, provisional label or new state is required.

The correction removes ordinal selection in `shared/src/pc/ata-inventory.inc`. Each physical record selects its matching saved policy, enable bit, PIO request and data-width bit. The existing CMOS byte format and BIOS ATA-only detected-disk numbering remain unchanged. The current four-position include is compiled only by M919. Other maintained ports keep their two-position owner.

This is strict simplification of the existing policy selector. No challenger is required for the deleted indirection. The normal-use floor is the same fixed Setup row before and after discovery, with settings retained through save/reload. The ceiling is deletion of detected-order rebinding, without a new persistence or discovery framework. The old wrong behavior is not a format to migrate.

The composed scenario must enter actual discovery, render overview/submenu/help, edit a physical policy, save, reload and rediscover. It must distinguish an empty bus, a lone Secondary Master, mixed ATA/ATAPI holes, a disabled physical slot and all four positions. It must compare per-position policy and PIO/data-width state, ATA-only BIOS numbering and independent public payloads. Early Setup remains editable without ATA I/O. The preceding0.9.6 image must fail the gap contrast. This is boundary B22 in the shared plan.

## Historical T3 accepted preflight

Required outcome: four simultaneous ATA/ATAPI positions, four complete persistent device policies, contiguous ATA-only BIOS numbers, and CD boot from either channel. Shared firmware owns iteration, policy, public selection, channel reset, IRQ and presentation. M919 supplies the qualified controller gate and physical port table. Other ports retain their two-position format and behavior.

Prior plan reconciliation: this section refines only unfinished T3 from the preceding specification. T1 remains the published checkpoint. T2 remains separate: automatic faster PIO requires a source-backed host clock and IORDY contract; the timing tuple alone does not establish it. T4, PM/SMM, FIFO, bus-master DMA, cache protocols, new disk boot priority and fixed-cable policy migration are outside T3.

Preserve the existing first/second *detected* policy meanings on M919. Add policies three/four with Auto defaults. Runtime records instead describe the four physical positions, with an independent `S_POLICY_INDEX`. Assign an ordinal immediately upon successful identification, before its enable policy is applied. An explicit FF sentinel distinguishes absent/unassigned records from detected-but-disabled records. Complete remaining sentinel mappings after discovery. Before discovery, including early Setup and an unusable/disabled controller, forms access only the policy arrays. They never infer runtime metadata or require a probe. Runtime S_ENABLED is derived from policy, separate from the root policy0 enable.

Use a board count of four, with shared default two. Preserve the 200h runtime stride. Move only M919's active/draft IDE arrays to A00/A40, size51, in its existing8KiB EBDA. Place its per-record nine-word port table at190h and position at1A2h, leaving CD/global cache/KBC/RAM scratch owners intact. `S_POLICY_INDEX` uses1CFh. Initialization clears only ATA-owned fields, never whole record0/common state.

All four policies retain type, translation, block size, EDD,32-bit transfer and manual geometry. The first two enable flags remain owned by the base settings record; only policies three/four add enable bytes. Keep every saved encoding. Use count-aware shared Setup and POST; M919 policy labels say Device1..4 instead of falsely claiming cable positions. Physical POST labels still identify channel/master/slave.

M919's CMOS extension occupies40h..7Fh exactly: IDE44bytes at40h..6Bh (ID/schema2/checksum, controller, four packed type/translation bytes, three packed flag bytes, four eight-byte geometry records); ports5bytes at6Ch..70h (P/schema2/checksum/two selector bytes); chipset15bytes at71h..7Fh (tag/checksum/13bytes of mask-selected bits). RAM policies remain unpacked. Global marker33h..35h is34h,02h,CAh; a checked marker distinguishes this format from legacy. Load legacy without writing, preserve its first two records and default the additional policies. Invalid records fall back only at their existing owner. Full save invalidates the base signature, publishes/verifies the format marker, writes/verifies extensions, then commits the base signature. Standalone chipset recovery save retains the current format. Every recovery marker reader/writer, including shared RAM-test failure, uses the board-selected address; new IDE bytes at old69h must never masquerade as recovery.

### T3 Scenario Proof and source clauses

The authoritative clauses are the user requirement for complete dual-channel support, existing ATA-only numbering and CHS/EDD behavior (`bios.asm`), detection-order compatibility (`ata-core.inc`), full record validation/persistence (`ide.inc`, `peripherals.inc`, `chipset-core.inc`, `setup.inc`), boot BPB ownership (`chs-geometry.inc`, `boot.inc`), packet discovery/boot (`cdboot.inc`), and recovery publication (`ram-test.inc`, M919 cache/chipset owners). The preflight challenger expansions below are applicable, with no unresolved T3 contract gap. T2's host timing qualification remains an explicit separate gap.

| ID | Discriminator and required terminal result | Production path and runnable oracle |
| --- | --- | --- |
| T3B1 | Empty, single positions, four ATA, duplicate model prefixes, ATA/ATAPI holes, identified Disabled versus absent. All physical records retain unique policy identities; no common state is cleared. | `ide_completeness_proof`: real scanner through publication, distinct independent device payloads/metadata, common-state and CD/KBC/PCI/RAM sentinels. |
| T3B2 | Early Delete Setup, disabled/unusable controller, and post-discovery Setup. All four complete forms edit/cancel/save without aliasing; gated paths issue no task-file I/O. | Same proof: actual Setup entry/navigation and record commit with distinct policies, then save/restart/discover/public read. |
| T3B3 | Mixed inventory's last valid ATA number versus first excluded number. Invalid requests never alias or issue task-file I/O, including EDD count; zero-disk80h compatibility remains. | Same proof: public INT13 geometry/CHS/EDD/payload and independent port log, every advertised disk, first excluded disk, caller/buffer protection. |
| T3B4 | A boot BPB geometry different from a later disk. Only the selected boot disk adopts it; explicit geometry wins. | Same proof: boot owner through later AH08/parameters/task-file address and independent sector read. |
| T3B5 | Primary/secondary reset, ATA/ATA and ATA/packet peers. Reset invalidates only that channel and restores required peer state before subsequent real reads; IRQ14/15 complete correctly. | Same proof: production reset then ordinary/MULTIPLE/packet continuation and PIC/INT15 observations. |
| T3B6 | Earlier nonbootable packet provider followed by a valid third/fourth-position CD. Discovery continues to the valid provider. | Same proof: actual CD boot iterator, independent El Torito bytes and selected packet ports. |
| T3B7 | Golden legacy records and independent packed schema, all four distinct full policies, valid/corrupt owner records and reserved padding. No-write load, defined local fallback and lossless save/restart. | Same proof: independent byte grammar and real settings owners, exact CMOS bytes, saved encodings and sorted visible choices. |
| T3B8 | Old/new recovery markers, including new geometry containing D2 at old69h. Real visible-RAM failure publishes the correct marker, restart selects safe policy without corrupting IDE/ports. | Extend `ram_proof` through actual failure/publication/restart; direct seeded-marker cases supplement this composed path. |
| T3B9 | Other ports keep two records, legacy CMOS and device enable/reset behavior. | Existing Presario IDE policy and legacy disk checks plus builds and changed shared-path checks; do not repeat unrelated validated matrices. |

Preflight: ready — expand the shared bounded device owners, retain the M919 port adapter, and compact only its full CMOS extension. The ignored task result records exact challenge identities and execution evidence.

## Historical T2a accepted preflight

Goal: offer per-device PIO0, PIO1 and PIO2 limits through shared negotiation and reset owners, with a complete qualified UMC timing adapter. Target version is0.7.0. This refines only unfinished T2. The accepted T3 checkpoint remains immutable. Auto and Unknown timing clock retain effective PIO0. An explicit33MHz timing-clock input enables the source-derived faster bench path. This input describes the actual PCI clock and does not change it. It is not an electrical qualification for every board or clock.

Shared owners compose IDENTIFY parsing, requested/effective mode state, command completion, blocked-channel state, reset, Setup and reporting. The M919 adapter composes the detected BF controller's register programming. ATA devices and electrical timing are opaque external systems. T3 persistence and four-device identity remain authoritative. The selected cache engine, automatic clock inference, modes3/4, host IORDY enable, FIFO, DMA, PM/SMM and other ports' policy are outside T2a.

The primary controller evidence is original AMI normal code233C..2445, called after IDENTIFY at564C. The BF branch requires southbridge revision0D and uses the full A/B/C recipe, including48h..4Fh. Its mode0/1/2 triples are3/6/B,2/5/8,1/4/5. Shared ATA negotiation must check SET FEATURES completion rather than copy the original host-only owner. ATA/ATAPI5 IDENTIFY validity, legacy word51 and minimum no-IORDY cycle word67 constrain the device limit. A fast IORDY-only capability does not establish a no-IORDY timing margin.

Keep four two-bit requested limits in C_CHIP byte20 and the clock selector in byte21 bit0. Zero means Auto/Unknown. Append these controlled bits to the packed record without shifting existing fields. Legacy standalone chipset saves keep these new bytes zero and retain the old format. Full save still migrates through the established owner. Runtime effective mode and IDENTIFY limit use free ATA-owned state before1CFh. A separate root channel mask blocks pending commands without deleting the advertised disk identity.

Before SRST, restore conservative host timings for both affected physical positions. After SRST, restore each identified ATA or packet device's requested/effective mode before geometry, MULTIPLE or packet traffic. Apply fast host timing only after successful EFh/03h completion. A completed ABRT retains PIO0. A command that remains busy or has a pending phase blocks replacement commands to that whole channel until reset. It must preserve S_PRESENT, capacity, model, BIOS numbering and the saved request. ATAPI readiness must not require DRDY.

### T2a boundary inventory and Scenario Proof

| ID | Authoritative clause, discriminator and contrast | Production path and required oracle | Named check |
| --- | --- | --- | --- |
| T2B1 | User requires faster PIO without assumed hardware. Qualified BF/revision0D with explicit33MHz versus unknown clock, wrong revision, unusable/disabled or absent controller. | Discovery/reset through board adapter. Unknown paths retain effective0 and issue no fast timing or negotiation. Positive path uses detected BDF and exact masked fields. | `pio_proof.qualification_cases` |
| T2B2 | ATA IDENTIFY timing contract. Same advanced capability with valid word67 at/below/above383ns and240ns, missing/invalid optional data, and valid/invalid legacy51. | Real discovery through shared IDENTIFY parser and negotiation. Independent device maximum and requested cap determine effective0..2; host never outruns no-IORDY timing. | `pio_proof.capability_cases` |
| T2B3 | Complete source-derived per-position recipe. Each mode and every physical position versus opposed peer nibble contents. | Real discovery/negotiation through adapter. Exact43..4F fields and operation order match independent original-board table, with other devices and global clock/FIFO/BM fields preserved. | `pio_proof.timing_cases` |
| T2B4 | ATA command completion owns activation. Accepted EF03 versus completed ABRT versus persistent busy/pending phase. | Discovery into next same-channel probe, later public ATA read/write or packet command. Fast host writes follow success only; ABRT uses0; pending channel issues no replacement command and retains previously identified disk metadata/numbering. Other channel continues. | `pio_proof.completion_cases` |
| T2B5 | Reset must invalidate device negotiation for both peers. Primary/secondary ATA pairs and mixed ATA/packet, different peer limits. | Public INT13 reset through conservative host writes before SRST, restored modes, geometry/MULTIPLE and subsequent ordinary/MULTIPLE/packet reads. Exact per-peer effective modes, independent payloads and unrelated-channel state survive. A previously blocked channel reopens only through reset. | `pio_proof.reset_cases` |
| T2B6 | Requested limits differ from effective results. All four policies, sorted PIO0/1/2/Auto and33MHz/Unknown choices, cancel versus save. | Real Setup arrows/popup, full save/reset/fresh load/discovery and POST summary. Exact packed bytes and retained four-device/port/chipset settings; literal choices and actual effective mode display. Auto/Unknown remain conservative. | `pio_proof.policy_cases` |
| T2B7 | Shared improvements preserve existing consumers. Flag absent versus M919 flag present with default Auto/Unknown. | Compiled two-position legacy services and existing four-device checks. Unchanged settings/discovery/CD/public ATA behavior and selected cache engine identity. | Existing T3 proof, shared completion/default checks and bounded other-port builds |

The original AMI full timing tuple and ATA command contract are mapped above. Physical timing margins are opaque and need bench testing. PIO3/4, IORDY wiring and FIFO/BM are deferred, not approximated. No new default boot policy, disk priority, cache protocol or independent persistence owner is added. The existing preflight challenger accepted this narrowed path after adding the word67 and whole-channel pending-command obligations. There is no unresolved T2a implementation decision.

Preflight: ready — shared conservative mode negotiation and channel reset, with a source-qualified M919 timing adapter.

## Historical T4a accepted preflight

Goal: add Game Port and ECP DMA channel selectors, and complete Memory Parity. Target0.8.0 refines only unfinished T4. T2a remains immutable. Existing Chipset > ISA Bus descriptors own the peripheral choices. Memory Parity keeps its existing Memory-group switch. Shared ports records, cache protocols, automatic hardware assumptions, PM/SMM, AUX and new transfer engines remain outside this change. Physical joystick, printer DMA and parity-SIMM operation require separate evidence.

Append two bits in C_CHIP byte22 after T2 bytes20/21. Bit0 selects Game Port:0 Disabled,1 Enabled. Bit1 selects ECP DMA:0 channel3,1 channel1. These zero defaults match original fallback BC5B/BC6D. Packed option length23 and mask03 append bits without moving existing fields. Legacy standalone saves keep new bytes zero. Full save retains the current migration/publication owner. Display DMA channels1,3 through inverse mapping. Use existing arrows and popup, with documented defaults in plain help. The ISA group gains two rows within the current panel.

SIO application owns only C0.20 for Game Port and only C3.40 for DMA. Apply DMA only when LPT is enabled in ECP mode. Retain its saved choice through inactive modes. Original code293F..2954 and BD0E..BD4B supplies the bindings and gates.

One parity helper owns ordered masked HB5A.10, HB05.01 and inverse IBC41.40. Early chipset apply holds reporting disabled. The post-RAM owner initializes required memory, then applies the enabled tuple before unmasking parity at port61. Preserve IOCHK, speaker bits, PCI status and unrelated fields. No new volatile state is required: successful late cache activation does not call early timing, and cache_run saves/restores HB5A and port61. Safe recovery selects parity-disabled defaults. Added operations remain outside the unchanged transient cache sequence.

| ID | Source clause and minimal contrast | Production path and required oracle | Named check |
| --- | --- | --- | --- |
| T4B1 | Manual C0.20/Game selector. Enabled from clear versus Disabled from set. | Peripheral/controller callers through ports_apply. Exact Game bit, other device fields and closed index window. | `tuning_proof.game_port_cases` |
| T4B2 | Original BD2B..BD4B. DMA1 versus DMA3 with opposed C3.40. | ports_apply. Bit set for1/clear for3, other C3/C4 bits preserved. | `tuning_proof.ecp_dma_cases` |
| T4B3 | Original enabled-LPT/ECP gate. ECP versus SPP/EPP/disabled, then ECP with retained choice. | One policy/application sequence. Inactive field preserved, final ECP applies saved choice. | `tuning_proof.ecp_dma_cases` |
| T4B4 | Original B3AF..B3E7 tuple/order. Enabled versus Disabled from opposed registers. | Initial apply through post-RAM completion. Ordered masked byte writes, unrelated fields and PCI status preserved. | `tuning_proof.parity_controls_cases` |
| T4B5 | Existing seed-before-reporting rule. Full test versus Fast Boot and Esc. | Actual visible RAM selection through post-RAM seed and arm. Required coverage preserves values, controls remain safe through the final required seed write. | `tuning_proof.parity_fast_boot_cases` |
| T4B6 | Port61 ownership. Opposed IOCHK seeds under both parity choices. | Post-RAM completion. Only parity mask follows policy; caller IOCHK/speaker bits survive. | `tuning_proof.parity_controls_cases` |
| T4B7 | Persistence. Same real edits followed by cancel versus save/reset, legacy/current records and reserved bits. | Setup, verified save, fresh load and SIO. Independent packed bytes, no-write load, local fallback, old PIO/four-device/ports and recovery ownership preserved. | `tuning_proof.t4_policy_cases` |
| T4B8 | Sorted choices/plain help. Both raw values through arrows/popup, reversed DMA encoding. | Existing descriptors/render/commit. Literal complete unique Disabled/Enabled and1/3 sets, stored meaning and documented defaults in help within panel bounds. | Policy cases and existing choices proof |
| T4B9 | Cache/clock/device/no-AUX invariants. New settings off versus on with other policy fixed. | Peripheral transactions and late normal-state owners. UART/printer/FDC/keyboard, final parity/clock fields and cache-engine identity remain correct. Reuse engine qualification. | SIO proof and extended final-state/host-cache observations |

All Game/ECP/parity clauses are mapped above. Physical wiring is opaque. Other register meanings and system/regional ROM caching stay deferred: protection and HB58/59 requirements remain unresolved. The same fresh challenger completed independent derivation and informed challenge with no findings or software contract gap. No new shared UI or persistence framework is required.

Preflight: ready — existing descriptor, SIO and parity owners with two appended bits.
