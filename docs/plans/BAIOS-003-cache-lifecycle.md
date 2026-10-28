# BAIOS-003: Shared cache lifecycle and migration


## Outcome and scope


Use one cache lifecycle, a concise startup cache check and one set of transition tests for Presario 800, PB430 and M919. Use Presario's two-pattern check as the starting point. Replace M919's expensive qualification workload. Each board adapter retains the complete hardware initialization and reset transactions that its controller requires.

This specification defines the complete migration. The accepted PB430 implementation boundary below records the current subset; the repository task remains Active until the other adapters and shared owners are complete.

The implementation must make the common process visible in shared source and executable tests. Three renamed private routines alone do not satisfy this outcome. Common code owns phase placement and common test cases. Adapters own hardware operations, eligibility and reset decisions.

## Accepted PB430 implementation boundary

The 2026-10-20 bench instructions authorize a bounded PB430 migration. Its shared primitive uses two complementary full-capacity word-pattern passes and retained unique address witnesses. The adapter preserves stock presence/size discovery, pre-policy prerequisites, line width, complete activation/reset transactions and qualified warm reuse. Shared startup marker classification preserves settings after an interrupted RAM test; only a comparison mismatch creates a recovery notice.

This supersedes the earlier address-derived-pattern and every-normal-boot requirements only for the accepted PB430 adapter. No persistent CMOS certificate is added. The complete common phase owner and shared transition driver are still future work, and the Presario/M919 cache migrations remain pending. Do not mark T1/T2 or the complete repository task finished on the strength of this subset.

The source publication is a maintenance update. Keep the existing ROM version/date and release; the user defers new releases until meaningful functionality such as SMI.

## Source baseline and reconciliation


The source base is `deb988c46833f5b2deef6b23f461b3010d64e79c` on `task/m919-kickoff`. The current checkout also contains staged, unstaged and untracked port work. Read the live files named below before implementation. Do not reconstruct this design from HEAD alone.

There is no origin remote. An isolated local clone on `task/baios-003-design-review` supplies the documentation review context. Its baseline contains a source snapshot of the live checkout. The primary index remains outside this task. Runtime implementation needs its own isolated branch after the port baselines are reconciled.

Carry the cache, timing and reset decisions in [PB430-001](../../pb430/docs/plans/PB430-001-port.md), especially its cache-choice reset correction. Carry M919's controller initialization, selected-mode eligibility, safe recovery and dirty-data requirements from [M919-004](../../m919/docs/plans/M919-004-timing.md). Its expensive qualification workload and certificate machinery are superseded below. No pending Plan-history captures were present during this design pass.

Prior plan reconciliation: the user's instruction to discard M919's slow qualification supersedes this plan's original preservation-only approach for that workload. Source: the current user instruction and M919-004's full-pattern, repeated-coherence and retained-validation requirements. Replacement: a short startup check based on Presario, run each normal boot without a persistent test certificate. Scope: unfinished BAIOS-003 subtasks T1-T5 and the M919 test policy they adopt. Preserve unrelated M919 timing choices, hardware initialization, eligibility, recovery, reset and public services. No runtime change is made by this design revision.

The [reference cache rule](../../AGENTS.md#reference-cache-setup) controls every extraction. The [shared-source contract](../../shared/README.md) requires complete Presario ROM byte preservation during source relocation. Physical cache stability remains separate from source, reference, fixture and emulator evidence.

One discrepancy remains in the live source. M919 defines `BOARD_POST_RAM_CACHE` as `chipset_post_ram_cache`, but the current shared POST does not invoke that binding. The replacement must establish its real production entry and ordering. Do not wire in the discarded long test merely to satisfy the old plan. This document changes no invocation and claims no currently passing complete path.

## What the three ports actually do


L1 is the CPU's internal cache. L2 is the board's external cache. Discovery establishes presence and geometry. Qualification tests whether a discovered configuration meets the port's software checks. Initialization establishes usable tags and controller state. Enabling selects the operational policy. These are separate results even when one transaction produces several of them.

| Port and source owners | Discovery and test evidence | Activation and reset obligations |
| --- | --- | --- |
| Presario: [bios.asm](../../presario-800/src/bios.asm), `startup`, `init_external_cache`, `warm_reset`; [VLSI policy](../../presario-800/src/chipsets/vl82c481/policy.inc), `chipset_late_cache` | Startup holds caches off. The late owner calls the complete direct-SRAM probe at known probe timings. It detects banks and capacity, tests opposing address-derived patterns across the detected span, and performs normal-mode fill/eviction. ZF/CF distinguish pass, SRAM failure and no response. It then restores selected policy and performs a runtime RAM check. | Preserve CEN and CR0 ordering together, protected-mode transitions, GDTR, A20, scratch, tag controls, timing and cacheability restoration. Preserve the software warm entry and shadow teardown. The `enable_cpu_full_speed` helper has fixture callers, but is not the current production POST entry. |
| PB430: [cache.inc](../../pb430/src/hardware/cache.inc), [startup-core.inc](../../pb430/src/hardware/startup-core.inc), [board-core.inc](../../pb430/src/hardware/board-core.inc), [timing-policy.inc](../../pb430/src/hardware/timing-policy.inc) | Cold startup probes presence and size, selects reference tables and retains the cold shutdown-test continuation. A valid warm result can be reused. Presence with an ambiguous size remains a distinct result. `HW_CACHE_QUALIFIED` means accepted reference size evidence, not a full data/tag stress test. | Preserve the complete stock activation: physical `0030:0100` stack and parent frames, original fill bytes, temporary IRQ0 handler, IF/NMI order and controller I/O. Restore stock timings before activation, then reapply runtime timings. Reset compares effective saved L1/L2 choices with the active record. Changed choices select cold initialization. Teardown still uses the complete old active record. |
| M919: [cache.inc](../../m919/src/hardware/cache.inc), [cache-validation.inc](../../m919/src/hardware/cache-validation.inc), [chipset-core.inc](../../m919/src/hardware/chipset-core.inc), [board-core.inc](../../m919/src/hardware/board-core.inc) | Early forced-hit discovery runs each boot. The separate qualification owner tests the selected mode with full-span patterns and tag/coherence checks. Matching retained validation can skip that expensive test, but cannot skip fresh discovery. The intended post-RAM invocation needs the reconciliation described above. | Preserve WT priming before selected WB mode, the mode-dependent tag limit, shadow and flat-segment handling, scratch restoration and failure details. The certificate remains bound to the existing settings, geometry, CPU and ROM identity. Warm reset preserves its write-back flush and A20 reopening before the controller reset pulse. Physical SRAM stability is unresolved. |

WT means writes also reach RAM. WB means modified cache lines can defer RAM writes. Intel's [271329-003, section 7.7.1](https://ardent-tool.com/CPU/docs/Intel/486/datasheets/271329-003.pdf#page=109) distinguishes `INVD` from `WBINVD` for write-back IntelDX4 caches. This supports preserving the correct flush operation. It does not establish a universal sequence for the CPUs or controllers in these ports.

PB430's [porting lessons](../../pb430/docs/porting-lessons.md) explain why neighboring owners belong in the cache transaction. A register-only comparison missed reset continuations, initialized fill memory, stack placement, timer accesses and diagnostic I/O. Preserve these lessons as adapter requirements. PB430 has narrower cache-test coverage than Presario. That does not weaken the evidence for its reference initialization or mean its hardware is known to be unreliable.

## Normal startup test baseline


Presario is the baseline for the amount and shape of POST testing. Its current `init_external_cache` detects banks and capacity, then writes and reads the detected span using two complementary address-derived patterns. The two passes transfer four times the cache capacity before normal initialization. They test data and address dependence together. Its later runtime RAM check is a separate operation, not part of this cache-only traffic count.

M919 currently uses four patterns, each with an initial readback and another readback after a full-capacity drain. It also clears the scratch span. Its separate coherence loop repeatedly primes and drains a full cache capacity while advancing address probes across installed RAM. The source establishes substantially more work, but no elapsed-time comparison was measured in this design pass.

The replacement process is:

1. Use the board's established presence, bank and capacity discovery. Reject absent, ambiguous or unsupported geometry.
2. Write and read two complementary address-derived patterns over the detected cache capacity. The adapter must make these accesses exercise external SRAM rather than ordinary DRAM or retained L1 data.
3. Execute the complete reference-supported tag initialization, fill and activation sequence in the adapter.
4. Where the adapter can make the result meaningful, use a fixed small set of normal-mode tag/coherence witnesses. Do not drain a complete cache for every installed-RAM address bit.
5. Restore temporary state, apply the eligible saved policy and report the actual result. On failure, use the existing safe disable/recovery path.

The normal test budget scales with cache capacity, not installed RAM. Instrument synthetic device traffic to enforce two full write/read passes and a fixed number of normal-mode witnesses. Account for mandatory initialization traffic separately. Do not add full-memory sweeps, repeated stress passes or a persistent certificate to make normal POST acceptable. Run the short check each normal boot. Keep special service-resume entries under their existing contract.

Presario's VLSI direct-SRAM mode, register values and flush order are not portable. M919 and PB430 adapters must establish equivalent access semantics from their own controllers. If a controller cannot expose SRAM directly, define and prove a bounded controller-specific check before claiming equivalent coverage. A passing DRAM readback is not a cache test.

Keep comprehensive fault, alias, dirty-writeback and DMA tests in the development suite. They prove the replacement's intended coverage and retained hardware contracts. They do not require the old M919 stress workload to remain in ordinary POST. Removing that workload also removes its performance and full-address-coverage assertions from the runtime acceptance criteria. Preserve saved user choices when retiring the certificate bytes.

## Shared process and adapter boundary


Use the existing assembly-time `BOARD_*` composition model. Do not add runtime board detection, a controller registry or a generic register interpreter. Proposed bindings describe safe phase boundaries. They do not permit calls inside a temporary hardware mode.

| Phase and proposed binding | Shared obligation | Adapter obligation and exit |
| --- | --- | --- |
| Early preparation, `BOARD_CACHE_EARLY` | Keep the phase at the board's established startup point, before visible RAM testing and ordinary device work. Preserve service-resume bypasses. | Establish the board's safe baseline and perform early discovery where its reference requires it. Preserve mandatory DRAM initialization and cold/warm prerequisites. Leave operational L2 off before ordinary RAM testing. |
| After RAM, `BOARD_CACHE_AFTER_RAM` | Place the boundary after RAM restoration and the pending early Setup gate, before peripherals. A board with no separate work emits no instructions here. | M919 can run the replacement short check here. Do not call the old qualification/reuse path. Presario and PB430 retain their required integrated late initialization. A temporary test must return to the required pre-activation state. |
| Final activation, `BOARD_CACHE_FINISH` | Invoke after the final Setup gate and before final effective-state reporting and option-ROM handoff. | Execute the complete board transaction. It can combine discovery, testing and activation. Apply only the board-supported request, preserve eligibility gates, restore runtime policy and finish its existing verification/recovery path. |
| Reset, `BOARD_CACHE_RESET` | Treat reset as part of the same lifecycle and test it through its real public trigger. Keep the reset implementation port-owned. | Preserve the existing reset classification, dirty-data obligations, teardown and continuation. PB430 retains its saved-versus-active comparison and old-record teardown. Presario and M919 do not acquire that comparison. |

These names are proposed assembly bindings, not new callable functions with a universal register ABI. Implement them as aliases or macro expansions that retain the original call instructions and inline code. Presario's early holdoff can remain inline. A reset binding can identify the existing complete `warm_reset` owner without adding a wrapper. Do not add a second call frame around PB430's stock parent or fill.

At each boundary, document the existing caller contract: registers and result flags, stack location, IF/NMI, A20, segments/GDT, execution shadow, scratch ownership and final controller state. Adapters consume private result flags before returning to shared decisions. Recovery can transfer to an existing restart or halt owner instead of returning. Normal exits restore temporary context or establish the existing documented final state.

The first implementation adds a small `shared/src/firmware/cache-lifecycle.inc` for common phase expansions. Both the shared donor shell and Presario's separate shell consume it at their existing safe sites. Preserve the current outer RAM/timing hooks until their composition is proved. Do not migrate the whole Presario shell as part of cache work.

Share Presario's two-pattern test policy and safe loop mechanics where the adapters establish equivalent external-SRAM access. Keep hardware detection, CPU-cache instructions and reference initialization inside the adapters. Similar loops alone do not prove equivalent bus behavior. A shared function must not insert stack accesses into a previously stackless window. The discarded M919 diagnostic loops are not part of the preserved initialization contract.

## State and policy rules


Keep active settings, Setup drafts, CMOS records and retained evidence with their existing owners. Do not add a shared persistent certificate or a second writer for hardware state. Keep existing POST strings and help with their current renderers during the first migration.

Common tests observe these facts separately:

- Requested, effective saved and currently active L1/L2 choices.
- Presence and accepted capacity, including present with unknown capacity.
- Evidence kind: untested, reference size accepted, short startup check passed, legacy full test passed/reused, or failed. Legacy evidence cannot replace the new short check.
- Eligibility, effective L1/L2 state and operational mode.
- Actual cold/warm path, phase visits, context restoration and boot/recovery terminal.

Normalize these observations in test adapters. Do not allocate a new firmware status record without a production consumer. M919's existing certificate is current-source context only. The target runs a short test each normal boot and retires that certificate without changing saved user choices.

The common policy is to enable only what the adapter establishes as eligible. PB430 requires L1 and accepted size before L2 activation. Preserve Presario and M919's own L1/L2 behavior. Do not turn PB430's dependency into a universal rule. Preserve absent, ambiguous, failed and disabled outcomes without reporting them as successful qualification.

Saving a draft does not itself prove which hardware is active. PB430 compares effective saved settings at reset, including after a later Save verification failure. M919 applies the effective saved memory/cache policy to the replacement check and final enable. Its old certificate must not bypass the new test. Discarded drafts and unrelated edits do not change the effective saved policy.

## Reusable transition tests


Add the common scenario driver to `shared/tools/cache_proof.py`. Its future executable entry is `python -B shared/tests/test-cache-transitions.py --port all`. The three ports supply adapters using their existing hardware fixtures. This command does not exist yet.

The adapter creates a machine, drives actual Setup keys, requests the real reset trigger and observes external devices, firmware visits and terminal output. Test adapters must not replace firmware decisions or seed a passing qualification result for a composed case. Keep the existing independent SRAM/tag models separate. A common driver does not require identical controller physics.

The following rows define the future proof obligations. The shared command runs each applicable row for every port. A port-specific row must remain explicit in the complete result. Unsupported modes are declared, not silently skipped.

| ID | Discriminator and minimum contrast | Complete production path and required oracle |
| --- | --- | --- |
| S1 | Cold start with each of the four saved L1/L2 combinations | Reset vector through preparation, RAM, final activation and boot. Observe requested and effective state separately. Require each board's own dependencies, tables and restored context. |
| S2 | Changed saved L1, then changed saved L2, each in both directions | Actual Setup Save through old-state teardown, reset, initialization, final state and boot. PB430 must use cold tables after a changed choice. Other ports must preserve their own reset classification. |
| S3 | An unchanged Save followed by ordinary Ctrl+Alt+Del | Continue on the same machine after S2. Require the board's normal path, with no permanent cold request. PB430 retains its required warm initialization behavior. M919 discovers afresh and performs the replacement short check without certificate reuse. |
| S4 | Saved edit versus discarded draft, canceled Save and Defaults followed by Save versus Discard | Actual UI through reset and next boot. Only effective saved changes affect later policy. No discarded draft can change the tested or enabled tuple. |
| S5 | PB430 chipset publication followed by rejected overall Save versus confirmed Save | Real verification leaves Setup available after rejection. A later Ctrl+Alt+Del reads the effective saved record and selects required initialization. Preserve the old active record through teardown. Apply this case to another port only if its existing save pipeline has the same publication boundary. |
| S6 | Present accepted capacity versus absent, ambiguous or failed hardware evidence | Actual discovery and any applicable test to final reporting and boot/recovery. Unknown capacity stays unknown. No unqualified cache becomes operational. A faulty-hardware fixture proves detection behavior only. |
| S7 | Short check on small versus large installed RAM, with identical cache capacity; old certificate absent versus present | Real POST reaches the replacement check and final enable on every normal boot. Count external cache traffic: two full write/read passes and fixed normal-mode witnesses. Installed RAM must not multiply that work. An old valid certificate cannot bypass the check or alter saved choices. |
| S8 | Optional full RAM test versus Fast Boot or Esc | Reset through mandatory memory initialization, RAM restoration, final Setup and cache activation. Skipping optional work must not skip initialized fill memory, reference tables, restored timing or cache checks already required by that port. |
| S9 | Detected data/address failure versus a passing short check, then existing recovery and explicit saved retry | Real error owner through acknowledgement, safe restart or halt and subsequent saved retry. Preserve safe disable and useful failure details. Report a pass only after the replacement test finishes. |
| S10 | Supported WT versus WB, with RAM at and beyond the supported tag limit | The short check, reference initialization and final activation must use compatible selected policy. In the development suite, execute supported WB dirty-data DMA and reset paths through their real service owners. Preserve data and status. Do not add WB support to another port. |

For each case, record one causal execution from its real entry to the required terminal. Component calls cannot replace a missing Save/reset continuation. Capture all reference-window instructions, I/O, memory accesses and table rows. Never filter added POST writes out of an equivalence comparison.

Current commands below supply baseline evidence for subsets of the rows. They are not a claim that the new common suite exists or that all cases currently pass. Run commands from the repository root. Build and reference dependencies remain those of the existing port tools.

| Existing command | Evidence to preserve and extend |
| --- | --- |
| `python -B presario-800/tools/test-external-cache.py` | Direct probe, bank/capacity/data contrasts, restoration, warm holdoff and late policy. Add complete real Setup/reset transitions for S1-S4 and the applicable recovery path. |
| `python -B pb430/tools/test-port.py --case cache` | Independent stock/reference comparison plus cold, warm, composed and interrupt-window checks. Preserve all of these when adding the common driver. |
| `python -B pb430/tools/test-cache-transitions.py` | Changed/reverse/unchanged choices, discard/cancel, rejected late Save, active-record preservation and absent/ambiguous SRAM. This is the first reusable scenario source. |
| `python -B pb430/tools/test-ram-order.py` and `python -B pb430/tools/test-timing-recovery.py` | Uncached RAM, selected/stock timing order and existing recovery. |
| `python -B m919/tools/cache_proof.py cache-discovery` and `python -B m919/tools/cache_proof.py cache-live` | Retain fresh discovery, failure/restoration and production-path observations. Replace old stress-workload coverage expectations with the new short-check contract. Do not require the old missing hook to invoke discarded code. |
| `python -B m919/tools/timing_proof.py cache-persistence` and `python -B m919/tools/timing_proof.py cache-writeback` | Replace certificate-reuse assertions with per-boot short-check and old-certificate retirement checks. Preserve selected-mode eligibility, tag limits and dirty-data contracts in the development suite. |
| `python -B m919/tools/cache_proof.py cache-dma` and `python -B m919/tools/cache_proof.py cache-recovery-boundaries-live` | Existing service composition and recovery boundaries. Run the relevant WB cases through the timing proof as well. |

## Migration subtasks and acceptance


Each subtask needs implementation preflight, its named scenario results and native checkpoint review before a local checkpoint commit. The complete candidate then needs final review. Keep operational results in one ignored task record. No runtime checks or physical tests are claimed by this specification.

| Subtask | Outcome and allowed owners | Dependencies, runnable checks and checkpoint oracle |
| --- | --- | --- |
| T1: Common proof vocabulary | Add the shared driver/entry and the smallest adapters around existing port fixtures. Keep firmware unchanged. Map S1-S10 and distinguish current behavior from replacement acceptance criteria. | Establish completed PB430 inputs and record the current M919 path discrepancy. Run applicable current-baseline commands. Define the new workload and failure oracles without claiming the old code satisfies them. New M919 S7/S9 acceptance becomes runnable with T4. Checkpoint contains the common baseline driver and adapter documentation, not a claim that the replacement is implemented. |
| T2: PB430 adoption | Bind existing startup, final cache/timing and reset transactions to the common phase model. Preserve `stock_cache_proof.py` and exact transient bytes, accesses and frames. | T1 baseline. Run the shared command with `--port pb430`, both PB430 cache commands, RAM-order and timing-recovery commands above. Require S1-S6/S8-S9 and the reference comparisons, including all cold tables and unchanged warm transitions. Checkpoint covers the complete PB430 integration. |
| T3: Presario adoption | Include common phase expansions in the separate Presario shell and extract only safe adapter ownership. Preserve production and diagnostic ROM bytes and existing include consumers. | T1/T2 common owner. Run the shared command with `--port presario-800` and the external-cache command. Build both VGA variants and every diagnostic variant affected by relocation using the existing builders. Compare complete outputs against the pre-migration inputs, not only checksums. Any byte difference blocks a relocation-only checkpoint. Prove the actual late POST and warm-reset paths, not only helper callers. |
| T4: M919 replacement and adoption | Replace the heavy qualification with the Presario-based short check through a UMC adapter. Establish its actual POST invocation. Retire persistent test certificates while preserving user choices, required WT/WB initialization, eligibility, useful failure output, recovery and service behavior. | T1/T2 and reconciled M919 ownership. Run the shared command with `--port m919` and the revised M919 commands above. Require S7's traffic budget, detected pattern/address failures, selected-mode final state and all applicable S1-S10. Compare initialization/reset operations separately from intentionally removed diagnostic traffic. Keep unresolved physical stability explicit. Checkpoint covers the complete replacement, tests and adoption. |
| T5: Complete migration | Update shared/port documentation, retire consumed duplicate test orchestration, and keep useful independent reference/model checks. Do not add an unproved generic cache algorithm. | T2-T4. Run `python -B shared/tests/test-cache-transitions.py --port all`, all affected port regression matrices, builds and ROM-integrity checks. Require production-path trace closure and final native review of the complete candidate. Record physical confirmation separately for each changed board path under the repository hardware workflow. |

Every flash candidate must retain the required ROM size, system checksum, physical layout, original selected regions and reset target. For physical handoff, report the full image's additive SUM32. A synthetic pass cannot resolve M919's electrical stability or qualify a new PB430 timing choice.

## Decisions and design proof


| Decision | Reason and rejected alternative |
| --- | --- |
| Share lifecycle and transition orchestration first. | The same user events exist on all ports. Leaving three separate scenario drivers permits transition coverage to drift. |
| Keep complete reference transactions in board adapters. | A universal detector or register engine cannot preserve the observed stack, interrupt, reset and temporary-mode differences without rebuilding each adapter inside the engine. |
| Use Presario's concise check as the POST baseline. | Two complementary address-derived passes provide a practical starting point. Discard M919's repeated stress passes and per-address full-cache drains. Retire its persistent test certificate rather than preserving machinery whose purpose is to hide a slow test. |
| Keep test coverage explicit. | PB430 size acceptance, Presario's direct-SRAM test and the current M919 stress routine prove different things. Strong reference-initialization evidence is separate from diagnostic coverage. |
| Keep reset classification board-owned. | PB430 needs a saved-versus-active comparison. Requiring it on Presario or M919 adds behavior that their current reset paths do not use. |
| Add no CPU tuning or new stress-test algorithm. | BAIOS-005 owns CPU-specific performance work. Reuse Presario's established test approach through the selected board-adapter model. An arXiv algorithm search is not needed to select that existing baseline. |
| Preserve port decisions outside the explicit supersession. | The user's new direction replaces M919's expensive POST qualification and certificate requirements. Other unfinished port decisions remain authoritative. This plan does not mark PB430 complete or resume physical tuning. |

For this documentation pass, the plan and its roadmap link are `composes`. All executable owners and existing observations are `opaque`. Runtime migration, new tests, physical trials, CPU tuning and SMM are `deferred`. There is no changed executable entry point, so runtime trace closure does not apply to this pass.

| Boundary | Authoritative clauses and disposition | Design oracle |
| --- | --- | --- |
| B1 | User-selected design-first scope and roadmap implementation prerequisite: mapped. | Only this specification and its roadmap link change. No task moves to Active or Completed. |
| B2 | Roadmap common process, root complete-reference and no-instrumentation rules, shared adapter ownership: mapped. Required hardware initialization contracts: opaque. Existing M919 diagnostic workload: explicitly superseded for future implementation. | All three ports have phase mappings. Temporary initialization transactions, tables, restoration and reset authority remain indivisible and port-owned. The new short test has an explicit coverage and traffic budget. |
| B3 | Roadmap cold/Save/warm/recovery coverage: mapped. Existing port transition semantics: opaque. | S1-S10 distinguish saved requests, discovery, evidence and effective state, with port-specific outcomes and future runnable commands. |
| B4 | Shared Presario byte-preservation rule and reference/software/physical evidence boundaries: mapped. | Migration checkpoints require independent reference proof, composed terminal tests and separate physical evidence. Current commands are distinguished from the future shared entry. |
| Deferred scope | Live flash/finalization procedures, runtime extraction, CPU performance and SMM: deferred. | These add no edits or new support in this pass. Their existing owners remain reachable through the linked rules and roadmap. |

Validate the documentation by resolving local links and named current entry points, inspecting the complete two-file diff, and confirming source/ROM hashes and the primary Git index remain unchanged. The documentation review is a single full native review against the isolated source snapshot. Actual results belong in the ignored task record.
