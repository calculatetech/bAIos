# M919 tuning and IDE completeness


The port must expose the established, non-power-management tuning controls through the existing Setup screens. It must preserve the selected SRAM sequence, explicit bus ratios, saved settings and no-AUX policy. The user confirms acceptable PCI performance and the0.5.4 ViRGE reset display fix.

The local task base is `71837dc`. Public integration must include the still-local checkpoint on top of public base `fc170ff`. The current branch is `task/m919-standard-cache`. M919 owns its roadmap. The register report at `docs/research/m919-registers.md` records known omissions and evidence limits. The M919-009 specification owns the earlier shared-default, ATA completion and VGA aperture contracts.

## Owners and limits


Shared firmware owns disk services, generic ATA transactions, Setup and boot policy. The M919 adapter owns UMC register programming, board IRQ wiring, Super I/O and hardware reset. Vendor ROMs and full disassemblies remain private inputs. The current operating model is the selected revision1.5 board, with runtime hardware detection and explicit settings for variable configuration. Software fixtures do not qualify electrical behavior.

Chipset PM/SMM, unsupported PS/2/AUX, speculative field meanings and a replacement cache engine are outside this task. Shared APM remains present. The original AMI automatic timing table must not override the explicit PCI ratio.

## Subtasks


T1 publishes the confirmed tuning controls, shared IDENTIFY/data-width improvements and reset display fix. Its checkpoint boundary is the changes since71837dc. The final public-source review also includes the preceding unpublished checkpoint. The user requests review and publication before further feature implementation.

T2 adds supported faster PIO modes through shared mode selection/negotiation and a UMC timing adapter. T3 completes two-channel/four-position device policy and services, moving reusable state, discovery, selection and reporting to shared owners. Before T2/T3 implementation, derive their persistence, reset, ATA/ATAPI and compatibility boundaries from the current source and primary controller/ATA references. The T1 inventory below does not authorize an unexamined disk-state migration.

T4 completes other attainable items from the omissions report after the IDE priorities. It must distinguish known implementation gaps from unqualified hardware meanings. Power management remains deferred. Each independently useful feature requires its own validation and review boundary. Preserve the published0.5.4 candidate while later candidates undergo bench testing.

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

The publication target is0.5.5. Its parity and interrupt predicate repairs preserve the existing behavior contracts;0.5.4 remains the physically confirmed reset-display baseline.

The user prioritizes faster PIO and complete dual-channel support. FIFO and proprietary DMA are separate transfer engines and must not be approximated with an enable bit in the PIO driver.
