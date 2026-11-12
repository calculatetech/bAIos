# Boot and resource compatibility


Startup must continue past an empty hard-disk bootstrap. Operating systems must enumerate each bus and controller once. ISA and PCI devices must receive usable resources while respecting manual reservations. ESCD notices must not erase device rows. Version 0.26.24 binds these corrections to one release candidate.

The task base is `6d3e2af2d1002c917c3286aa86f524c10c5bdbec`, on branch `task/boot-invalid-mbr`. Physical iteration preceded this reconciliation under the repository's live hardware rule. The current conversation supplies the accepted results. There are no pending Plan captures for this task. This specification records the final behavior boundaries without changing earlier port plans.

## Owners and limits


Shared boot, PnP node encoding, resource accounting and POST notices retain their existing owners under `shared/src/firmware/`. M919 adapter declarations select PCI enumeration. `hardware/pci-tuning.inc` owns slot wiring and interrupt assignment. `chipset-core.inc` owns migration and validation of the existing saved chipset record. Other ports retain their enumeration declarations and settings layouts. Existing ESCD storage, CPU/cache initialization, timing controls, no-AUX policy and accepted board limitations remain unchanged.

The supported hardware model is the existing M919 port with ISA PnP and PCI devices. Tests distinguish firmware behavior from physical stability. The reported ESS1868 and 3C905C observations qualify that configuration, not all cards or board revisions. The unexplained revision 3.4 reset/floppy behavior and VLB palette issue remain deferred. Original ROMs and captured private resource streams remain outside Git.

## Atomic release boundary


Subtask S1 covers the existing boot selector, public/internal resource ownership, resource solver consumers, final IRQ routing, saved slot policy and POST notice placement. The release boundary is the complete change from the task base. Use one full native correctness review after validation and trace closure. A correction receives a delta review followed by a final complete review. Tests, diagnostic sources, documentation and the release artifact belong to this same boundary.

## Accepted boundaries and scenario proof


Each boundary below maps a reported requirement to its production entry and a named runnable check. The nearest wrong meaning must produce a different terminal result. The examples are independent authored fixtures unless an actual captured stream is explicitly identified. Test results belong to the ignored task record.

| Boundary | Requirement and discriminator | Production entry and terminal result | Exact named check |
| --- | --- | --- | --- |
| B1 | A signed disk sector with empty bootstrap must not trap boot. Contrast empty zero/FF code with nonempty code while retaining the disk identifier and partitions. | `boot_candidate` through `boot_read` either hands off genuine code or advances to floppy/retry. Read failure and INT18 retain continuation. | `python -B shared/tests/test-boot-fallback.py --image m919/build/baios-m919.bin` |
| B2 | PCI owns OS enumeration without losing enabled IDE reservations. Contrast public/private access and primary/secondary enable states. | Public PnP Functions 00/01/02 exclude duplicate IDE/ISA bus nodes. `pnp_seed` still protects enabled IDE ports and IRQ14/15. | `python -B m919/tools/test-pnp-ide.py` |
| B3 | A high PCI I/O interval does not consume a low ISA ten-bit alias. Contrast PCI-origin and ISA-origin claims, true overlap, adjacency and manual reservation. | `pnp_pci_candidate_core` and ISA allocation use `pnp_claim_query`; the preferred MIDI/gameport profile remains 330h/201h unless genuinely blocked. | `shared/tests/test-pnp.py::pci_isa_io_aliases`, `preferred_profiles`, `pci_precedence`, `pci_manual_windows` |
| B4 | Unused links must not spend free IRQs. Contrast one/three active slots, a reserved IRQ, only one available IRQ and no available IRQ. | `pnp_prepare`/`pci_initialize` then `board_pci_runtime_policy` write allowed distinct IRQs before sharing, or FF when none exist. ISA edge state survives. | `shared/tests/test-pnp.py::pci_irq_reservations`, `pci_final_routing` |
| B5 | Slot pin controls use Auto/INTA-D rather than IRQ numbers. Contrast each selected pin and function 0/1. Preserve wiring, sorted choices and other settings. | Native Setup selection/save/load and final router respect the reported pin in Auto, apply function-0 overrides, and retire only legacy IRQ selectors. Invalid new selectors cannot publish. | `python -B m919/tools/test-pci-slot-policy.py` carries all five native choices through Save, a fresh load and routing for each slot, with function 0 reporting INTD and function 1 reporting INTB. `shared/tests/test-pnp.py::pci_irq_settings`, `settings_regressions` cover migration and invalid saved selectors. |
| B6 | ESCD progress stays below the grid without erasing PnP rows. Contrast success/failure, scroll/wrap and a row that leaves the screen. | Resident `post_status` and far `pnp_console_callback` preserve device rows and return state. `pnp_publish_finish` places the notice before the table. | `python -B shared/tests/test-post-escd-status.py`, including `composed`, runs the actual Summary, table, final publication and storage completion with an external VGA text service and flash model. It contrasts successful and failed saved-state writes, natural line wrap, visible scrolling and an offscreen notice. |
| B7 | Retained ROM regions, reset vector, layout and checksums remain valid. | Existing normal builder/verifier produces the same hardware-tested physical image. | `python -B tools/verify-rom.py m919`; `m919/tools/test-build.py` |

All requested behavior clauses map to B1-B7. Rejected contact-related NIC observations are non-boundary hardware evidence. New register tuning, joystick functionality, wider card electrical compatibility and the existing board limitations are deferred. No new behavioral contract gap is introduced.

## Validation


Run the complete declared `m919/validation.json` check list once against the current source, plus the new checks named above. Reuse a passed check until its source, input or oracle changes. Shared source changes also require builds and focused PnP/boot/POST checks for the other adopting ports. Do not rerun an unchanged physical experiment. Compare the final image with its hardware-tested identity before finishing its versioned candidate name.

## Decision Log


PCI enumeration and BIOS resource reservation have different visibility requirements. Keep a private IDE node after the public handle range rather than removing the allocator's onboard ownership. Mark PCI I/O origin inside the ledger rather than changing public resource descriptors. Allocate only active links before sharing. Keep pin overrides separate from IRQ reservations and preserve the packed payload size with an unused marker encoding. Keep all earlier behavior and limitations outside these corrections unchanged.
