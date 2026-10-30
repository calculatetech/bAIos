# M919 roadmap

This is the source of truth for accepted M919 work. Task identifiers are permanent. Never reuse or rename an identifier. Keep at most one task active.

The user resumed this port and replaced its adapters. A selected 512 KB SRAM population now passes Memtest and runs Quake with write-back cache enabled. Rejected chips are not all established defective. The shared-code checkpoint and its defaults are confirmed. Preserve that candidate while extending the tuning controls.

Status legend:

- 🎯 **Active**: Implementation or required review is in progress.
- ⏸ **Suspended**: Work is paused at the user's request.
- ⏭ **Planned next**: Accepted and ordered for near-term delivery.
- ◻ **Planned later**: Accepted but not yet scheduled.
- ⚠️ **Accepted residual risk**: Bounded work is complete with a limitation accepted by the user.
- ❌ **Declined**: Intentionally unsupported work.
- ✅ **Completed**: Implemented and validated work.

## Active

- **M919-010: Complete the known tuning controls.** Add the non-power-management controls supported by the aggregated ROM and chipset evidence through the existing individual-setting menus. Preserve confirmed defaults, valid saved settings, dynamic hardware detection, the complete cache sequence and no-AUX policy. Keep uncertain encodings and chipset power management deferred. Retain the existing shared APM service. The [tuning and IDE plan](plans/M919-010-tuning.md) defines the publication checkpoint, then faster PIO and complete dual-channel/four-device support through shared owners. Physical iteration uses bounded checks and a new flash candidate.

## On hold

- **M919-004: Extend M919 chipset configuration.** Add the supported memory and cache timing options through the existing adapters. Reuse the Presario RAM profile system and preserve its screen, extending the table for M919 bus speeds. Validate L2 immediately after the RAM test, show enabled status only in Summary, and speed up testing with persistent validation until Setup parameters change. Preserve the complete donor firmware, recovery, saved settings, and presentation; justify register mappings with the local manual and AMI code.

## Planned next

- **M919-003: Extend the disk compatibility matrix.** Basic DOS boot and donor disk services are required by M919-002. Extend proof across both IDE channels, multiple disks, option-ROM providers, boot policies, and capacity limits using disposable media.

## Planned later

- **M919-005: Validate broader cache, memory, and CPU compatibility.** M919-008 owns adapter completion for revision 1.5 and the reported SRAM. Establish physical timing margins and wider CPU/SIMM combinations after that work. Add each later PCB revision only with independent evidence.
- **M919-006: Prepare upstream register corrections when evidence requires them.** Compare the pinned UMC manual with AMI instruction traces, emulator behavior, and revision 1.5 observations. Distinguish AMI bugs, emulator gaps, and documentation errors. Keep a reproducer and chip/revision limits with each proposal. Public submission requires a user request.
- **M919-007: Finalize the supported port.** Use the retained [M919-002 contract](plans/M919-002-post.md) and extend its supported-hardware proof. Close the BIOS-service, reset, option-ROM, boot, configuration, and hardware validation matrix. Run complete validation and required review. Deliver the final flash image with layout, reset target, retained-region checks, and hashes.

## Accepted residual risk

No residual risk is accepted.

## Declined

No task is declined.

## Completed

- **M919-009: Checkpoint the replacement adapters and shared fixes.** Local checkpoint `71837dc` records 512 KB WB operation, ViRGE compatibility with reset corruption, shared ATA/PCI VGA owners, and CD/floppy/HD defaults with supported caches enabled/WB. Targeted validation and native checkpoint review passed. The user confirmed the defaults on hardware. Further tuning belongs to M919-010.
- **M919-008: Complete hardware adapters and accelerate RAM testing.** Completed RAM geometry, Super I/O, cache qualification and fault reporting, shared CPU recognition, and PCI support while preserving the donor firmware and presentation. Full-coverage RAM testing is faster. The complete software matrix, boundary trace closure, and native review passed. Replacing U23 and U14 restored the reported revision 1.5 board's 512 KB write-through cache. Wider physical compatibility and timing margins remain in M919-005.
- **M919-002: Port the complete donor firmware through M919 hardware adapters.** Delivered the shared donor POST, RAM test, Setup, CMOS policy, beeps, error handling, presentation, and native DOS 6.22 services. M919 adapters support the reported revision 1.5 baseline. The no-AUX board policy restores keyboard input. Complete first-deliverable validation, trace closure, and final review passed. Wider compatibility remains in M919-003 through M919-007.
- **M919-001: Prepare the M919 port and shared source.** Prepared root shared code, M919 porting seeds, diagnostics, reference identities, and the complete-POST contract. Presario ROM bytes and all original AMI references remain unchanged.
