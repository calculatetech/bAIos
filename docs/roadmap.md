# bAIos Roadmap

This is the source of truth for accepted repository-wide work. Port roadmaps own port work. Task identifiers are permanent. Never reuse or rename an identifier. Keep at most one task active.

Status legend:

- 🎯 **Active**: Implementation or required review is in progress.
- ⏭ **Planned next**: Accepted and ordered for near-term delivery.
- ◻ **Planned later**: Accepted but not yet scheduled.
- ⚠️ **Accepted residual risk**: Bounded work is complete with a limitation accepted by the user.
- ❌ **Declined**: Intentionally unsupported work.
- ✅ **Completed**: Implemented and validated work.

## Active

- **BAIOS-012: Add Plug and Play support.** Identify supported expansion devices, assign resources without conflicts, and provide the standard BIOS interface to operating systems. Share the common logic and keep controller-specific operations in board adapters. Include ISA Plug and Play, PCI resource coordination, saved manual reservations, BIOS/OS configuration policy and Clear ESCD. Prioritize this work ahead of the remaining CPU tuning and retain the 64 KB system-ROM layouts.

## Planned next

- **BAIOS-005: Add CPU-specific performance initialization.** After BAIOS-003, investigate the performance features that supported processors can provide. Detect exact CPU vendor, model and revision before applying documented controls. Cover Cyrix/IBM 5x86 performance registers, Intel P24T Pentium OverDrive enhancements, AMD Am5x86 cache controls, and other supported CPU-specific optimizations. Use the datasheets in `reference/processors/` and record missing references. Respect board wiring, chipset coherency and reset requirements. Preserve conservative defaults and compare cold boot, warm reset, DMA and real workloads. Coordinate cache operations with BAIOS-003 and SMM behavior with BAIOS-004.

## Planned later

- **BAIOS-013: Add ACPI support.** Provide Advanced Configuration and Power Interface tables and operating-system services through shared code and board adapters. Describe the actual hardware and implement each advertised power operation. Coordinate with existing APM support and preserve legacy operating-system startup.

- **BAIOS-014: Add custom saved Setup profiles.** Save and restore named groups of Setup settings. Define available storage, validation and compatibility when firmware or hardware changes. Keep saved profiles separate from factory defaults and the current active settings.

- **BAIOS-006: Add optional power management. Very low priority.** Prioritize monitor power saving. Disk spin-down is secondary and remains disabled by default, including for solid-state replacements. Reuse shared services with board-specific hardware support and coordinate with BAIOS-004 where SMM is needed.

- **BAIOS-007: Add boot and Setup passwords. Very low priority.** Define shared password behavior, storage and owner recovery before port-specific integration.

## Accepted residual risk

No residual risk is accepted.

## Declined

No task is declined.

## Completed

- **BAIOS-003: Share cache initialization and transition tests across controllers.** Added common phase bindings, short startup checks and transition validation while preserving complete controller setup and reset sequences in board adapters. See the [cache lifecycle design](plans/BAIOS-003-cache-lifecycle.md), [shared contracts](development/firmware.md) and [port update instructions](port-updates.md).

- **BAIOS-004: Add SMI and System Management Mode support where hardware permits.** Added shared installation, handler, CPU identification and APM idle services through board adapters. Supported adapters handle real, virtual8086 and protected callers while preserving caller and cache state. Hardware activation, clock recipes, diagnostic results and remaining port work stay in port-local plans. See the [shared SMM design](plans/BAIOS-004-smm.md) and [user guide](sl486-support.md).

- **BAIOS-011: Identify SL-enhanced 486 CPU candidates through board adapters.** Added a guarded shared query that separates CPU capability from available motherboard features. BAIOS-004 extends it with identification strings and SMM services. See [SL support](sl486-support.md) and the [SL identification design](plans/BAIOS-011-sl486.md).

- **BAIOS-010: Complete shared PIO0–4 support.** Shared negotiation, command completion, reset restoration and effective-mode reporting are implemented. Ports set a documented mode ceiling and supply controller timing where needed. See the [PIO design](plans/BAIOS-010-pio.md).

- **BAIOS-009: Standardize port organization and candidate identity.** Standardized build and diagnostic paths, protected retained inputs, and added version/UTC candidate naming with latest pointers. Port eligibility and hardware work remain port-owned.

- **BAIOS-001: Move shared tools and dependencies to repository-root owners.** Moved common emulator resources, dependencies and helpers to shared owners while preserving port overrides, commands and retained inputs.

- **BAIOS-002: Organize repository ownership and build cleanup.** Keep build output clean, keep port-specific files with their ports, and organize shared references at repository root. Preserve current ROMs, original inputs, pending review artifacts and current observations. Maintain shared cleanup safety and port retention policies. Keep repository-wide work in this roadmap and port work in its port roadmap.

- **BAIOS-008: Publish a sanitized public source repository.** Published original source under MIT with private history, personal paths, vendor ROMs and manuals excluded. Publication retains the source guard and protected main branch.
