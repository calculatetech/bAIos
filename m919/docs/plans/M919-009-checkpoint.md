# M919-009: Replacement-adapter checkpoint

The checkpoint preserves the working M919 hardware result, fixes common owners,
and makes normal Setup defaults consistent. The user can observe CD, floppy,
then hard disk after loading defaults, with supported caches requested enabled
and write-back where the adapter supports that policy. Valid saved settings and
cache-off recovery remain unchanged.

## Sources and reconciliation

Use branch `task/m919-standard-cache` in the primary checkout, based on
`fc170ffe8a6994eb132c82ecbb886601e1988626`. Include the current replacement-adapter
work and its shared fixes in one local checkpoint. There are no pending Plan
captures in `.agent/plan-history/`. The ignored
`.agent/test-results/m919-standard-cache.json` owns operational evidence.

The current user instructions supersede M919-004's profile implementation,
persistent cache certificate, WT default, and hardware hold for this checkpoint.
The replacement uses individual timing controls and full short cache tests.
M919-004's remaining features do not enter this task. Keep the no-AUX rule,
original reference inputs, board-specific hardware sequences, and shared owners.

## Product boundary and preflight

The supported model is one developer, existing local tools, and the documented
ports. Firmware Setup, PCI sizing, disk interrupt/completion handling, adapters,
and their direct checks compose this task. Existing board timing values, cache
qualification, ATA data formats and CMOS layouts are preserved. Wider CPU/SIMM
compatibility, SMI, reset-display repair, new timing controls and publication are
deferred. Fault injection is supporting diagnostic evidence, not physical proof.

Keep generic PCI ROM sizing in `shared/src/pc/pci.inc`; chipset shadow writes stay
in `m919/src/hardware/pci.inc`. Existing shared INT13/INT76 and ATA completion
owners in `shared/src/firmware/bios.asm` and `ide.inc` own disk behavior. Common
default policy belongs in shared Setup sources; adapters map cache policy into
their existing record encodings. Do not add WB controls to WT-only hardware.
Presario's standalone core directly composes the same shared IDE caller but
still duplicates the older polling routines. Consolidate those routines and
the identical IRQ14 handler into shared PC includes consumed by both cores.

## Boundary inventory and Scenario Proof

| ID | Requirement and owner | Discriminator and contrast | Production path and required oracle | Named check |
| --- | --- | --- | --- | --- |
| B1 | Shared CD/floppy/HD defaults, latest user instruction | Missing/invalid saved base versus valid nondefault saved order | `settings_load` returns 3/1/2/0 only for fallback; valid saved order remains unchanged | `shared/tools/checkpoint_proof.py` defaults cases |
| B2 | Same default policy in F9 | Live nondefault values versus draft defaults | `setup_draft_defaults` returns 3/1/2/0 without writing CMOS | Same defaults cases |
| B3 | Supported caches enabled/WB by default; existing recovery retained | M919 normal defaults versus safe recovery, plus existing saved WT | Real `chipset_defaults` maps common policy to enabled L1/L2 and WB; `chipset_safe_defaults` keeps both off; saved record stays unchanged | Same defaults cases and `m919/tools/manual_proof.py` settings cases |
| B4 | Disk-write IRQ fix checked at shared owner | INT13 entry with IF cleared versus actual data-phase interrupt exclusion; composed core versus Presario's standalone caller | Installed INT13 enables IRQ service, PIO blocks exclude interrupts, actual write completes and shared IRQ14 acknowledges both PICs; common delayed/stuck-status polling works in both cores | `shared/tools/ata_completion_proof.py` against both cores |
| B5 | PCI VGA ROM fix shared | No PCI device, 32 KB aperture, 64 KB aperture with 32 KB legacy header, invalid BAR size | Shared sizing restores command/BAR and extends only valid aperture; M919 shadows full extent and scanner skips VGA mirror while retaining real later ROM | `m919/tools/manual_proof.py` aperture cases |
| B6 | Physical evidence and local checkpoint | Confirmed 512 KB WB and ViRGE operation versus remaining reset corruption | README/register ledger retain exact evidence limits; checkpoint stages only owned source and reviewed records | Documentation review, ROM integrity and native checkpoint review |
| B7 | No AUX initialization on M919, AGENTS.md | Normal/default or saved policy on the no-AUX adapter | Existing keyboard/mouse owners issue no A7/A8/A9/D3/D4 commands and preserve keyboard use | `m919/tools/manual_proof.py` no-aux cases |
| B8 | Declared proof entry points run their claimed cases | Executed runner versus uncalled helper | Validation output includes the settings, aperture and public disk-owner cases | Named checks above through their script entry points |

Input-domain cases cover valid saved policy, defaults and supported PCI aperture
sizes. Transition cases cover cold load, F9, disk completion and VGA initialization
through late discovery. ROM collection cases distinguish a VGA mirror from a
genuine later provider. No new handling for unavailable hardware or new services
is introduced. Physical stability is based on the user's tests, not emulator
cache models.

## Implementation and checkpoint boundary

One atomic subtask, C1, covers shared fixes/defaults and the cumulative M919
replacement. Add a small shared policy source, map existing adapter defaults,
factor the existing PCI aperture routine without changing its hardware order,
and make its existing proof cases part of the declared validation entry point.
Both confirmed Setup default actions call one shared default-application owner
instead of duplicating its helper sequence. The defaults proof follows that
owner through save/reload and real boot-source selection. The disk proof enters
public INT13 with architectural IF cleared rather than pre-enabling interrupts.
Record the ViRGE reset caveat and measured Bank 0 byte/socket map. Preserve the
physically tested 0.3.14 image in `build/review/` before rebuilding a new candidate.
Increment the affected port version for changed normal defaults.

Run the named checks above, the current supported M919 adapter checks and ROM
integrity, and compile directly affected ports. Do not repeat unchanged passing
checks unless their source, image or asserted outcome changes. Resolve obsolete
fixtures only within this checkpoint's supported replacement behavior. Run fresh
boundary trace closure and native checkpoint review of the staged cumulative
tree before the local commit. Do not push, merge, release or start remaining
features as part of C1.

## Decision Log

The selected SRAM population establishes a working 512 KB WB baseline. Twelve
rejected chips do not establish twelve dead chips or a vendor-wide incompatibility.
ViRGE is usable with reset corruption still present. The latest user request
restores WB as the normal default. Hardware adapters retain policy limits and
safe recovery. The checkpoint does not claim the remaining port feature plan is
complete.
