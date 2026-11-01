> Developer reference. Board implementation, research and validation details belong here.

# Shared SMM and Stop Grant services

The [shared design](../../../docs/plans/BAIOS-004-smm.md) owns reusable service contracts. This port-local record retains the original detailed activation and clock-work boundaries. Current normal idle uses the native doze provider. The user's later divider instruction supersedes the earlier PCI /1 and ISA-setting gates in B21. Preserve the actual PCI divider through every request and wake write. SMM readiness and the compatible save-state interface remain real prerequisites. See the [current implementation reference](../development/sl486.md#current-idle-implementation).

The later ordinary-idle and EMM386 requirements also supersede ACT1's deferral of native APM clock control and protected command entry. Private commands0..2 keep their existing caches-off wrapper. APM command3 uses the same native doze and full-on release in real, virtual8086, protected16 and protected32 entry modes. Its caller performs no privileged cache or CR0 instruction. The handler owns those operations after entry in the normally uncacheable final VGA aperture. This does not change cache initialization or authorize system suspend/device power management.

## Ordinary idle integration boundaries

The user requires usable native idle through DOS POWER.EXE, Microsoft EMM386 and Windows APM, preserved floppy access, an SL CPU suffix, and aligned POST values. These requirements extend the accepted activation and diagnostic inventory below. Existing B1..B25 retain their scopes, except B21 now requires preserving all divider encodings and B24 preserves the interrupted CPU state while allowing temporary cache/CR0 operations in the command3 SMM handler. Private command2 retains exact prior restoration; ordinary command3 requires native full-on state without replaying a dormant power request.

| Boundary | Required discriminator and contrast | Production path and terminal oracle | Exact check |
| --- | --- | --- | --- |
| B26 | Actual APM connection metadata, rather than seeded state or assumed descriptors; real versus protected16/protected32 connection. | Public connection entry returns code/data/lengths; build descriptors from that result, enter the returned address, execute adapter/SMM/RSM and one IRQ return. Preserve caller, flags, segments, stack and connection owner. Disabled Idle makes no request; unavailable provider falls back once. | `python -B m919/tools/test-idle.py` |
| B27 | Eligible IRQ versus masked PIT or empty cascade, with nondefault saved PM controls and every raw PCI divider encoding. | Public APM idle through installed handler, native doze/retry/full-on, RSM and pending IRQ delivery. No IRQ is acknowledged in SMM; no dormant A0/A4/80 replay or divider change. | Same check, request/before/spurious/spurious-cascade/slave-IRQ cases and exact ordered write assertions. |
| B28 | Virtual8086 entry with paging off/on, fresh SMI versus no delivery, and dirty ordinary RAM. | Public virtual INT15 through the board's nonprivileged caller, installed SMM cache owner, RSM and IRQ/caller return. No CR0/cache instruction outside SMM; preserve CR0/CR3 and registers. Drain dirty data on delivered entry; preserve it on timeout; restore cache and controls before handoff. | Same check, V86 delivery/timeout and paged contrasts. CPU/I/O mediation remains a model; user reports DOS/Windows/floppy operation with and without EMM386. |
| B29 | AMD SL capability versus unknown/unsupported identity; long SL name versus adjacent summary label. | Actual name adapter through POST, Setup and summary render. Exact identity text, blank separator after Enhanced, and consistent shifted value columns; other ports retain their default layout. | `python -B m919/tools/test-hardware.py --case cpu`, with shared CPU proof and rendered-row assertions. |

Physical scope: the reported motherboard/CPU passes ordinary DOS and Windows use and floppy reads with and without EMM386. Windows3.1 Advanced shows changing HCLKO while STCK appears high. This does not establish a measured CPU Stop Grant acknowledgment. Other configurations retain their separate qualification limits.


## Outcome and scope


Desktop SL-qualified Intel 486 names gain an SL suffix through the board adapter. Shared code supplies a bounded SMM installer, an Intel-compatible stackless SMM handler, and an optional board-owned Stop Grant idle path. SMM is the CPU's System Management Mode. Stop Grant uses STPCLK with the external clock running. Removing the external clock, device power management, and new Setup controls are outside this checkpoint.

Base: `9f7977c9190a272f683d1dbe9863b01429a3638d`, branch `task/shared-sl486`, one checkout. No pending Plan capture applies. The completed BAIOS-011 checkpoint remains intact. This task supersedes its unchanged-name requirement and its deferral of architectural SMM/Stop Grant services only. Board-only hardware access, unknown capability disabled, existing cache/reset owners, and the original mobile 486SL distinction remain required.

Feature versions: M919 0.11.0, PB430 0.4.0, Presario 800 0.4.0, and MP386 0.5.0. The automated update pipeline runs the two shared architectural proofs once per update.

The shared-services checkpoint is commit `4f1c35c42386bae0bb3d6cafc211da07cc2d2c15`. The user's activation request supersedes its blanket unavailable-board policy. ACT1 below adds the supported M919 software-SMI backend. Other hardware paths retain their concrete limits. Physical qualification remains separate from the bench image.

## Sources and design decisions


The user's latest request promotes SMM and stop-clock and requests corresponding identification strings. The earlier board-adapter-only constraint composes with this request. Intel 241731-002 sections 8 and 9 define state layout, RSM, relocation, SMRAM protection, reset interlocks, and Stop Grant wake handling. AMD 19751 revision C sections 5, 7.7 and 7.8 define its clock states and the compatible two-pin Am5x86 format. Intel AP-485 qualifies conservative Intel desktop identities. These are fixed architecture contracts, not an open algorithm choice requiring prior-art research.

The M919 reference ROMs establish useful SMM setup order but do not qualify a stop-clock backend: their APM idle uses HLT. The incomplete UM888x register report does not establish a reliable request/release path. These physical operations stay opaque board responsibilities. Do not infer them from speculative bit names or activate them in this change.

`shared/src/pc/cpu.inc` owns CPU classification and name formatting. Board composition files own public access. `shared/src/pc/smm.inc` owns the bounded copy service and stackless handler macro. `shared/src/pc/processor.inc` owns mode-neutral idle macros. `shared/src/firmware/apm.inc` owns public APM entry and capability reporting. `shared/tools/` owns focused instruction-level proofs. Existing port build owners retain image layout and integrity checks.

## Atomic software checkpoint SMC1


Implement these services together with their direct consumers, tests, interface documentation, and feature-version increments. One full native review and one local checkpoint cover the software deliverable. Do not publish, promote completed flash candidates, or change latest pointers.

The CPU profile query returns AX=1 for the existing documented Intel desktop candidates and AX=2 for GenuineAMD original family-four models E/F, whose Am5x86 two-pin format is documented. All other identities remain unknown. DX remains board capability, independently zero on current adapters. The board name formatter decorates only Intel profile 1, preserves the name ABI, and reaches all three real presentation consumers. A jumper is not readable without a documented selector; electrical jumper wiring does not create a software identity source.

The SMM installer takes AX profile, DX board capability bit 0, DS:SI source, ES:DI destination, and CX length. It accepts profiles 1/2, DI=8000h, length 2..7E00h, and SI+CX<=10000h. Qualification and bounds precede all destination writes. It copies forward regardless of caller DF, verifies bytes, returns AX status/CF, and preserves other registers and flags. The board owns SMRAM mapping, reservation, protection, first-fetch coherency, reset interlocks, and source activation. Installation alone authorizes none of those operations.

The stackless handler uses only documented writable save-map fields. A board acknowledgment macro reports whether this is the software-command source. Only that source plus saved EBX request magic permits a command. Ping and fixed-target relocation return a positive, distinct reply magic, explicit status, and revision. Relocation requires revision bit 17 and a prepared, installed, protected target; the complete target window must remain below 1 MiB (32 KiB aligned SMBASE at most F0000h). Invalid fixed targets fail assembly. Preserve I/O restart, halt restart, reserved fields, and ordinary saved context. RSM is the only return. No ordinary BIOS calls, stack, HLT, FPU, or cache operations occur in the handler.

Optional inline board idle query and entry macros must be supplied together. They work in real, protected 16-bit, and protected 32-bit APM paths. Query gates runtime CPU and board support. A successful entry completes request, Stop Grant acknowledgment, wake release, interrupt, and return. Decline is pre-entry only: no asserted STPCLK, no consumed wake, preserved segment/stack state. Shared code then executes one HLT fallback. Disabled APM Idle does not query hardware. Installation can query capability while policy is disabled and reports both facts. Installation flags advertise clock slowing only when the provider qualifies. With no provider, preserve the existing HLT sequence.

## Scenario Proof and validation


B1: Actual four board queries distinguish CPU profile from unavailable hardware. Their preparation calls must reject before any destination write or hardware operation, including on positively identified CPUs.

B2: Actual detector and all three presentation consumers preserve caller state and show the specified Intel suffix. Original mobile 486SL, ambiguous/non-CPUID identities, and AMD marketing names remain distinct. Run the existing per-port CPU proof against freshly composed test images; changed display and profile paths justify these checks.

B3: `python -B shared/tools/smm_proof.py` executes the real installer with qualification, profile, destination, length 1/2 and 7E00/7E01, exact source endpoint/crossing, DF, and verification contrasts. Rejected input must not write SMRAM; successful bytes must match the independent source image.

B4: The same proof enters the actually installed handler using independent Intel/AMD state layouts. Check source acknowledgment, fresh request/reply, uncommanded SMI, invalid command/revision, RSM continuation, and untouched restart/context fields. Install both windows through the actual installer, relocate, then obtain a new ping reply at the new entry. Include a pending SMI after relocation. Compile F0000h and reject F8000h.

B5: `python -B shared/tools/stop_grant_proof.py` checks real/PM16/PM32 public APM paths, accurate flags, disabled gate, default/unavailable HLT, qualified Stop Grant request/ack/wake/IRQ/return, and pre-entry decline with exactly one fallback wake. Its synthetic board and pin model prove the interface, not a physical controller.

B6: Run the existing four build/integrity owners. Preserve retained regions and fixed entries. Current startup, cache, and reset activation stays unchanged. Reuse unchanged completed proofs instead of repeating unrelated matrices. Record commands, outputs, hashes, and boundary results in ignored `.agent/test-results/shared-smm.json`. Obtain fresh read-only boundary trace closure, then native correctness review of the exact staged tree. Fix only source-backed findings within this scope.

## Decision Log


The software checkpoint separates reusable CPU architecture from unqualified board wiring. Hardware activation remains blocked by missing electrical and controller evidence, rather than guessed register values. Positive handler and idle proofs use independent architectural models and explicit test adapters. They do not certify physical stability. Stop Grant keeps CLK running; literal clock removal has additional cache, DMA, and PLL requirements outside this checkpoint.

## ACT1: Activate supported software SMI hardware


Normal M919 POST must install and activate its SMM handler automatically. Keep this work on the existing task branch. Its base is the reviewed shared-services checkpoint above. M919 becomes 0.12.0. Other port firmware versions remain unchanged when their composed bytes do not change.

Source: the user explicitly requests activation on every supported port. Status: supersedes the earlier unavailable-only completion claim. Scope: board activation, the request transport required by real I/O, and direct tests/documentation. Keep the existing cache initialization sequence, CPU naming, APM entry modes and no-AUX policy.

The maintained-port census is finite. M919 has the executable UMC path below. MP386's native 386DX is incompatible. The VL82C481 CPU-interface table has no native SMI/SMIACT/STPCLK path; a Compaq external implementation is not documented. ACC2168 references lack the required SMRAM/source controls. Do not transplant the different ACC2087 map or pretend the latter two lack all possible external hardware.

The M919 OEM decoded core at 2881..28DA,37F8..3A43,409D..40F3,428D..4369,C610..C676 establishes Intel-compatible interface selection, installation, software triggering and acknowledgment. The independent UM8881/UM8886 implementation in the retained 86Box source supplies the memory-view and PCI-register model. These are reverse-engineered hardware contracts for a bench candidate, not physical certification. The AF PCI ID is 1060:886A and BF is 1060:888A. The host is 1060:8881.

Call the board initializer from startup after state/BDA/IVT initialization and before cache initialization, DMA/PIC, PCI masters, VGA and option ROMs. First require CPU profile 1/2 and the actual supported host/bridge IDs. Unknown combinations return without activation writes. Separate this pre-install qualifier from final readiness: `board_smm_prepare` uses the live qualifier and the actual shared installer. `board_cpu_sl_query` retains its read-only ABI and reports final readiness from the current EBDA only after successful activation.

Set A0 to zero and clear the software request/enable while installing. Select the Intel-compatible SB76 interface and SMI rather than IRQ in SB46. Select low SMRAM through HB5C/HB5D and clear the classic split-data mode in HB60. Install and verify at A000:8000 with HB60.01 open, and install the bootstrap at 3000:8000. Close and check the manual view before requesting relocation and a fresh ping. Set readiness only after both distinct positive replies. Retain the hidden final handler; bootstrap RAM is disposable before the RAM test. Failure must not publish readiness, leave a manual SMRAM view open, or leave requests enabled. A bounded poll diagnoses a missing fresh reply; it cannot recover a CPU that enters broken SMM and never returns.

The real trigger uses OUT AL/DX. Change the shared request transport to low CX=command, EDI=target, EBX=request magic. EAX/EDX are I/O scratch. Replies retain EAX=status, EBX=reply, ECX=revision and saved CF. Keep restart and other saved state intact. The board acknowledgment is stackless, captures the actual software-source bit, performs OEM A2=0/A3|20/A3&9F, restores CF8, and returns the captured cause.

The private real-mode command wrapper saves actual A0/A8 bytes before flushing caches. During each request it applies the reference A0|34h and A8|28h fields and pre-arms A3.80 before raising A3.40. A3.04 is not required by the reference software-SMI re-enable path. The individual roles of A0.34/A8.28 remain unresolved. Restore both saved bytes before restoring caches or interrupts, including timeout. The wrapper masks IRQ/NMI, flushes dirty data, disables CPU/L2 caching, performs the command without ordinary RAM/stack writes, restores L2 and invalidates clean tags, restores CR0/CF8 and board NMI policy, then restores caller state. Use the established WBINVD/CD/L2-disable and INVD primitives outside the reference's transient initialization window. Do not change timing, geometry, tag format or replay initialization inside SMM. Manual SMRAM opening is confined to early POST. Runtime always uses the closed conditional SMM view.

Normal reset owners quiesce the software source before their existing reset I/O. Reinstall both windows on cold and warm POST, covering default and retained SMBASE. Do not invent a hardware SRESET latch or claim that external electrical reset timing was measured. The supported model is synchronous firmware-controlled software SMI, with temporary reference controller fields restored after each command. Global reset remains a CPU/controller operation.

Stop Grant is still unfinished: the OEM idle path uses HLT, and the proposed SB76/A1 bits do not establish request depth and wake release. Do not advertise clock slowing or turn on speculative power-state bits to obtain it. Device power management and protected-mode command entry remain outside ACT1. This checkpoint must not be described as completion of all stop-clock work.

The Phase 2 finding about first-boot readiness is accepted: prerequisite qualification and final readiness have separate owners. No test can pre-seed readiness to install the handler.

The F bank cannot contain this extension alongside the existing firmware. ACT1 uses the physical image's previously unused E bank instead. SB57.20 enables E ROM decode; startup verifies its header before a real far call. All E/F transitions use matching far returns. Before later VGA shadow policy can select E backing, the positive-qualified initializer copies the complete E bank with shadow reads off and restores its write policy. Reset quiescence stays wholly in F. Both banks and the physical image have independent additive byte checksums. `rom.checksum_regions` is optional and leaves other ports' builder behavior unchanged. Configured identity text still must fit the fixed F-bank capacity.

The read-only DOS handoff tool uses the configured EBDA size and board-owned status offset. It prints one result code without triggering SMI. Build it in `build/diagnostics/` through the board proof; do not add persistent Setup state or device discovery for this diagnostic.

Activation boundaries and exact checks:

- B7: `python -B m919/tools/smm_activation_proof.py` starts at the actual startup call site and ends at the next unchanged POST owner. It must traverse live CPU/controller qualification, actual preparation/installer, real PCI trigger/ack, installed handler/RSM, relocation, fresh ping and readiness. Contrast cold default SMBASE with warm retained SMBASE.
- B8: The same check varies CPU and each required PCI identity independently. Rejection performs no activation writes. Preparation succeeds with readiness initially zero. A later query reports readiness without configuration I/O and follows the current BDA pointer.
- B9: The same check models independent normal CPU, bus-master and SMM views. Closing the manual view precedes enable. Ordinary and DMA writes cannot alter hidden handler bytes; a later actual command still succeeds.
- B10: The same check keeps the request cookie constant while varying real source status, and checks fresh/absent/stale replies, unsupported relocation, timeout and installer failure. Only handled requests receive replies; failure leaves readiness zero and sources/manual view closed. Generic `python -B shared/tools/smm_proof.py` retains the save-map/bounds cases with the corrected transport.
- B11: The board proof exercises a runtime command with dirty ordinary memory and prior cache/CF8 state. Observe flush before first SMM fetch, no ordinary writes while caching is off, INVD before CR0 restoration, and exact caller/cache/configuration restoration. No instruction is added inside the established cache initialization window.
- B12: The board proof follows source quiescence through normal reset I/O and subsequent startup at either SMBASE. External electrical reset timing remains opaque and unmeasured.
- B13: Retain existing CPU naming and other-port negative paths. Rerun only the affected M919 CPU owner and changed shared handler proof. Verify unchanged other-port firmware paths by source/byte identity instead of repeating their completed suites.
- B14: Existing M919 build/integrity checks protect the physical image and retained regions. The changed board proof and generic handler proof become declared automated checks. Preserve the complete reference cache operation/table bytes and no-AUX policy. Run fresh boundary trace closure and native checkpoint review before delivery; do not repeat unrelated validated suites.

## SGR1: Exhaust the available Stop Grant evidence

Source: the user requires active investigation until all available research avenues are exhausted. This replaces any interpretation of the missing backend as permission to park the feature. Scope: unfinished board Stop Grant request, acknowledgment and wake handling. Preserve the completed shared-services and M919 SMM activation checkpoints, including `a824af51bc6226669f2f295fc65e063ae1c9a0ca`. Keep the current bench image intact during research.

Account for every unique retained UMC ROM, including expanded AMI, Award and Phoenix runtime/SMM modules; available chipset, CPU, board and pin documentation; the retained modern Biostar replacement BIOS and its source; and emulator implementations. Trace initialization, APM idle/busy, register-table inputs, SMM handlers and wake-source configuration together. An HLT instruction alone does not establish that a surrounding chipset path lacks Stop Grant. Distinguish architectural Stop Grant, Auto Halt power-down, clock division and deeper suspend states.

Record source identities, duplicate groups, verified decode coverage, reachable request/release paths, counterevidence and exact unresolved questions in the ignored research evidence. Keep vendor ROMs and full listings outside Git. Missing documentation is a remaining question, not evidence that the hardware lacks support. Do not repeat unrelated validated firmware tests or modify timings and caches while pursuing this feature.

When the evidence establishes a complete board sequence, extend the accepted boundary inventory and run Design Preflight before implementation through the existing board adapters. If it does not, finish the available source analysis and identify the smallest physical observation needed to discriminate the remaining possibilities. Do not label a partial source search exhaustive or silently put the feature on hold.

The [Stop Grant evidence report](../research/stop-grant.md) owns the source findings, including all 33 distinct retained UMC-comparison inputs, the actual APM/SMM clock and wake paths, the missing pin spreadsheet, the legacy-UMC interface correction and the temporary RTC wake mechanism. The remaining experiment must discriminate a continuing external CPU clock from full clock gating. An emulator that merely stores these fields cannot supply that observation.

## SGW1: Qualify a controlled wake before a clock request


The user has a scope or logic analyzer but prefers it as a last resort. First supply `m919/build/diagnostics/WAKECHK.COM`, without changing or rebuilding the current flash image. Its short result covers the current boot's SMM readiness and an owned RTC alarm interrupt. It does not request a clock transition or establish electrical Stop Grant. The donor's RTC B bit 20h enables a configured daily alarm, not periodic interrupts. Its default midnight alarm cannot supply this experiment's deadline.

This subtask starts from `a824af51bc6226669f2f295fc65e063ae1c9a0ca` on the existing branch and checkout. SMC1 and ACT1 remain unchanged. Stop Grant integration remains active and depends on the physical SMM/wake result. Do not add a firmware command or power-policy interface just for this prerequisite.

Product boundary: the new port-owned DOS diagnostic, RTC policy snapshot/restore and result formatting compose. The existing public INT1A alarm/time service and int70 interrupt/callback owner are traversed unchanged. Existing startup, SMM installation, cache transitions, APM and reset remain opaque preserved owners. DOS vector services and RTC/PIC/PIT hardware are external seams. Electrical clock control and normal APM clock slowing are outside SGW1, not abandoned work.

The supported model is one deliberately invoked tool in plain real-mode DOS, with interrupts enabled and an idle RTC interrupt owner. The configured board NMI policy replaces an unreadable port-70 latch. PIC read selectors return to their ordinary IRR selection. Read actual state, alarm fields and masks. Do not assume a CPU frequency, RAM size or alarm time. Time and timer ticks can advance naturally.

The smallest implementation is `m919/diagnostics/wake-check.asm` plus `m919/tools/test-wake-check.py`, its declared pipeline check and documentation. Compile the status offset, EBDA size and NMI policy from their existing owners. Validate the ROM header and current BDA/EBDA, require SMM status 1, reject protected/V86 entry or IF clear, and reject an active RTC interrupt/SET bit or masked IRQ0 before mutation. Require valid RTC power and its normal divider. Preserve the actual inactive alarm fields, B, PIC masks and INT4A vector.

Use INT1A AH02's BCD 24-hour result to calculate an alarm two seconds ahead, including midnight rollover. Install a private INT4A callback through DOS. Use INT1A AH06 to arm the real alarm owner, including stale-C acknowledgement and IRQ8/cascade routing. Poll the observed callback against five seconds of BDA ticks, with day-wrap handling and a finite instruction guard. No clock is stopped, so this software timeout can execute. Cancel through AH07, restore the inactive native alarm values and B, and drain any owned IRQ8 through actual int70 before restoring masks/vector. Return the configured NMI/index policy. Preserve time/date, RTC A, clock/cache/SMRAM policy and the flash artifact.

Codes: W0 means current SMM status 1 and scheduled alarm callback observed, with cleanup complete. W1 means incompatible ROM/state or SMM not ready. W2 means RTC/interrupt ownership is busy. W3 means RTC/time/arming was rejected. W4 means no matching callback within the software bound. W5 means the owned IRQ8 did not drain, so its pending state is not certified despite restored configuration. WX requires plain DOS. A W0 result is not a clock-transition result.

The Phase 2 drain finding is accepted. An IRQ0 tick or absence of another callback does not prove IRQ8 cleanup. Poll IRQ8 IRR/ISR with interrupts masked between observations. Permit the real IRQ8 handler to execute between bounded polls, and require both requests/in-service bits clear after its C read and EOIs. A pending-at-cancel fixture must reach the actual handler. On drain failure report W5, restore saved policy/vector, and require a restart before a later clock experiment. Do not claim that an unavailable hardware event can always be recovered by software.

Authoritative clause dispositions and Scenario Proof:

| Boundary | Source and invariant | Discriminator and contrast | Production path and oracle | Runnable check |
| --- | --- | --- | --- | --- |
| B15 | User board-only/variable-state rules; existing SMMSTATE qualification. Mapped. Unknown state and unsupported mode decline before alarm/vector mutation. | Vary each mode, IF, header, EBDA, readiness, RTC B/validity/divider and IRQ0 predicate independently. | Actual COM gate through DOS result; no alarm/vector mutation on each rejection. | `python -B m919/tools/test-wake-check.py`: guard cases. |
| B16 | Shared RTC time/alarm/int70 contracts and corrected donor alarm source. Mapped. Only a new enabled alarm earns the callback result. | New future alarm versus stale C, periodic/update causes, and no alarm; include native binary/12-hour time and second/minute/midnight rollover. | COM calculation, actual INT1A, RTC/PIC seam, actual int70 and callback, COM result. Exact scheduled values, cause gate and both EOIs. | Same command: scheduled/stale/other-cause cases. |
| B17 | User preserves existing owners; donor saves temporary policy. Mapped. Every returning path restores saved configuration and callback ownership. | Distinct original alarm/B/masks/vector against assumed defaults; success versus timeout/arm rejection and owned pending IRQ8 at cancel. | Complete COM/BIOS/IRQ path through cleanup and DOS exit. Exact restored policy; drained IRR/ISR for normal cleanup, explicit W5 otherwise. | Same command: restoration, day-wrap deadline and pending-drain cases. |
| B18 | User minimal handoff and no-PS/2 rules. Mapped. Diagnostic makes no CPU-power/cache/SMRAM changes or flash replacement. | Explicit diagnostic entry versus unchanged bench/normal firmware. | Exact W output; complete I/O trace permits only RTC/PIC; original full flash bytes and identity remain unchanged. | Same command: output/I/O/image preservation checks. |

The current SMM command and cache transient obligations remain opaque unchanged source, rather than new diagnostic obligations. Electrical STPCLK/CLK behavior remains opaque physical evidence. No new record collection or aggregation exists. Each saved field and result owes its own contrast. No PS/2, broader cache/IDE testing, full power manager, normal idle activation or new dependency belongs in SGW1.

Record exact per-case results in the existing ignored task record. Finalize the relevant documentation, obtain fresh boundary trace closure for B15..B18, then native checkpoint review against ACT1 before a local commit. Do not promote or publish a new ROM. The unchanged flash version remains 0.12.0 because SGW1 changes no firmware bytes.

## ACT2: Correct physical SMI delivery and retain useful failure evidence


This corrective checkpoint follows `6c445e79bb4d0e1edac013f394c6d0e111ab7b2e`. It owns the request-local reference controls, enable-before-request order, failed-command status and hidden entry trace. The firmware fix version is 0.12.1. Earlier installation, qualification, cache, reset and shared handler contracts remain required. This supersedes ACT1's inference that A0=0 suffices throughout a software request. It does not enable normal clock transitions.

The retained OEM PM-disable path clears A3.04 but retains A0.34 and A8.28. Software re-enable reaches C610 before restoring A3.04. Use those facts together instead of guessing individual field names. Save actual A0/A8 values before WBINVD, apply the two reference masks only around the request, and restore both before L2/CR0 and IRQ return. Keep stack metadata reads inside the cache-off window read-only. Preserve the complete existing cache initialization sequence.

Latch an initialization failure's command status in board-owned EBDA. A missing reply is not proof that SMI never arrived. One owned SMRAM trace byte records entry, the cookie predicate and the source predicate without modifying interrupted CPU state. Read both bootstrap and final markers only on early initialization failure after sources are quiesced, then close the manual view. Publish trace validity only after inspection. The DOS reader validates the current ROM/EBDA, remains read-only, and displays a compact extended code. Unknown or older trace data does not earn a new interpretation.

The applicable source clauses map to B7..B14 and B19 below. Unchanged CPU naming, generic installer/save map, normal APM and other-port behavior remain opaque. Electrical reset, sustained SMM stability and a clock backend remain outside this checkpoint. No new Setup state, device power policy or PS/2 access belongs here.

| Boundary | Source and invariant | Discriminator and contrast | Complete path, oracle and exact check |
| --- | --- | --- | --- |
| B7..B10 | Existing ACT1 installation, protection and software-source clauses. Mapped. Preserve cold/warm qualification, relocation, fresh ping and failure cleanup with the corrected control tuple. | Actual controller/CPU gates; normal source versus absent/source-cleared delivery; final view open versus closed. | Actual startup/command/handler/RSM/next POST owner. Existing installer, hidden-memory, no-reply and source contrasts in `python -B m919/tools/smm_activation_proof.py`. |
| B11 | ACT1 preservation plus actual reference controls. Mapped. Save/restore variable A0/A8 without cache-off RAM writes. | Nondefault A0/A8 and dirty cache state; reply versus timeout. | Actual runtime wrapper, installed handler, RSM and caller return; exact A0/A8, cache, CF8, NMI, stack and caller equality in the same command. |
| B12..B14 | Existing reset, unchanged consumers and image integrity clauses. Mapped. Preserve reset/reinstallation, no-AUX and fixed image layout. | Both reset owners, cold/warm SMBASE, incompatible inputs and unchanged shared source. | Existing reset/startup cases and same command's assembled image checks. Reuse unchanged CPU/shared proof results and direct source/byte identity. |
| B19 | User minimal hardware handoff and failure discrimination. Mapped. Hidden trace is private, noninvasive to saved CPU context and read only after quiescence. | No delivery `(0,0)` versus source rejection `(6,0)` or warm `(0,6)`; valid versus absent marker; ordinary/stale/wrong-cookie source contrasts. | Actual failed startup to marker inspection and closed-view return, plus actual read-only DOS entry. Same command's entry-trace and SMMSTATE cases assert exact latch/code, scratch-only SMM writes and saved-state preservation. |

Keep BAIOS-004 active. Finalize these owner descriptions, run fresh checkpoint trace closure for B7..B14/B19 and native review, then save the local checkpoint. Do not rerun unchanged validated matrices or publish a new release. Physical SMM/RTC observations are retained in the existing ignored result record and current support document.

## SGC1: One explicit clock request with an owned RTC wake

This subtask follows the ACT2 local checkpoint. The firmware feature version is0.13.0. Normal POST and APM policy stay unchanged. Add one board-private command and CLOCKCHK.COM. Reuse the existing SMM cache wrapper and the proven WAKECHK alarm/callback/cancel/drain owners. Keep the ordinary WAKECHK image byte-identical. The physical prerequisite is S1 and W0; neither is an electrical clock qualification.

Use the retained Phoenix native-E inactive path, profile 9Dh. Its positive native mode00 SMM test selects this path for supported Intel SL and Am5x86 CPUs. Require the current qualified CPU/controllers and mode00. A4 low2 must already be1, and SB56 low4 must already be2. Decline C8 or C9 otherwise, without changing Setup. These gates preserve live PCI, ISA and keyboard clock encodings during the request. Read hardware; Keep Current is not a fixed encoding.

The E header adds a versioned private descriptor and an F far entry. The existing F owner rejects protected mode before E access. Only a matching software-source, cookie and command2 reaches the new stackless board handler. Existing shared commands0/1 and the generic shared handler remain unchanged. Hidden scratch belongs to the installed board image; ordinary RAM and interrupted CPU state remain unchanged except the documented reply fields.

Before mutation require the deliberately armed RTC alarm, no SET/periodic/update owner, no pending/in-service IRQ8 and compatible live clock fields. Save actual A0/A4/56/80/91/92/port61 and CF8. Enable91.01, then use reference order A0=(old&FC)|2, SB56=(old&F0)|2, port61&FC, A4=(old&60)|9D, eighteen NOPs. Sample A2 and IRQ8 without reading RTC C. Always return through full-on cleanup: clear80.C0, clear92.80, pulseA3.20, write savedA4|10, restore saved56, then restore exact savedA4 and the remaining saved fields before RSM. Keeping the source's intermediate full-on write before exact restoration is deliberate. The enclosing wrapper restores A0/A8 before L2/CR0.

The donor's persistent inactive branch, device callbacks, software APM notifications and timer rearm are explicitly omitted: this single diagnostic owns no peripheral or normal power policy. Its alarm is a new two-second deadline owned through actual INT1A/int70, rather than the donor's configured daily alarm. Restore the actual RTC fields, PIC masks and vector, and the established PIC read-selector0A and board NMI policies. A request that never resumes needs a power cycle; a software timeout cannot execute while its clock is stopped.

C0 means IRQ8 was already pending at the end of the request window and the real alarm callback and cleanup completed. C6 means the window continued before the alarm, then callback and cleanup completed. Neither proves Stop Grant or the external CLK state. C1 is incompatible firmware/SMM, C2 busy/expired alarm, C3 RTC rejection, C4 callback timeout, C5 undrained IRQ8, C7 no fresh SMI reply, C8 PCI encoding mismatch, C9 ISA/keyboard encoding mismatch, CX unsupported execution mode. There is no automatic clock policy, new Setup control, generic extension framework or raw-register command interface.

| Boundary | Source and invariant | Discriminator and contrast | Complete path and oracle | Check |
| --- | --- | --- | --- | --- |
| B20 | Board-only and live-configuration rules. Mapped. Reject unsupported mode/header/CPU/controllers/SMM before a clock write. | Each gate independently false versus qualified entry; same cookie with wrong source versus matching software request. | Actual COM/F wrapper/installed handler to result; no clock request on decline. | `python -B m919/tools/test-clock-check.py` |
| B21 | Existing PCI/ISA/keyboard owners and retained profile. Mapped. No transient retiming of those fields. | A4 low2=1 versus0/2/3; SB56 low4=2 versus an ISA-only or keyboard-only difference. | Same composed path, C8/C9 and zero request edges; exact source bytes/order when compatible. | Same check. |
| B22 | Existing RTC ownership and controlled future alarm. Mapped. Only a newly armed nonexpired alarm can precede request. | Fresh versus already observed/pending alarm and active RTC owner. | COM, actual INT1A, installed SMM entry, actual int70/callback/cancel/drain; expired case declines before A4 edge. | Same check. |
| B23 | One-shot source adaptation. Mapped. Every returning path completes exact configuration restoration and correct event result. | Alarm pending during window versus immediate return; no delivery, callback timeout and pending-at-cancel; nondefault snapshots including A4=01 versus11. | One actual COM-to-firmware-to-RSM-to-IRQ-to-DOS path; ordered full-on I/O plus exact terminal controls/cache/caller/RTC/PIC/vector and policy equality. | Same check. |
| B24 | Shared and board owner preservation. Mapped. No ordinary RAM/CPU mutation in SMM, no unrelated activation. | Correct source/cookie versus unrelated/stale/unknown command; tool versus ordinary WAKECHK and normal POST/APM. | Actual installed handler and caller plus original WAKECHK byte identity; existing unchanged shared/cache owners remain opaque. | Same check and focused activation proof for changed board image. |
| B25 | Physical image contract. Mapped. Fixed image layout, checksums and startup survive. | Both E/F banks and reset entry versus wrong layout. | Actual built image integrity and reset-target checks, no vendor input changes. | Same check/build integrity. |

No collection aggregation is added. Opaque seams are CPU save/RSM, PCI/RTC/PIC hardware and DOS vector/output services. Tests must execute all in-scope firmware owners together, not replace the command or IRQ handler with mocks. Source I/O order is an oracle independent of final byte equality. The fresh Phase2 findings are accepted: separate SB56 gate, honest PIC selector policy and ordered intermediate full-on restore. Record results in the ignored task record. Electrical STPCLK/CLK is a physical observation, not an emulator result.
