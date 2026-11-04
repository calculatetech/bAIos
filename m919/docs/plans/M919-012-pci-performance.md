# M919 PCI performance production checkpoint

The user requests a production release of the confirmed register findings, with conservative RAM and cache defaults. Cyrix tuning follows this release. The user reports successful tests at 40 MHz with PCI graphics. VLB palette corruption remains an accepted limitation, also reproduced with the original BIOS.

## Implementation scope

Use the existing startup, chipset, Setup, saved-settings and PCI IDE owners. Remove the Register Lab, its cold-start CMOS wipe, aggressive defaults and temporary shared hooks. Remove unsuccessful PCI comparison overrides. Keep the confirmed IBC41 bit 0 and IBC45 bit 3 settings, clear the known-bad IBC83 bit 6, preserve IDE42 bit 6 clear, use 2 T2 local sampling, and establish saved bus clocks before PCI/VGA. Preserve normal CD/floppy/hard-disk boot defaults, Fast Boot Off, WB caches and persistent settings. Use 2 BCLK ISA I/O recovery as requested, with the conservative ISA divider.

Keep the already implemented secondary IDE disable control and fixed COM/LPT selectors. These use the existing packed settings record and shared Setup renderer. Do not change cache initialization, CPU support, PS/2 initialization or undocumented controls beyond these findings. Research tools remain diagnostics, outside the production firmware.

This finalization is a strict simplification of the tested bench implementation: no new interface, storage, dependency or supported use case. The preflight challenger exemption applies. A previous challenger launch failed without creating an agent. Validation and independent review remain required.

## Accepted boundary inventory and scenario proof

| ID | Requirement and discriminator | Contrast and production path | Oracle and exact check |
| --- | --- | --- | --- |
| B1 | Production boots retain saved settings; no laboratory reset policy. | Cold versus warm KBC state through `startup.normal`, then saved settings reload; invalid settings use normal defaults. | CMOS bytes retained on valid boots, lab code absent, conservative defaults and normal boot order. `m919/tools/test-production-policy.py`. |
| B2 | Confirmed bridge fixes apply before PCI/VGA without destroying peer bits. | Opposite initial bit states through `chipset_initialize` and `startup.pci_policy`. | IBC41.01 and IBC45.08 set, IBC83.40 clear; other byte bits preserved except established owner masks. `m919/tools/test-production-policy.py`. |
| B3 | Saved clocks apply before peripherals and retain the same late result. | Keep Current versus explicit divider; valid versus invalid packed settings. Startup through `chipset_early_bus_timing`, then late tuning. | No CMOS writes; correct divider/peer bits and late consistency. `m919/tools/tuning_proof.py --case early-bus`. |
| B4 | Secondary IDE can be disabled independently; physical positions retain ownership. | Both Channels, Primary Only, Disabled through Setup arrows/popup, save/reload, PCI initialization, detection, runtime access and IRQ reservation. | Only selected channels decode/respond; disabled positions receive no task-file traffic; primary PIO4 remains usable. `m919/tools/test-ide-channels.py`. |
| B5 | All supported COM/LPT choices are reachable, sorted and retain saved encodings. | Every address/Disabled through arrows and popup, save/reload and Super I/O application. | Correct text, no skipped choices, existing encoding and unrelated saved fields preserved. `m919/tools/tuning_proof.py --case t4-policy --case device-commit`. |

The physical performance and crackle findings are observed hardware evidence, not claims proved by an emulator. Unknown electrical meanings remain opaque. VLB palette repair and Cyrix performance are deferred by the user's release direction. Artifact size, bank checksums, reset vector and retained cache/SMM code are integrity invariants checked separately.

The production checkpoint is version **0.18.2**, following the 0.18.x bench feature line. Shared Setup fixes also increment Presario 800 and PB430 to 0.4.1 and MP386 to 0.5.1. Their hardware behavior outside the shared menu changes is unchanged.

## Delivery

1. Simplify the candidate and select its next version.
2. Build once; run the declared M919 validation matrix and the focused boundary checks. Check affected shared consumers without repeating unchanged suites.
3. Update the port manual, research findings and roadmap. Keep technical evidence in developer documents.
4. Complete boundary trace closure and native review of the staged source. Correct in-scope defects, then publish the reviewed source and completed ROM.

Operational results, exact commands, review trees and release status belong in the ignored task result, not this specification.
