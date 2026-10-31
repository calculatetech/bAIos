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

No task is active.

## Planned next

- **BAIOS-003: Share cache initialization and transition tests across controllers.** PB430 consumes a shared short SRAM workload and shared interrupted-RAM-test marker policy. Presario and PB430 use the maintained shared firmware owners. The [automated port update pipeline](port-updates.md) builds and validates maintained ports. Preserve each controller's complete reference setup and reset sequence. The complete common cache phase/transition driver and remaining M919 cache migration stay separate unfinished work.See the [cache lifecycle design and migration plan](plans/BAIOS-003-cache-lifecycle.md).

## Planned later

- **BAIOS-004: Add SMI and System Management Mode support where hardware permits.** Inventory CPU and controller support, SMI routing, protected SMRAM, entry and resume state, and reset behavior from central references. Design shared services with port-specific hardware adapters. Keep unsupported systems unchanged. Validate interrupt handling, cache coherency, DMA and recovery before enabling a source.

- **BAIOS-005: Add CPU-specific performance initialization.** Detect exact CPU vendor, model and revision before applying documented controls. Cover Cyrix/IBM 5x86 performance registers, Intel P24T Pentium OverDrive enhancements, AMD Am5x86 cache controls, and other supported CPU-specific optimizations. Use the datasheets in `reference/processors/` and record missing references. Respect board wiring, chipset coherency and reset requirements. Preserve conservative defaults and compare cold boot, warm reset, DMA and real workloads. Coordinate cache operations with BAIOS-003 and SMM behavior with BAIOS-004.

- **BAIOS-006: Add optional power management. Very low priority.** Prioritize monitor power saving. Disk spin-down is secondary and remains disabled by default, including for solid-state replacements. Reuse shared services with board-specific hardware support and coordinate with BAIOS-004 where SMM is needed.

- **BAIOS-007: Add boot and Setup passwords. Very low priority.** Define shared password behavior, storage and owner recovery before port-specific integration. This is separate from the current PB430 hardware settings work.

## Accepted residual risk

No residual risk is accepted.

## Declined

No task is declined.

## Completed

- **BAIOS-010: Complete shared PIO0–4 support.** Shared negotiation, command completion, reset restoration and effective-mode reporting cover all maintained ports. Ports can set a mode ceiling and provide controller timing operations. M919 includes PIO3/4 timing and no longer exposes a game-port control. The changed-path checks, ROM integrity checks and final native review passed. Physical PIO3/4 qualification remains separate. See the [PIO plan](plans/BAIOS-010-pio.md).

- **BAIOS-009: Standardize port organization and candidate identity.** Relocated source checkouts, standardized build and diagnostic paths, protected retained inputs and completed candidates, and added version/UTC naming with latest pointers. All four build folders were cleaned. The focused checks and final native review passed. M919 was on hardware hold at this checkpoint; its port roadmap now owns resumed development.

- **BAIOS-001: Move shared tools and dependencies to repository-root owners.** Moved common emulator resources, dependencies, and helper implementations to root owners. Preserved port overrides, existing commands, original references, and approved Presario ROM bytes. Validation and final review passed.

- **BAIOS-002: Organize repository ownership and build cleanup.** Keep build output clean, keep port-specific files with their ports, and organize shared references at repository root. Preserve current ROMs, original inputs, pending review artifacts and current observations. Maintain shared cleanup safety and port retention policies. Keep repository-wide work in this roadmap and port work in its port roadmap.

- **BAIOS-008: Publish a sanitized public source repository.** Published original source under MIT with private history, personal paths, vendor ROMs and manuals excluded. Public CI passes. Main requires the source check and blocks force pushes and deletion, including administrators. Native review passed.
