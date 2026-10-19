# M919 roadmap

This is the source of truth for accepted M919 work. Task identifiers are permanent. Never reuse or rename an identifier. Keep at most one task active.

The user resumed hardware testing after discovering that the FSB was set to 40 MHz. Restore the build from before Fast was removed, retain full L2 failure diagnostics, and retest at 33 MHz. AMI still cannot enable L2. The fault is not localized.

Status legend:

- 🎯 **Active**: Implementation or required review is in progress.
- ⏸ **Suspended**: Work is paused at the user's request.
- ⏭ **Planned next**: Accepted and ordered for near-term delivery.
- ◻ **Planned later**: Accepted but not yet scheduled.
- ⚠️ **Accepted residual risk**: Bounded work is complete with a limitation accepted by the user.
- ❌ **Declined**: Intentionally unsupported work.
- ✅ **Completed**: Implemented and validated work.

## Active

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

- **M919-008: Complete hardware adapters and accelerate RAM testing.** Completed RAM geometry, Super I/O, cache qualification and fault reporting, shared CPU recognition, and PCI support while preserving the donor firmware and presentation. Full-coverage RAM testing is faster. The complete software matrix, boundary trace closure, and native review passed. Replacing U23 and U14 restored the reported revision 1.5 board's 512 KB write-through cache. Wider physical compatibility and timing margins remain in M919-005.
- **M919-002: Port the complete donor firmware through M919 hardware adapters.** Delivered the shared donor POST, RAM test, Setup, CMOS policy, beeps, error handling, presentation, and native DOS 6.22 services. M919 adapters support the reported revision 1.5 baseline. The no-AUX board policy restores keyboard input. Complete first-deliverable validation, trace closure, and final review passed. Wider compatibility remains in M919-003 through M919-007.
- **M919-001: Prepare the M919 port and shared source.** Prepared root shared code, M919 porting seeds, diagnostics, reference identities, and the complete-POST contract. Presario ROM bytes and all original AMI references remain unchanged.
