# M919-004: Memory and cache profiles


Reuse the Presario RAM profile system and preserve its screen layout, colors, columns, help, and save/default/discard behavior. Put all nine memory controls on one page. Extend the configured profile clocks to 25, 33, 40, and 50 MHz. Add the supported UMC memory/cache controls. Service the pending Setup request immediately after the visible RAM test. Run L2 qualification after that Setup gate, hide L2 enabled status until Summary, and retain successful validation so unchanged boots skip the expensive full test. Show L2 Cache Test on the next POST row below RAM banks only when full qualification runs. Change Testing... to Passed after success.

## Sources and reconciliation


The base is `deb988c46833f5b2deef6b23f461b3010d64e79c` on `task/m919-kickoff` in the primary checkout. The port roadmap owns lifecycle state. The ignored `.agent/test-results/m919-timing.json` owns commands and results.

Carry the complete donor, no-AUX, hardware adapters, protected inputs, ROM layout, recovery, and standard services from [M919-002](M919-002-post.md) and [M919-008](M919-008-hardware.md). Current user instructions supersede the earlier timing deferral, late L2 qualification order, and full qualification on every boot. They do not authorize changing Presario's approved firmware or shared floppy/DMA policy. Broader physical timing margins remain M919-005.

The Presario authorities are `presario-800/src/chipsets/vl82c481/setup-data.inc`, `setup-policy.inc`, and `policy.inc`. Use its profile interaction and presentation, not its VLSI register bytes. The board manual `m919/docs/user-manual.pdf`, PDF page 4, lists the four bus inputs separately from multiplier jumpers. A profile clock is configured input; it neither detects nor programs clock hardware. Keep shared processor recognition unchanged.

The pinned UMC manual is `reference/chipsets/umc/um888x/UMC_chipset_technical_reference_manual_RE.md`. Native September 1998 AMI handlers at 25EA..2678 confirm HB50.30 burst, HB51.F0 waits, HB50.40/HB51.01 cache-mode pairing, HB52.80 posted writes, and HB53.C0 burst/copyback controls. Handler 20EF..20FC confirms the EDO selector writes HB61.C0. The native RMW helper at B8B0 preserves masked bits. The automatic table at BADA uses 30-byte rows. Its rows 1/2 supply burst20/waitsF0 for the nominal 25/33 entries; rows 3/4 supply burst00/waits50 for 40/50. The CPU-dependent automatic selector is not a bus-speed detector.

## Product boundary and owners


M919 chipset policy, profile tuples, cache controls, CMOS validation, and cache rendering compose this change. Shared POST order, existing descriptor menu mechanics, and a small stateless CRC32 helper compose its direct needs. The CRC32 value identifies the actual 64 KiB system ROM; it is an integrity fingerprint, not a security claim. Existing RAM mapping/testing, BIOS services, CPU identification, device routing, ROM shadow ownership, and Presario firmware remain unchanged except the explicitly selected M919 POST hook. Keep all model/version data in configured owners.

Use the existing 24-byte chipset record. Keep its first three active policy meanings. New tagged records store timing/profile choices and a validation certificate in the remaining bytes. Validate ranges, legal encodings, and preset/raw tuple coherence. Read the old 55h record only after checking its original checksum/masks, preserve its waits/L1/L2 choices, and migrate it to Manual with configured 33 MHz/Unknown speed in RAM. Do not write on load. D2 recovery selects Compatibility with L2 disabled and no certificate. Validate a saved preset encoding before normalizing Fast if changed hardware removes its benefit. Preserve other accepted settings. Reuse also requires the active tuple to match the stored record checksum.

## Option inventory and profile policy


Expose the profile inputs `Timing Profile Clock`, `DRAM Speed` (Unknown/60 ns/70 ns), and `Memory Timing` (Normal/Compatibility/Manual/Fast). Keep the Presario Profiles header and first three rows. Use full DRAM wait-state labels and numeric choices from 0 through 3. List Enabled first in every binary popup without changing saved encodings. Normal and F9 defaults enable L1 and request L2 enabled in WT mode. This supersedes the WB default because physical WB boots fail or hang. Saved explicit WB requests remain selectable. Safe recovery disables both caches. Port capability policy hides unsupported controls and excludes them from keyboard navigation. Unknown selects the 70 ns row. The retained AMI table has no DRAM-nanosecond split, so both known speeds use the same source-backed Normal tuple; do not invent distinct timing margins.

| Category | Control | Owned bits and evidence |
| --- | --- | --- |
| Memory | Read/write waits | HB51.C0/30; manual and AMI 25FC..2615 |
| Memory | FPM/EDO selector | HB61.C0; AMI 20EF..20FC |
| Memory | EDO burst speed | HB61.08; pinned manual |
| Memory | Normal/slow refresh | HB5D.10; pinned manual; AMI clears it at26F3..26F9 |
| Memory | Memory parity | HB5A.10 plus system-port-B bit04 reporting gate; pinned manual and Presario policy665..674; initialize RAM parity before unmasking the existing shared NMI owner |
| Cache | CPU L1 enable | Existing CR0 policy, independent of L2 |
| Cache | L2 enable | Existing measured/qualified gate |
| Cache | Read burst | HB50.30; four documented cycle sequences and AMI mask |
| Cache | WT/WB policy | HB50.40 paired with HB51.01; AMI2621..263D |
| Cache | Early cache write | HB5D.80; pinned manual |
| Bus access | CPU posted writes | HB52.80; AMI264F..265D; preserve geometry |
| Bus access | CPU burst writes/copyback | HB53.80/40; AMI2660..2678; preserve geometry |

Keep memory geometry and cache size/bank mapping measured. Do not expose raw size overrides, unknown bits, HB51.02 CPU write-policy polarity, HB62's AMD-sensitive burst mode, SMM, or voltage/multiplier controls. ROM cacheability has incomplete address/protection semantics in the current evidence; memory holes change the established memory/service contract. These are deferred rather than given guessed controls.

Normal uses the retained AMI wait/burst tuples above. Compatibility retains the physically successful conservative waits00/burst00 policy at every configured clock. Fast uses the documented minimum waits and fastest burst encodings, without claiming physical margins. Offer Fast only where its tuple can improve an enabled SRAM path or the selected RAM waits; retain donor unavailable-field behavior when no improvement exists. Manual preserves raw timings. Presets lock their owned raw controls; an explicit cache burst edit becomes Manual. Other independent controls remain selectable. F9 normal defaults and recovery Compatibility are distinct owners.

## Implementation boundary


This is one atomic implementation and review boundary: the timing choices, actual qualification, persistence, and final enable must agree before a checkpoint can be useful. Run one complete validation, fresh trace closure and native full review before the local commit.

P1 adds the profile/options, validated record migration and masked register application. Reuse existing shared descriptor renderers and move ordinary reusable enum edit mechanics into the shared Setup owner when needed. M919 supplies profile tuples and hardware-specific commit/editability callbacks. Preserve preset/raw tuple coherence through popup, arrows, defaults, save/reset/reload, and discard. Parity remains inhibited while data is initialized. Reuse the donor's parity reporting sequence after RAM/shadow initialization; a skipped RAM test needs a nondestructive initialization pass before enabling checking. Verify the effective controller and port-B gate together, not readback alone.

P2 adds a board-selected POST hook directly after `chipset_visible_ram_test`. M919 qualifies or reuses validation there, leaves L2 off through the existing final Setup gate, and performs final operational enable at the established late owner. The qualification and enable paths use the same selected burst/mode/early-write policy. Restore selected L1 and all scratch/gates on every path. Retain the fresh native discovery protocol each boot. Do not bypass its unresolved physical initialization effect. Suppress the complete early L2 line; Summary reports measured capacity and the effective state.

P3 speeds up full pattern writes without reducing tested capacity, opposing patterns, address independence, retained failure values, or tag/coherence checks. Compare executed work at equal512KiB coverage. Persistence removes repeated full qualification: publish a certificate only after a completed successful full qualification. Bind it to the checksummed memory/cache settings record, rediscovered RAM/cache map, CPU identity available to this firmware, and actual system-ROM CRC32. A changed map, new ROM, invalid/default/recovery record, failed qualification, or changed saved memory/cache parameter forces full testing. Entering Setup, discarding edits, canceling defaults, and an unchanged save preserve validation. A changed memory/cache parameter clears it before publication of the new accepted settings. The existing chipset save owner can compare its complete active and draft option set. The shared verified save flow remains authoritative. Disk, ports, theme, and immediate date/time edits are outside this result's input domain because they do not alter memory/cache operation; ordinary RTC ticks never invalidate it. The user explicitly confirmed memory/cache settings only.

The certificate reduces repeated testing; it does not certify continuing health of a same-identity chip. Keep absent cache off and preserve acknowledged safe recovery with bank/byte/socket-group localization. Explicitly saving Enabled after recovery must qualify again. WB has the native seven-tag/dirty-bit policy and a capacity-times128 cacheable range, versus times256 for WT. Keep early hardware in WT. Prime clean tags in WT before switching to the selected WB mode in qualification and final enable. The AMI 297A..299E WT sequence and 2621..263D selected-mode handler own that order. Qualify the selected mode, flush the cache through existing POST bus cycles, and keep the proven runtime DMA service untouched. Extend the external SRAM seam to model dirty L2 independently of L1 policy. It must write back on eviction/flush, respond to modeled master transactions, and preserve dirty data through the actual warm-reset owner. Negative external coherence/writeback contrasts must disprove stale or lost data. These are software hardware-contract checks, not physical snoop measurements. The warm-reset adapter keeps its write-back flush and reopens fast A20 before the 8042 reset pulse. The native warm case also boots real DOS/HIMEM from floppy through Ctrl-Alt-Delete, where HIMEM closes the A20 gate.

## Boundary inventory and Scenario Proof


| Boundary | Requirement/discriminator and contrast | Production path and terminal oracle | Runnable check |
| --- | --- | --- | --- |
| B1 | Every accepted option versus a later omitted descriptor; owned masks versus seeded unrelated bits | Real field edit/save/reset/reload reaches every independent expected register mask, preserving geometry and other settings | Extend `cache_proof.py cache-settings` with option inventory; `test-build.py`; `test-reference.py` |
| B2 | Preset versus Manual; Normal/Compatibility/Fast; Unknown versus70ns | Actual RAM profile screen matches donor positions/attributes/navigation; preset metadata and raw tuples agree; Manual preserves chosen raw timings | New `timing_proof.py timing-settings` and native Setup capture |
| B3 | All four configured clocks, including40/50 after a duplicate prefix | Real popup/save/reload indexes each independent tuple and shows configured-input help; no clock/multiplier writes | `timing_proof.py timing-settings` |
| B4 | Old55h/new valid versus foreign, first-invalid selector and incoherent preset | Real settings load and save/default/discard reach correct active bytes/checksums and hardware policy; legacy settings survive | `timing_proof.py timing-settings`; existing `cache-settings` |
| B5 | RAM completion followed by early qualification versus the old late path; two distinct timing tuples | Actual reset traverses RAM test then qualification before peripherals; exact selected timing bits match final enable; Setup gates remain reachable | Extend `cache_proof.py cache-policy`; `timing-order` |
| B6 | Enabled/disabled SRAM at the same early stage, then Summary | Pre-Summary cells contain no L2 label, capacity or state; Summary reports capacity and WT/WB/Off with existing styling | `timing_proof.py timing-order`; `test-post.py --case setup` |
| B7 | Passed persistent certificate versus missing result | Complete first POST writes success; cold/warm reset clears volatile state and unchanged matching inputs skip full work but safely reach final enable/Summary | New `timing_proof.py cache-persistence` with work counters |
| B8 | Changed saved memory/cache field versus draft-only edit/no-change save; accepted/canceled F9 and unrelated changes | Real Setup edit/save/discard/reset/reload clears or preserves the certificate and visits actual qualification exactly when required; unrelated disk/theme/clock edits preserve it | `timing_proof.py cache-persistence` |
| B9 | Same settings versus changed measured map, CPU identity or ROM | Real startup producer and fingerprint comparison reject stale reuse; independent CRC vectors and a changed ROM byte disprove a constant result | `timing_proof.py cache-persistence`; compiled CRC helper check |
| B10 | Full passing capacity versus data/tag/WT/WB failure, absent SRAM and explicit retry | Qualification retains every tested dword and expected/observed fault values; safe notice/key/reset disables cache and invalidates success; Enabled save causes a fresh pass | `cache-live`; `cache-discovery`; `cache-recovery-boundaries-live`; `cache-persistence` |
| B11 | RAM pass versus real Esc/Delete/Pause/recovery | Restore RAM/machine state; Delete/changed save/reset reopens qualification with new settings; no aborted qualification publishes success | Existing `test-hardware.py --case ram-test` and composed timing/order cases |
| B12 | Equal full coverage versus faster full/repeated work | Exact512KiB address sets and restoration survive while measured firmware instruction work decreases; unchanged certified boot skips the expensive loops | `cache_proof.py cache-live`; `timing_proof.py cache-speed`; `cache-persistence` work comparison |
| B13 | Parity enabled/disabled, full/skipped RAM test, independent parity status | Real setting/save/reset initializes data and reaches the effective HB/port-B gate; later installed NMI sees parity status and reaches E8/message/halt; Disabled remains masked and unrelated bits survive | New `timing_proof.py timing-parity` |
| B14 | Dirty L2 WB versus WT with L1 policy held constant; lost-writeback/unsnooped external contrasts | Actual selected cache policy through eviction/flush, both installed INT13 DMA directions and real warm reset preserves data/status; independent defective hardware contrasts fail | Extend `cache_proof.py cache-dma`; new `cache-writeback` |
| B15 | WB at its tag limit/beyond it versus WT with the same RAM | Real POST applies the selected tag width, qualifies safely, and reaches correct enable/Off and Summary; independent tag model exposes aliasing beyond its supported bound | New `timing_proof.py cache-writeback` |

The complete M919-008 matrix remains the regression floor, with changed ordering/schema/presentation assertions updated to the new accepted behavior. Test hardware seams replace opaque SRAM/tag/controller behavior only. Do not replace firmware decisions or set their final result in a fixture. Use individual input, state transition, and complete field/clock collection contrasts rather than a Cartesian product. Record each actual named result in the ignored task file before independent trace closure and native review.

`timing_boundaries.py` supplies additional composed evidence within this inventory. `profiles` covers B2/B3 through actual popups, save/reset/reload, rendered configured-input help, and the clock editor's I/O surface. `masks` covers B1/B5 with seeded unrelated bits, preserved port B, and the selected qualification/final-enable tuple. `checksums` covers B4 with corrupted old/new checksums. `persistence` covers B8/B11 with an unrelated disk save, the last option-byte change, and real mid-RAM Delete followed by changed save/reset/fresh qualification on present SRAM. `parity-halt` covers B13's installed NMI message/code/halt. `tag-range` covers B15 with a cacheability aperture independent of tag width, an actual CPU guest exposing the WB/WT alias contrast, and the real beyond-limit Off gate. These checks do not add or reinterpret a boundary. `timing_proof.py timing-review` checks the single memory page, ordered numeric and binary choices, preserved record encodings, and real F9/save/reload/qualification with the WT default.

## Decision Log


Reuse established legacy profiles, chipset masks, and a conventional CRC32 fingerprint. The approach is fixed legacy BIOS work; no open architecture or arXiv algorithm selection is needed. The ROM fingerprint is necessary to prevent an old successful test from surviving a different flashed implementation with unchanged version text. Keep safe defaults distinct from Normal and keep hardware identity comparisons based on measured producers. The earlier full qualification proof remains required for first/changed boots; the new persistent reuse result intentionally reduces repeated health testing.

## Handoff


Use PowerShell without profiles and Python with `-B`. Keep generated artifacts under `m919/build`. Retain the current approved candidate until a replacement passes size/layout/checksum, retained-region and reset-entry checks. Finish substantive docs, full named validation, fresh boundary closure, and native review before the local checkpoint. Clean disposable VMs/media and consumed task helpers. Report the exact physical image, programmer sum and SHA256, with software and physical observations kept distinct.
