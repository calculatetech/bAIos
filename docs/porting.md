<!-- cpk-rule-owner: reference-first-porting -->
<!-- cpk-rule-guard: Establish a physically bootable reference-based port before experimenting with universal hardware methods. -->
<!-- cpk-rule-guard: Exclude donor hardware initialization from a new port unless target-specific evidence establishes that it applies. -->

# Reference instructions for new ports

Read this document before selecting source for a port. Apply it to the Presario, M919, PB430, and future donors.
The modular base supplies reusable services. It does not establish that donor hardware setup works on another board.
The [repository cache rule](../AGENTS.md#reference-cache-setup) owns the requirements for matching the reference cache sequence.

## Establish the hardware baseline first

Build the first working port around the target's working BIOS and hardware documents.
Keep its hardware sequence intact while connecting the established bAIos services and presentation.
Do not replace a target sequence with a proposed universal method during initial bring-up.

A fully bootable baseline physically completes normal POST, supports Setup Save/reset, and boots the intended medium.
Use the selected reference hardware configuration for this result. A boot with cache disabled does not establish a working cache baseline.
Record the observed result and its limits. Emulator boot and synthetic test success do not satisfy this gate.

Only after the physical baseline works, experiment with universal hardware methods in a separate change.
Keep the working baseline reachable in Git and preserve its selected test image under the port's retention policy.
Do not turn an unbootable port into an experiment in shared hardware abstractions.

## Select donor code by its ownership

Record the source of every imported or adapted hardware owner in the port's evidence document.
Identify the exact file or ROM range and the target evidence that supports its use.
Use these defaults until that evidence exists:

| Source | Initial-port rule |
| --- | --- |
| Shared POST rendering and established Setup mechanics | Reuse the existing presentation and interaction. |
| Shared PC interrupt services, disk services, and boot policy | Reuse the service, then prove its target hardware assumptions. |
| Donor reset, DRAM mapping, cache, shadow, clock, turbo, A20, interrupt routing, and Super I/O setup | Exclude the implementation. Derive the target owner from its references. |
| Donor cache wrappers, CPU-cache policy, helper timing, and save/restore conventions | Exclude the sequence until comparison with the target reference establishes compatibility. |
| M919 modular organization | Reuse its separation of owners. Its unfinished hardware policy is not a template. |
| New abstractions or universal initialization | Defer until the target meets the physical boot requirement above. |

If donor-derived code fails on the target, record its source and exclude that implementation from the next port's starting set.
If newly written code fails, identify it as newly written. Do not assign its failure to a donor without evidence.
An x86 instruction can be supported while its ordering within a hardware sequence is wrong.
Do not label `PUSHAD`, `WBINVD`, or `INVD` universally unsafe from one stopped image.

## Read the complete reference sequence

Follow the target's caller, prerequisites, hardware operations, and return path before writing the replacement.
Include cold entry, warm entry, disabled states, and the transition back to normal services.
Record any remaining difference from the reference before producing a candidate.

Make sure that the comparison covers:

1. Register indices, values, masks, table selection, and I/O delay cycles.
2. CPU cache state before the transition, invalidation instructions, and final state.
3. Interrupt and NMI handling before, during, and after the transition.
4. Stack location, access widths, saved registers, caller state, and return instructions.
5. Address and operand sizes, complete memory ranges, iteration counts, and final accessed addresses.
6. Reference configuration storage and its explicit mapping to bAIos configuration storage.

Match the whole owner before asking for hardware tests. Matching the middle register writes does not establish a matching return path.
Compare the physical stack addresses as well as the saved register list. Include parent frames and calls added by modularization.
Keep source ordering even when later writes overwrite the same registers. Equal final values do not prove equal hardware transitions.
Compare register reads, index selections, and individual delay cycles as well as data writes. Keep reads whose returned value is discarded.
When private CMOS facts move into bAIos state, preserve the NMI masking caused by their original index selections.
Keep necessary state-format adaptations separate from changes to hardware behavior.
Do not write reference BIOS private CMOS flags over bAIos configuration records.
Capture the hardware state that actually reaches the owner. An isolated test with chosen register values cannot establish that entry state.
Include adjacent memory-controller and shadow routines in that comparison. A required cache input can be programmed by another owner.
Exercise the cold path from the reset vector through DRAM detection. A Setup-triggered warm reset does not cover that path.
Exercise reset after caches are active. Preserve valid detection before rebuilding BIOS state, and follow the target's warm-entry sequence.
Compare flush instructions across warm-entry tag-state changes. A redundant cold-path flush can introduce an unsupported warm-path operation.
Include reset-time board I/O before reading inputs for clock and cache table selection.
Trace the restart producer as well as the reset consumer. Preserve service-selector clearing in intentional normal restarts, and test genuine service resumes separately.

## Prove what the references actually establish

Decode complete ROM and document formats before selecting extraction or conversion tools. Preserve the original inputs.
Keep generic manuals in categorized root `reference/`. Keep board inputs and board evidence in the port.

Treat RAM probe codes as observations until physical counting establishes their capacity.
Prove the low workspace and stack before using them. Account for reserved BIOS state in public memory counts.
If a reference lookup has an ambiguous or defective fallback, record it. Do not silently assign a plausible result.

Separate cache presence, qualified capacity, requested configuration, and effective enablement.
Preserve undocumented fields. Do not invent timings, hardware capabilities, or register encodings to complete a menu.
Use the controller's actual variant and reserved-bit rules. An emulator's implementation does not override its data sheet.

For video and option ROMs, prove the complete declared image, its mapping, and its callable entry.
Preserve the established display and interrupt-vector behavior. Validate physical far-pointer destinations, including equivalent segment aliases.
Trace fallback calls after initialization as well as installer calls. Do not alias a fallback vector to a handler that calls it.
Include unsupported video probes such as INT10 AH=FE and AH=FF. A correct POST screen does not prove that DOS application startup will return.
Keep the complete initialized provider extent out of later option-ROM discovery.

## Use diagnostics without changing the operation being diagnosed

A POST code identifies the last executed marker. It does not prove that the owner returned or that hardware is stable.
Do not use an unrestricted live register value as a phase marker. Derive preservation from the helper's returned registers, not its call arguments.
Place markers at owner entry, return, and service handoff. Interpret reused codes with their preceding phase.
Do not add a stack access or change a cache-sensitive loop merely to emit a marker inside a stock transition.
Keep diagnostic writes outside the stock interrupt window. Prove that each marker preserves live registers, flags and stack accesses.
Distinguish normal reset from special service-resume paths before calling a missing screen a skipped POST.
Distinguish a stalled display from a hard CPU freeze. Record keyboard response and whether the next failure follows a warm reset.

Distinguish source-backed corrections from hypotheses in the diagnostic record.
A source difference is not proof of the electrical cause of a halt.
Do not turn an unsuccessful workaround into a permanent porting rule.

Compare the unmodified reference code with assembled port code when practical.
Keep added diagnostics outside temporary cache modes. Compare the uninterrupted reference transition, including all I/O. Ignoring a POST write because it preserves registers does not prove equivalent bus activity or instruction fetching.
Map platform prerequisites before comparing the cache body. Refresh, DMA cascade, shadow state, and both reset producers and consumers can precede the apparent owner.
Trace reset pulses inside POST, including shutdown codes and saved return addresses. A self-test can resume after cache sizing with different hardware state. A comparison that joins isolated routines must account for those intervening paths before claiming equivalent entry state.
Separate mandatory RAM initialization from optional RAM testing. Trace what the reference skip path still writes. Require cold initialization before any skip can reach cache activation, and preserve warm retained-memory behavior. A donor's non-destructive test does not supply this prerequisite when the user can interrupt it.
Keep a reassemblable reference map with original offsets, entry evidence, inline data, and unresolved indirect transfers. A linear decoder can treat ROM return words or strings as instructions.
Do not equate two chipset implementations because they share an I/O pair or register numbers. Compare their callers, fill ranges, CPU invalidation, and flag contracts first.
Exercise register operations, CPU state, interrupts enabled and disabled, returned registers, stack position, and continuation.
Use nonzero register values so that a broken return does not pass because the fixture starts at zero.
Compare the complete reference parent and its continuation, not only the cache body's return. A parent can still change controller pins and NMI state.
Match pre-reset cache teardown to the reset mechanism actually used. A reset pulse and a software restart can have different reference prerequisites.
Test saved cache changes across a complete reset, in both directions. Retained SRAM qualification does not prove that cold tables match a new L1 or L2 choice. Preserve the active record for teardown, compare it with effective saved choices, and select full reference initialization when needed. Also test unchanged Save, Discard, canceled Save and a rejected Save that already published part of its record. A later reset must use what actually persisted.
Audit inherited cache flushes at the common reset entry as well as inside the board's cache owner. Match the target's CPU-cache disable instructions and preserve required holdoff before RAM work. Record any changed placement. Reset invalidation does not establish a safe replacement for runtime dirty-data write-back.
Set segment registers and the BIOS-state address to their actual entry values.
For a cache-sensitive reference routine, check byte identity as well as decoded instructions. Equivalent encodings can change the instruction stream.
Test reset with a working boot device before and after restart. An empty-machine test that expects boot failure cannot prove device retention.
Make fixtures accept the target's documented I/O behavior instead of changing firmware to satisfy donor fixtures.
Inspect which register effects the emulator actually implements. A named board model can omit the cache-tag or memory-controller behavior under diagnosis.
Exercise interrupts inside the actual enabled window. An interrupt after the transition does not cover service accesses during transient cache modes.

Compare the handlers reached in that window, including their memory addresses, device accesses, stack use, hooks, and PIC acknowledgement. A shared timer that works after POST is not automatically safe during tag initialization. Reject unexpected high-memory accesses in the focused test; ordinary RAM returned by an emulator does not qualify those accesses on physical cache hardware. Preserve the target's handler behavior before experimenting with different interrupt masks.

The [live hardware rules](../AGENTS.md#live-hardware-iteration) own candidate checks and the hardware-test handoff.
Follow their programmer-checksum requirement. Keep source identity hashes in internal evidence.
Keep the observed hardware result distinct from software or emulator results.

## RAM tests, timing trials and recovery

Reuse the established POST and Setup interaction, including early RAM testing on both cold and warm starts. Verify actual call order through peripheral initialization. A test that moves after floppy seek no longer follows that baseline.

Apply the selected DRAM timings before testing them. Hold CPU and external caches disabled during a DRAM test unless a target-specific method proves that every tested access reaches RAM. Test cache hardware separately. Preserve the current block before Pause, Esc, Delete or an error leaves the loop. Delete must reach the existing Setup gate without leaking a pending key into DOS.

Keep mandatory reference memory initialization separate from optional testing. Fast Boot and skip keys can shorten tests, but cannot bypass initialization required by later cache activation. Continue to report the detected RAM total.

Reuse the existing recovery owner and retry limit. Arm a persistent timing trial before risky settings take effect. Keep it pending through all later POST stages that use those settings. A detected failure must restore safe hardware state before retry. An unfinished trial on hard reset must select safe defaults early enough to regain Setup. Clear the recovery guard only after a verified save. Test rejected saves and Discard as well as successful saves.

Prove deliberate warm reset and reference service-resume paths separately from failed-trial hard reset. Restore reference prerequisites before the stock cache sequence, then apply runtime choices through their existing owner. Derive the restoration order from the target's timing dependencies, not from the donor's register numbers.

Use tests that observe actual memory reads and writes, cache state, restored data, persistent markers, and the terminal Setup or boot path. A passing component test or RAM loop cannot prove the complete recovery sequence. Label physical timing and long-term stability separately from software validation.

## Carry lessons forward

When a port exposes a new reuse failure, update this document and the port's evidence before handing off the next candidate.
Record the source, observed result, required exclusion, correction status, and remaining physical uncertainty.
Preserve rejected hypotheses as rejected findings when they prevent repeating the same mistake.
Do not copy board-specific register recipes into this project-wide guide.

The current worked example is [the PB430 porting lessons](../pb430/docs/porting-lessons.md).
Its physical results qualify only the tested PB430 configuration. They do not make its hardware owners portable to another chipset.
