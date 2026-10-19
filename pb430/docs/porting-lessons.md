# PB430 lessons for the next port

The [project porting instructions](../../docs/porting.md) own the rules for future ports.
The PB430 now boots on the tested hardware. The user reports a 24% average benchmark improvement over the stock BIOS. The separate RAM throughput test rose from 13.6 to 17.3 MB/sec (27.2%), with effective read/write access times of 242/121 ns. The benchmark set and complete winning settings were not supplied, so these are user observations rather than a reproducible performance profile.

The cold-start freeze was resolved by matching the stock reset-and-resume state before cache activation. The working image retains the other reference-sequence corrections described below. Their individual contributions were not isolated. Subsequent timing work must preserve that complete baseline.

The Microsoft Plug and Play manager reports `no escd.rf file found`. Its behavior with the stock BIOS is unknown. Investigate this separately after the firmware review; do not assume that a missing DOS file proves a BIOS defect.

## RAM testing and recovery

The Presario supplies the POST interaction and recovery pattern. Target hardware restoration remains the port's responsibility. The PB430 implementation uses these rules:

1. Apply selected DRAM timings before the visible RAM test. A test under stock timings cannot qualify the settings that run afterward.
2. Keep both caches disabled during the DRAM test. Cache hits can hide DRAM accesses, and extra cache-eviction scans made the PB430 test slower. This RAM test does not qualify L2.
3. Keep the original early POST order on cold and warm starts. Test RAM before peripheral initialization and floppy seek. Delete must restore the current block and reach the established Setup gate. Preserve Pause, Esc and Ctrl+Alt+Del handling.
4. Complete mandatory cold memory initialization even when Fast Boot or Esc skips optional testing. A non-destructive test cannot replace initialization required by the reference cache fill.
5. Arm a persistent trial marker before applying experimental timings. Clear it only after POST completes the later cache, summary and clock stages. Passing the RAM loop alone is not completion.
6. On a detected RAM error, restore the tested block and stock timings before the existing safe-default restart. Permit one recovery attempt. A second failure must stop rather than loop forever.
7. On a hard reset with an unfinished trial, restore safe timing before memory use and enter the existing recovery path with L2 disabled. A verified Setup save permits another trial. Discard or a rejected save must not clear the retry guard.
8. Treat deliberate Ctrl+Alt+Del separately: restore the hardware and clear the pending trial before restarting with the saved choices. Service-resume entries must retain their distinct reference contract.
9. Restore all reference prerequisites before the late stock cache sequence, then reapply selected runtime timings. Do not splice experimental writes into temporary cache modes.

PB430 timing restoration lengthens CAS before removing the earlier pulse. This ordering is board-owned, not a generic recipe. Recovery state uses the existing CMOS and reset owners. The live settings record and its checksum must remain valid when the marker changes.

The focused checks are `tools/test-timing-recovery.py` (data restoration, selected timings, cache state, keys, failed-trial reset and retry guard) and `tools/test-ram-order.py` (cold and warm POST through RAM, floppy setup, reference cache prerequisites and boot). Keep the distinction between a detected test error and a CPU lock that cannot execute recovery. Hardware Reset is the recovery event for the latter. A short POST test cannot prove long-term timing stability.

## Timing and menu lessons

Use the related ACC2046/2087 tables as explicit hypotheses, then compare live registers and measured results. Do not transfer VLSI bit encodings. The Presario's clock-budget method remains useful: translate cycles at the controller clock, account for pulse advance and address setup, and distinguish DRAM row-access ratings from CAS timing.

On this PB430, Earlier Read Pulse Timing allowed Read CAS Width 1T. Earlier Write Pulse Timing allowed Uncached Write Wait 0 WS. The two fields in each pair must be considered together. The 1T read-precharge label is inferred; the ACC2087 table explicitly describes only the 2T state. The original claim that 512 KiB alone caused the slowdown was contradicted by the user's 128 KiB comparison.

Keep each timing in one clear menu location. Remove obsolete shortcuts when the individual controls exist. Put parent and dependent burst choices together and preserve saved child values while editing is unavailable. Explain tested pairings in plain Setup help, and keep uncertain register semantics in developer documents. Do not replace manually selected winning settings with a newly guessed default profile.

## Historical bring-up observations

The following records describe earlier failed candidates. Later sections state which corrections received physical confirmation. They do not describe the current port's acceptance state.

Cold boot initially succeeded with L2 enabled, while cache stability and warm-reset acceptance remained pending.
The user clarified that the first stop still accepted Caps Lock and Ctrl+Alt+Del. The following warm reset hard-froze at `64`.
The candidate with programmer checksum `013CB200` still hard-locked at `64`.
The following `013C8900` image reset on its own, then stopped at `64` again.
The `013BF700` image still freezes at `64` with L2 enabled. The user reports that the board boots with L2 disabled.
This narrows the current failure to the enabled L2 path or its interaction with the incoming hardware state.
The missing ESCD data is a separate reported issue. The user deferred that work.
Boot with L2 disabled does not complete cache acceptance or the required physical baseline.
The `013BEE00` correction matches the complete chipset read/write/delay stream and the original NMI mask transitions.
The user confirms that it boots with L2 enabled. The user then reports a warm-reset halt at `51`, before the RAM test.
Performance is similar to stock. The user reports nearly doubled RAM latency with 512 KiB L2 enabled.
Performance work is paused until warm reset works. The missing ESCD issue also remains deferred.
The `013BE600` warm-reset candidate then stops at `64` intermittently. The user also reports that warm reset sometimes skips POST.
Keep those observations separate until reset and cache markers identify their paths. Intermittence alone does not prove an interrupt defect.
The `013BDA00` trace candidate stops at `15`. The user reports that the reset button permits boot, but Ctrl+Alt+Del skips POST and reports no boot device.
That symptom remains unresolved. Clearing CMOS0F did not establish physical warm-reset acceptance.
The previous trace reused `15` for early size qualification and the late enable byte. It did not identify the phase from that code alone.
Early qualification emits `1F`. The following parent-completion candidate replaces the live pre-fill byte with constant `66`.
The user reports `FF` before the visible summary, then a reset-button boot. Warm reset still skips tests and loses the boot device.
A later hard reset after that warm failure stops at `15`. Ctrl+Alt+Del responds at that stop, although Num Lock does not visibly toggle.
Delete appears only after DOS boots. That is consistent with input queued after the Setup gate closed, not proof that a key survived reset.
The old pre-fill trace could emit `FF` from register04. `FF` alone therefore did not prove that the summary returned.

## Source and reuse findings

The target source is `reference/pb430-m27c1001.bin`, with a 64 KiB system region in its upper half.
Offsets below refer to that system region. `reference/acc386.BIN` identifies ACC2046 and is comparison evidence only.
The [hardware evidence](hardware-evidence.md) owns the detailed register observations and input identities.

The initial PB430 cache code was newly adapted ACC code. It was not a direct copy of the Presario's VL82C481 cache routine.
It did retain similar policy structure: early CPU-cache selection, `WBINVD`, and a `PUSHF`/`PUSHAD` wrapper.
These patterns also appear in `presario-800/src/chipsets/vl82c481/policy.inc` under `chipset_cpu_policy` and `chipset_late_cache`.
Shared use of a pattern does not prove its literal origin or the electrical cause of a halt.

Exclude those hardware policy and wrapper patterns from the next port's starting implementation unless its target reference supports them.
Keep the proven shared rendering, Setup mechanics, PC services, and boot-policy owners.
The Presario remains the behavioral reference for that presentation. Its chipset sequence is not an ACC2168 initialization specification.

## Cache findings and required exclusions

| Finding | Target evidence | Consequence for later ports |
| --- | --- | --- |
| The first image used calls and stack-based POST macros during the SRAM presence probe. | Stock `8F33-9110` keeps that probe free of stack and BIOS-state accesses. The image stopped at `12`. | Preserve the target probe's access rules. Do not insert general helpers into a transient memory mode. |
| The new ACC read helper omitted the reference's I/O delays. | Stock `A168-A170` delays after the index write and data read. | Derive bus helpers from the target, including delay cycles and caller register effects. |
| Initial PB430 code enabled L1 before the final hardware gate and flushed it again after L2 fill. | Stock `8F3A-8F46` holds L1 off. `971F-972C` enables it and executes `INVD` before L2 activation. | Exclude the donor-style early CPU policy and added post-fill flush. Preserve the complete target ordering. |
| Matching the core register writes omitted other parts of stock activation. | Stock `9748-978D` includes the CMOS70 read, `STI`, saved flags, fill call, and final flag restoration. | Include interrupt, NMI, helper, and return behavior in the reference comparison. |
| The stock fill has its own saved registers and address sizes. | `9795-97C6` uses address-16 `REP LODSD`, eight segments, and `3FFF` dwords per segment. Its last read is `7FFF8`. | Preserve the routine, not just an equivalent-looking byte count or shortened loop. |
| The modular outer wrapper still differed after the hardware core matched. | The initial wrapper restored a 32-bit frame. Stock `978E-9794` restores six words and returns. The latest image stopped at `54`. | Include the outer caller frame and return in the initial comparison. Do not declare a core-only match complete. |
| A proposed stack-free late-cache workaround moved the observed stop but did not establish bootability. | Reports progressed through `66` to `A0`. Stock late activation does use stack operations. | The workaround and its restrictive fixture guard are rejected as a universal method. Keep the stock late sequence. |
| Early reference tests compared hardware operations but not the returned register state. | The extended test uses nonzero register values and both interrupt states. | Compare returned registers, stack position, and interrupt state as well as register writes. |
| The port re-probed cache after a warm reset and erased prior detection. | Stock `8E88-8E9C` clears register `1E` bit 5 and skips the cold probe/setup. Ctrl+Alt+Del followed the responsive stop before the hard freeze. | Match warm entry too. Clear the stock state before rebuilding RAM, and retain valid detection through that rebuild. |
| Cache-only comparison did not cover reset-time board I/O. | Stock `E07B` writes zero to port78 before `E081` reads its inputs. Earlier notes incorrectly cited `E079`, which writes CMOS0F. | Include the source of clock/table inputs in the comparison. Preserve the observed I/O without inventing its undocumented bit meanings. |
| The shadow port omitted its memory-controller continuation. | Stock `94B1-94E7` reads `12` and `00`, then sets `00` bit7 except when the mode is2 and the low nibble is9. The port kept the reset value through cache activation. | Include neighboring owners when checking cache inputs. Preserve this exact conditional write without assigning an undocumented meaning to bit7. |
| Equal register values concealed missing reset transitions. | `E067` writes06=13 before clock selection. `F163-F19E` writes a19-row table and00=20,12=4D,05=96 before the later cold table. | Retain the complete ordinary cold-start sequence. Later overwrites do not establish that earlier writes have no effect. |
| Mode1 DRAM entry reordered writes. | `9909-99C6` writes13=00,12&F7, enables A20, then writes mode1 fields00/12/05. | Preserve intermediate states and order, including reads used by the reference dispatcher. |
| Matching the six-word frame still left a different physical cache stack. | `4C45-4C53` selects0030:0100. `97C7/97C8` adds AX and a call frame. `9748` is inline. Fill reaches physical003D8. | Match SS:SP, parent frames, and physical accesses. An added activation CALL changes the cache-sensitive stack. |

These reports locate stopped execution. They do not prove that `PUSHAD` itself fails on this CPU or that a particular bus cycle caused a halt.
The current word-sized return wrapper is a source-backed correction with physical acceptance pending.
The responsive first stop does not prove that this wrapper or a cache instruction caused the stall.

The stock hardware functions now match decoded instructions. Some equivalent NASM instruction encodings differ from the original bytes.
The return epilogue is byte-identical to `978E-9794`.
`tools/stock_cache_proof.py` executes the unmodified reference and the assembled port independently.
It covers 64 cold probe/setup combinations and 16 final-enable/return combinations.
It also compares the warm-entry instructions with the original ROM.
Eight comparisons execute the original caller and compare every low-memory stack read/write while the cache transition is active.
The adapter uses the existing save/switch/restore method and restores the modular caller's stack afterward.
Eight jumper comparisons cover the initial clock sequence. The preliminary reset-table and mode1 entry I/O streams also match the unmodified ROM.
The existing component and composed tests also cover absent, ambiguous, disabled, and qualified cache states.
The software warm test runs the real IRQ1 handler for Caps Lock and Ctrl+Alt+Del after L2 activation.
It covers repeated resets, both values of reserved bit7, and invalid prior detection.
It also delivers IRQ0 at the return after54. The handler returns with registers and stack intact, then POST reaches boot retry.
Cold-entry tests cover the port78 write and all eight jumper values before DRAM initialization.
The added cold POST test starts at the reset vector with physical bank and SRAM alias models.
It runs DRAM detection, shadowing, the final cache owner, and the existing boot-retry path.
It records the actual late-entry registers for comparison with stock cold cache setup and the post-shadow update.
The pre-cache register snapshot is captured at owner entry. Repeated register indices in a reset transcript are not reliable phase boundaries.
The new reference comparison covers all memory-mode/low-nibble combinations with bit7 initially clear and set.
The port's system/video shadow mapping remains an explicit adaptation and is recorded separately.
The mapper-only fixture previously stopped on every `HLT`. Complete POST must let normal timer interrupts resume those waits.
The proof checks the CPU's actual stop address because another hook can stop execution before the diagnostic hook runs.
Resolve fixed listing addresses before instruction hooks. Repeated listing searches made the first extended test impractically slow.
The reference comparison initializes FS to the real BIOS-state segment and compares returned FS/GS as well as general registers.
Decoded instruction equality previously accepted different encodings in the fill, including a near branch where stock uses a short branch.
The port now includes the original50 bytes at9795-97C6. Its sole branch stays within the block, so relocation needs no fixup.
The proof requires byte identity and the actual fill/REP label offsets. The listing reader must recognize NASM's `<bin ...>` records.
Stock972D also selects DS=0000 before activation. The port now matches that input, while its existing frame restores the caller's DS.
These changes remove confirmed source differences. They do not prove that instruction encoding or the saved DS word caused the physical freeze.

The earlier comparison recorded register data writes, but omitted index selections, register reads, and individual delay cycles.
It therefore missed the extra read/write delays in the port, the discarded register04 read, and the size-row register1D read.
The stronger comparison records each chipset input/output and its delay value. It rejects the physically failing `013BF700` sequence.
Stock early reads have no delay. Its timing/size executor `9306-9323` delays after index selection only.
The range owner retains its two additional register reads before programming equivalent rows. Their returned values do not change these row bytes.
Moving stock CMOS facts into private BIOS state also omitted NMI masking. Preserve those mask transitions without writing stock facts over bAIos configuration.
The final owner's CMOS34/3D reads retain their original interrupt and NMI effects. Saved bAIos configuration still supplies the policy decisions.
These are confirmed sequence differences. None proves the electrical cause of the L2 freeze.

The existing IRQ0 injection follows `54`, after transient cache mode ends. It does not cover the stock activation's short `STI` window.
The shared timer accesses more state than the stock timer. That difference remains an investigation limit, not authority to replace the shared service.
The old parity NMI handler printed before emitting `E8`. PB430 now emits `E8` first, so a stalled print cannot hide the parity marker.

Deterministic IRQ0/IRQ1 injections now cover the actual transient-mode interrupt window, including instructions between chipset index and data operations.
All36 cases preserve registers, flags and the selected chipset index. They do not reproduce the physical freeze in the current model.
A separate parity case stops at the print entry and requires that `E8` is already visible.
The shared timer accesses high BIOS state during this mode. That access is recorded, but its electrical cache effects remain outside the model.
The stock IRQ1 also uses a substantial frame and permits nested IRQ0. Stack depth alone does not justify replacing a handler or masking the stock window.
One remaining warm adaptation is explicit: the port clears register04 after the stock1E clear, then enables04 again late.
The stock post-reset block8E88 preserves incoming04. Its pre-reset owners require separate tracing before judging the complete transition.
Source9631 performs cache teardown only when the old BDA0472 already contains1234. Source968E supplies a separate teardown before the protected-mode reset pulse.
The port also uses a reset pulse, but previously omitted that teardown. It now adapts968E with the CPU request and qualified/requested L2 gates.
The original CMOS34/3D reads retain their NMI/interrupt effects. The source order is CR0 CD/NW, INVD, transient1A, fill, CMOS70, STI,04 off,1A clear.
There is no register1E operation or WBINVD in that owner. The port removes its old warm-reset WBINVD and clears its own effective marker after teardown.
Qualified/requested state covers a reset during activation. An effective-enabled marker alone is still zero during that interval and is an inadequate gate.
The extra saved FS word protects the modular state owner. Reset-fill stack addresses therefore differ by two bytes from the stock entry fixture.
The proof compares reset hardware, reads, delays, CPU/NMI/IF, fill accesses and returned ABI. It does not claim identical reset stack addresses.
It starts with L1 actually enabled for the enabled cases, and includes qualified SRAM with the separate L2 request disabled.
The following7EE2-7EF3 pulse preparation selects CMOS80 to mask NMI and writes register02&98. The port includes these19 bytes unchanged.
This retains F000's mapping while releasing C000 shadow and write protection. Video initialization clears E000 shadow before reading the retained physical provider.
The native three-boot observer must check rendered summary borders as well as successful disk boot after those real mapping changes.
The port retains its existing controller-pulse mechanism and now matches that reference producer's prerequisites. The stock real-mode path uses a software restart instead.

The earlier parent proof stopped at97CB, after9706 returned. It missed97D3 and9808.
Stock97D3 reads CMOSB4 and leaves NMI masked. It forces the high branch of9808, which sends C7 then20 and waits after the data write.
Both warm-reset callers also force that high branch, without the parent's CMOSB4 read. The shared bounded helper preserves these separate effects.
The controller transaction masks interrupts before the command and restores entry flags after the final wait, as the source does.
The port excludes OEM private4B5 writes. The physical function of the controller pin remains unproved, so no new timing option is exposed.
The parent comparison now reaches4C56 and includes actual controller reads/writes and their interrupt state.

Stack-free cache markers now identify tag selection, the start of fill, fill return and the final state writes.
Other constants replace AL immediately before the stock code replaces it. At fill entry, the stock writer leaves AL=AH.
The marker emits66, then MOV AL,AH restores the live byte. A256-value execution check requires identical AX, flags and stack position.
Swapping AL/AH cannot select the index here: the writer already copied its value from AH to AL. Check the helper's return state before choosing a diagnostic register.
No marker is added inside the stock interrupt window or fill loop. The reference check validates these exact trace bytes before comparing the remaining instructions.
Shutdown service05/0A emits its actual code before the original far handoff. Normal reset still runs the full POST branch.
The normal reset producer previously left CMOS0F unchanged. A stale05/0A could therefore select a valid service resume and bypass POST.
Stock real-mode Ctrl+Alt+Del reaches7F27 and jumps toE05B, whose ordinary path clears CMOS0F atE071-E079.
The port pulses the keyboard-controller reset instead. It now clears CMOS0F through the existing RTC writer before that normal reset.
Controlled defaults restart uses the same clear. Genuine service consumers remain intact and retain their separate tests.
The new check rejects the previous013BE600 producer with a stale05. Full warm cases include stale05/0A and require the clear before the pulse.
The empty-device warm fixture expected `E4`, so it could not detect loss of a previously bootable device.
The new device test boots a signed ATA sector, poisons old disk publication, then requires actual IRQ1 restart, full POST and successful boot again.
Both Delete variants and stale05/0A are covered. RAM testing, floppy initialization and ATA discovery must run before the next INT19 entry.
The normal BIOS Ctrl+Alt+Del handler always requests reset. Public INT19 and the fresh-key boot retry intentionally bypass POST and reuse disk state.
Keep these paths distinct when tracing a missing POST screen. The physical observation does not yet identify the caller.
The native observer boots the actual ATA image three times through both Ctrl+Alt+Del variants. A BDA witness must clear on each full POST.
Its first version raced the timer's LED writes between commandD2 and its scan parameter. Only that test transaction now masks interrupts.
The corrected observer passes in86Box. Its previous timeout is not evidence that the firmware reset failed.

The warm `51` investigation found an extra `WBINVD` at entry to `chipset_apply`, before retained L2 was disabled.
Startup already flushes L1 and holds it off before the stock warm register1E transition.
The reference warm block does not issue another writeback flush after that transition.
Remove this redundant operation. Keep the later flushes after register04 disables L2.
The new warm check rejects `013BEE00` at that operation, with `51` as its last marker.
It monitors flushes in F000 and the staged shadow copy. This proves operation order, not the electrical cause of the halt.
Markers `D0-D4` after `51` separate settings, NumLock, keyboard presence, chipset entry, and retained-L2 disable.
An absent keyboard with the saved All Errors policy can intentionally wait in this phase. A halt at `51` alone does not identify an instruction.

OEM private CMOS flags map to existing bAIos state and configuration fields. The port does not overwrite its configuration with OEM records.
The bAIos reset pipeline retains valid cache detection through its BIOS-state rebuild and skips cold cache probing on warm entry.
An explicit validity byte distinguishes prior detection from uninitialized state. Invalid detection takes cold cache setup after the stock warm state clear.
This adapts the OEM private warm-start data to bAIos state. It does not copy the OEM private CMOS records.
Unknown 32/64 KiB results remain unqualified and disabled. These adaptations are explicit limits, not universal hardware behavior.

## Other findings from this port

| Area | Evidence and lesson |
| --- | --- |
| Reference documents | `AC216811.MAN` is a WordPerfect AMI guide. Its file suffix does not identify its real format. Preserve it and its diagrams when producing searchable copies. |
| DRAM mapping | A bank probe code is not a capacity. Physical alias-aware counting establishes size. The original table-search flag defect cannot justify an invented fallback. |
| First stack and reserved state | Prove the actual low-memory stack before the first push. Reserve the full 8 KiB BIOS state region and publish the resulting conventional-memory count. |
| SRAM reporting | Distinguish presence, qualified capacity, requested policy, and effective enablement. The user reports 512 KiB installed. That fact does not replace the actual probe. |
| Undocumented controls | Keep unknown encodings and fields unchanged. The ACC2046 comparison does not establish ACC2168 CAS timings or PB430 wiring. |
| Super I/O | ACC3221 variant, reserved fields, address selection, and IRQ selection come from its data sheet. The emulator's primary-UART IRQ encoding defect does not justify different physical programming. |
| Video input | The retained onboard provider is 32 KiB. Validate a declared external image completely, but copy only the bytes covered by the controlled mapping. |
| Video vectors | Accept equivalent far-pointer aliases within the valid physical handler window. Preserve the actual returned vector at INT42. |
| Option ROM scan | Skip the initialized video provider's full declared extent. An interior signature is not a separate provider. |
| A20 and reset | Preserve the target's combined keyboard-controller and fast-gate behavior. Reference service continuations must precede destructive cold-memory work. |
| Diagnostics | A completion marker can precede register restoration. A changed last code is not proof that the system became stable. |
| Fixtures | The inherited RTC fixture recognized a Presario port84 delay. Stock PB430 uses `OUT ED`. Fix the fixture's hardware seam instead of modifying stock firmware to satisfy that assumption. |
| 86Box | The exact PB430 model is available and the automated runner uses build10408. Both the failing013C8900 image and the current candidate reach its boot observer. The ACC implementation stores1D/1E and lacks the physical SRAM/tag initialization effects. Emulator boot does not qualify this hardware failure. |
| Delivery | Use the full physical image and the programmer checksum required by root `AGENTS.md`. A zero-sum system ROM and a physical image checksum serve different purposes. |

Keep board recipes in this port. Before reusing one elsewhere, establish that the new target has the same contract.
Universal-method experiments remain deferred until the PB430 physically completes POST, Setup Save/reset, and the intended boot path.


## Complete instruction maps after stop66

The stock-parent image013B6400 stops at66. This is after04 enable andCLI, before the original fill returns. It excludes the later97D3/9808 continuation as the cause of that first stop. It does not identify an individual failing read.

The [durable maps](../reference/maps/README.md) cover all bytes of both original ROMs and reassemble byte-for-byte. Their [behavior document](../reference/maps/stock-behavior.md) records the startup chains, callers, tables, reset owners, good/failed image comparison, and unresolved differences. Static instruction reachability is distinct from a hardware trace.

The full source audit found early refresh and DMA cascade setup atE115-E131. The old port delayed refresh until after destructive RAM work, SRAM probing, and shadow copying. Presario's later initialization placement is not a portable contract. Establish the target's prerequisite before first RAM use and retain cascade state after any later DMA master clear. The new candidate does so. The ordering correction is established. Its effect on physical66 remains unproved.

The audit also found warm consumer9631, before8E5E. The old port copied only the later8E88 holdoff. The new consumer retains963D-9687, reaches it throughDI without an extra early stack write, and uses the stock0000:7C00 stack region. A callerCLI protects the port's vector rebuild after the stockSTI sequence. Tests distinguish this warm fill from the finalactivation fill and keep the first BIOS-state write after04off/1Eclear. Pre-pulse968E and post-reset9631 are separate contracts.

ACC386 does not share the PB430 fill or activation sequence. It uses word reads over28000-9FFFF, different flags and calling conventions, and different invalidation operations. Do not transplant it as a PB430 workaround. Its83 ROM-stack calls require inline return words to be marked as data. PB430'sD3E5 inline-string printer changes the saved returnIP, so following ordinary fallthrough through its strings gives a false instruction map.

The retained good image013BEE00 booted but did not establish repeatable reset or cache stability. Both good and failed images lacked early refresh. The comparison therefore identifies an omission, not proof that one changed byte explains all hardware symptoms. No new timing profile or alternate cache-size encoding was introduced.


## Stop66 persists: diagnostic writes changed the reference transition

The user reports that stock-map013B0F00 also stops at66. Early refresh and the earlier warm teardown did not establish a cure. Preserve their source evidence without calling them the physical cause.

The previously booting013BEE00 image and the original ROM contain no POST writes inside9748-978D. The later trace candidates inserted65,66,67,68 while temporary tag mode was active. The old comparison explicitly removed those instructions and ignored port80, so its equivalence claim did not include those bus operations. Proving that a marker preserves registers, flags, and SP is insufficient in a cache transition.

The new candidate removes those18 instruction bytes. It retains64 before entry and69 after normal mode returns. The source comparison now rejects any extra instruction in the contiguous transition and records all IN/OUT events while it executes. The failed stock-map image is a negative control and must fail that check. Both source and previously booting image support this change. Physical acceptance is still pending, and removing bytes also changes instruction placement, so success alone cannot identify the electrical mechanism.

The focused audit found no independent segment, loop-count, stack-depth, or RET defect. CPU-enable CALL/RET, high private-state reads, interrupt handlers, and code placement still differ from stock. Several also existed in the booting image. Do not turn them into an unsupported cache-timing fix.

## Hard freeze64: include the timer handler in the reference contract

The stock-transition image013B1D00 hard freezes at64. Removing diagnostic writes did not cure the failure. This code now covers the entire uninterrupted activation, not the narrower point marked64 in older images.

Stock IRQ0 atCFDF-D027 uses low BDA memory, the floppy motor port when its countdown expires, INT1C, and a final PIC acknowledgement. The shared timer also polls the keyboard, updates LEDs, and reads high BIOS memory through its motor service. The old interrupt test recorded reads at9E1EB and9E086 during1A mode08 but accepted them because its flat memory model returned RAM. This was an unqualified hardware assumption, not evidence of safe cache operation.

The stock-timer candidate uses the original73-byte PB430 timer with only its zero-constant address relocated. The late wrapper installs it underCLI before transient mode and saves the previous vector on the caller's stack, outside the fixed0030 cache frame. It restores that vector underCLI after normal mode returns. Ctrl+Alt+Del installs the same handler before cache teardown and retains it through the reset pulse and early warm consumer. Normal startup replaces it when rebuilding vectors. The uninterrupted chipset sequence, PIC masks, fill and timings stay unchanged.

The focused IRQ test now rejects high BIOS-memory accesses by the timer and requires restoration of the runtime vector. This checks the built-in INT1C hook; external hooks and arbitrary keyboard activity during reset remain outside this physical qualification. Stock itself calls INT1C. Do not silently discard that hook or mask stock IRQs to satisfy a fixture. Physical repeatability remains unproved.

The user reports intermittent10/64 freezes and successful boots with stock-timer013AEE00, but confirms that warm reset works again. Preserve that improvement separately from the unresolved cache failure. One successful reset does not qualify cold-start stability.

The reset audit found an inherited WBINVD pair around CR0 cache disable. Stock PB430 uses the identical14-byte CR0/INVD prefix at963D-964A and8F3A-8F47. The next candidate replaces only that common-entry pair. It retains cache holdoff before modular RAM work and preserves the working warm path. This placement is an adaptation, not an exact stock cold-start sequence. The proof now requires those14 bytes without normalization. Do not carry donor flush instructions into a new port without checking the target's entry state and dirty-data contract. Do not replace runtime flushes merely because reset uses INVD. Physical correction of the random freeze remains unconfirmed.

## Cold-only freezes when the visible RAM test is skipped

The user cannot reproduce the freeze on warm reset, even with the RAM test skipped. Cold and hard-reset failures appear influenced by skipping. Treat this as evidence about retained state, not proof that an extra delay fixes hardware.

Stock initializes the first64KiB at3CF6/3D44 and each accepted conventional block at5855 before the visible test. Its Space path still clears blocks at5C79. The port omitted most conventional clearing and relied on a shared non-destructive test that Esc can stop. This is an invalid initialization dependency. Even the completed test excludes08000-0FFFF.

The correction adds mandatory clearing to the existing cold mapper, preserving topology scratch and the warm bypass. It reuses the existing extended-memory clearing method. Tests count actual writes before stack establishment and reject the previous image. Early Esc and full-test cases must both reach cache activation with no unwritten fill bytes. Keep this requirement for future ports. The specific cold-memory layout and clearing instructions remain board-owned. Physical confirmation remains pending.

## Cold POST contains a reset before the visible RAM test

Cold-ram-init013ACE00 still freezes at64. Both completed and skipped RAM tests can fail. The user reports reliable recovery even when Ctrl+Alt+Del interrupts the cold RAM test. Later disk and boot state are therefore not required for recovery.

The reference contains a cold-only shutdown self-test at424B-4381. It resets through the boot block, then returns to43C7 without repeating cache sizing. The reset reapplies06 and changes04/1A/1E before shadow/RAM work. The earlier comparison omitted this path and incorrectly accepted cold1A24/1E7B. The healthy stock continuation supplies2C/5B. See the complete [reset-and-resume trace](../reference/maps/stock-behavior.md#cold-shutdown-self-test-and-its-reset-continuation).

The correction copies the original clock/NMI/61 prefix and cache-control prefix into cold policy. It preserves the working warm path. The tests now include this original continuation. For the next port, trace reset producers and saved return addresses throughout POST, not only user-requested resets. A source-backed register table is insufficient when a later reset changes its result. Do not label a comparison complete when it connects separate owners without accounting for the path between them.

The user confirms repeatable physical boot with this correction in image SUM32 `013A7200`. The earlier conventional clearing, timer, reset-entry and uninterrupted cache-sequence corrections remain part of that accepted image. Their individual effects are not isolated by this result. Preserve the complete sequence during performance work and compare later candidates against this baseline.

Fast Boot skips only the optional visible extended-memory test. It must not bypass the mandatory initialization that precedes cache activation. POST can show a selected setting before hardware applies it: the PB430 L1 field now reports the saved choice, while L2 still reports its effective state. See the repository [Setup help policy](../../AGENTS.md#setup-help) for user-facing explanations.

The cold SRAM sizing probe is also a temporary cache window. Report its result only after the stock mode and saved RAM are restored. A comparison that records chipset writes but silently drops port80 can miss added instrumentation. Compare all probe I/O; list any private CMOS storage adaptation by exact reference sites and retain the NMI transitions.

## Saved cache changes require reference reinitialization

A cold start with L1 disabled selects the reference safe tables and omits the size-dependent cache range writes. Enabling L1 in Setup cannot safely reuse that state merely because the SRAM probe previously qualified its size. The warm path skips those cold prerequisites. Component tests of each choice missed the transition between them.

PB430 now compares the active L1/L2 choices with the effective saved record at normal reset. A change selects full cold initialization; unchanged choices retain warm reset. The comparison preserves the complete active record and validity byte so stock teardown still sees the old choices. It uses the existing loader, including invalid-record defaults and recovery behavior. No new persistent reset flag is needed.

Compare at reset, not only after successful Save. Chipset data can be validly published before a later base-record verification fails. That failure must leave Setup available, but a later Ctrl+Alt+Del still needs to initialize the saved cache choices. Exercise the actual Setup and reset continuations on the same machine, including reverse changes, unchanged saves, discard, cancellation and absent or unqualified SRAM. Software checks do not qualify the new image on physical hardware.
