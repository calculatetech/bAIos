# Shared cache lifecycle design

This developer specification describes the common process. Controller transactions, migration details and validation records belong to their ports.

## Required behavior

Keep cache discovery, capacity, qualification, initialization and activation as separate facts. Unknown capacity remains unknown. Preserve requested settings, effective saved settings and active hardware state separately.

Use a short startup test with two complementary address-derived write/read passes over the established cache capacity. Where meaningful, add a fixed set of normal-mode address witnesses. The test budget scales with cache capacity rather than installed RAM. Comprehensive stress and DMA checks belong in development validation.

The adapter must make the test exercise external SRAM. A successful DRAM readback is not a cache test. Run the short check each normal boot instead of using a persistent certificate to bypass it.

## Adapter boundary

Use the existing assembly-time board composition. Keep early preparation, after-RAM work, final activation and reset at the board's established entry points. Do not add a runtime board registry or register interpreter.

Preserve each complete reference transition, including its prerequisites, stack, interrupts, NMI, A20, segments, timing, tag initialization, fill and return. A common phase binding cannot insert calls or diagnostic operations into a sensitive temporary mode.

Apply eligible saved policy through the existing activation owner. Preserve disabled, absent, ambiguous and failed outcomes. Recovery and deliberate reset keep their established owners. Optional Fast Boot or skip keys cannot bypass mandatory memory initialization.

## Migration

Share the workload and transition vocabulary first. Then integrate each adapter without changing its hardware transaction. Compare source relocation against its original emitted image. Treat intentional test-policy changes separately from retained initialization.

The [port migration reference](../../pb430/docs/plans/BAIOS-003-cache-lifecycle.md) retains the detailed transition scenarios and controller adaptations. Individual ports own their outcomes and evidence. The [shared source contracts](../development/firmware.md) describe reusable primitives.

## Implementation specification

Required outcome: one assembly-time cache phase owner and one common transition proof entry, with a concise startup workload and complete existing controller transactions.

The common phase owner expands the adapter's early preparation, after-RAM and final operations at existing call sites. The reset binding names the complete existing reset owner. It does not wrap the owner's sensitive transaction in another call. A phase with no separate operation emits no instructions. Keep existing outer memory and timing hooks.

Extract the existing address-derived two-pass loop as an inline shared primitive. The adapter supplies the span, failure destination and optional invalidation instruction. Keep the existing complementary word-pattern primitive for adapters with an explicitly accepted exception. The generic short test adds only a fixed number of normal-mode address witnesses. Count mandatory reference initialization separately from qualification work.

The dword primitive clobbers EAX, EDX and EDI. Success leaves EDI at the exclusive end. Mismatch leaves EDI at the failing dword and EAX as its full expected value; the adapter reads the observed dword before recording failure. Preserve live controller-policy registers. Prove first- and second-pass mismatches, including an upper-half-only error at the last dword, through the existing safe recovery terminal.

Normal-mode tag witnesses use at most two competing address pairs at one cache index. The first compares the scratch base with the next cache-capacity boundary. The second compares that base with the highest distinct complete cache region below both installed scratch RAM end and the selected mode's cacheable limit. Round the latter address down to a cache-capacity boundary. Skip a pair if there is no distinct eligible region. Assert actual external indices, tags and cacheability, including installed RAM beyond the cacheable limit. These witnesses are a short startup screen, not comprehensive tag qualification.

Installed RAM beyond the cacheable range does not by itself disable cache. Preserve the existing adapter's activation of its cacheable subset. Distinguish that upper limit from the minimum initialized RAM required by a complete reference fill.

Retiring an old certificate preserves the preceding saved choices. Recognize its adapter-selected legacy chipset tag when certificate bytes occupy the newer format markers. Exact packed markers retain precedence. Check the complete old checksum, copy only its saved-choice prefix, and use current defaults for the retired tail. Never restore certificate reuse or publish a new storage format.

The normal-use floor includes cold POST, changed and unchanged saved choices, discarded drafts, reset continuation, failure recovery, optional RAM-test skips and actual final activation. The ceiling excludes new cache modes, CPU tuning, changed hardware recipes, new persistent state and a runtime adapter registry. Independent external devices may be modeled; in-scope firmware decisions must execute.

### Prior plan reconciliation

Source: `06be436b2a026faa0d52c51490de1f1f08b1accb:pb430/docs/plans/BAIOS-003-cache-lifecycle.md`, all 187 lines.

Carry its accepted adapter-specific exceptions, complete reference requirements, S1-S10 transition obligations and physical evidence separation. Its earlier checkout and missing-hook observations describe historical source. Do not restore removed certificate machinery to satisfy obsolete checks.

Scope: unfinished subtasks T1-T5. Consolidate these into one integration checkpoint, because the shared expansion, adapter bindings and common proof entry form one deliverable. This replaces their old separate checkpoint order, not their acceptance criteria. Keep source relocation byte-preserving. An intentional startup-test policy change has its own workload and failure oracle.

### Boundary inventory and Scenario Proof

The following inventory accounts for the shared requirements above and the port reference's current clauses. Every retained boundary requires its own actual result, not only a suite count. Port-specific interpretations and fixture details remain in port developer documentation.

| Boundary | Source clauses and disposition | Discriminator and minimal contrast | Production path and required terminal oracle | Runnable proof |
| --- | --- | --- | --- | --- |
| B1: phase ownership | Shared Adapter boundary; reference phase bindings and T1-T5: mapped. | Existing safe phase order versus a missing, duplicated or displaced phase. | Reset through early work, RAM, final gate, activation and boot; observe actual owners in order. | `python -B shared/tests/test-cache-transitions.py --port all` |
| B2: evidence and eligibility | Shared facts, unknown capacity, saved policy and absent/ambiguous/failed outcomes; reference state and S1/S6: mapped. Variable configuration rule: mapped. | Known independent SRAM versus absent, ambiguous, failed or disabled; toggle each saved request independently. | Discovery through real qualification, eligibility, reporting and boot or existing recovery; saved choices and active state remain distinct. | Common transition proof, per adapter. |
| B3: short workload | Shared two-pass, actual-SRAM and fixed-witness clauses; reference short-check steps and explicit pattern exception: mapped. | Same cache capacity with small/large installed RAM; independent data/address failure. | Actual POST test reaches all SRAM entries with two complementary passes, bounded witness traffic and restored state; mandatory fill is separate. | Common transition proof, plus adapter external-SRAM checks. |
| B4: repeated startup | Shared no-certificate clause and reference warm-reuse exception/S3/S7: mapped. | Old certificate absent/present; changed save followed by unchanged save and ordinary reset. | Same machine reaches required next-boot test or accepted warm reuse without sticky cold classification or changed user choices. | Common transition proof. |
| B5: complete transactions | Shared reference-preservation clause; reference prerequisites, tables, frames, timing, tags, context, return and no transient instrumentation; AGENTS cache setup: mapped. | Identical before/after controller inputs. | Early, final and reset transactions preserve complete unfiltered instruction/I/O/access order, table bytes and context. | Adapter reference comparisons and relocation image comparison. |
| B6: recovery | Shared existing recovery/reset clause; reference S9 and accepted interrupted-RAM classification: mapped. | Completed mismatch versus pass or interruption without mismatch. | Actual failure owner through acknowledgement, safe restart/halt and explicit saved retry; failure details remain useful and no false qualification is published. | Common transition proof and adapter recovery checks. |
| B7: optional RAM work | Shared Fast Boot/skip restriction; reference S8: mapped. | Full optional sweep versus Fast Boot or Esc. | Real reset, mandatory memory preparation, optional sweep, restoration, required cache work, final gate and boot. | Common transition proof and adapter RAM-order checks. |
| B8: relocation | Shared emitted-image comparison; reference relocation and diagnostic composition clauses: mapped. | Before/after build with identical inputs/defines. | Complete physical production variants and affected diagnostics are byte-identical where only source ownership changed. | Existing builders plus full-byte comparison. |
| B9: dirty data | Reference retained WT/WB eligibility, tag limits, fault/alias and DMA/reset contracts: mapped. | Supported mode and actual range boundary; exact dirty payload through DMA/reset. | Actual POST, reference initialization, final activation, service and consumer preserve policy, data and status. | Common transition proof plus independent DMA/reference checks. |
| B10: saved versus active | Reference S1-S5 and state/publication clauses: mapped. | Save versus discarded/canceled draft, defaults Save/Discard, changed versus unchanged; effective publication before rejected overall Save where applicable. | Real Setup keys through publication or rejection, existing reset, old active teardown and next boot's hardware state. | Common transition proof. |
| B11: complete common proof | Reference common driver, all applicable scenarios and one causal execution clauses: mapped. | Exact required result set versus missing, duplicate or later failed result. | Shared runner executes every applicable adapter scenario, reports unsupported modes explicitly and propagates failures. | Common transition proof and its result-inventory self-check. |
| B12: flash integrity | Reference artifact size/layout/checksum/retained input/reset/SUM32 clauses and AGENTS candidate checks: mapped. | Complete artifact group versus selected inputs and manifest. | Existing builder and integrity owner validate the complete image and required members. Physical confidence remains separate. | Existing per-port ROM integrity commands. |
| B13: other shared consumers | Existing native cache and shadow ordering in other shared-shell adapters: mapped. | Existing enabled/disabled hardware selector and passing/failing native qualification. | Cold and warm POST retain native transactions, CPU instruction limits, final shadow-before-cache order and boot. | Existing adapter qualification, boot and instruction checks through the common runner. |

Other clause dispositions: the ban on a runtime registry/interpreter and repository source/output ownership are implementation restrictions (`non-boundary`). Historical checkout, publication and old review-pass records are `non-boundary`. Existing service-resume bypasses, effective Setup storage, unrelated timing policy and hardware operation internals are `opaque`; their composition and preservation obligations are mapped above. New CPU tuning, physical electrical qualification and unrelated services are `deferred` to their existing owners. There is no unresolved product contract gap.

### Validation and delivery

Use the common proof's port selection for focused execution. It must inventory applicable scenarios and preserve independent controller models and reference comparisons. Add the common entry to each port's validation declaration. Do not replace production Save/reset hops with successful metadata. Store exact commands, results, source identities, image comparisons and review bindings in the ignored task result.

Before review, build affected production and diagnostic images, validate integrity, complete every mapped scenario and run fresh boundary trace closure. Review the complete integration candidate once; review correction deltas separately if needed. Keep physical claims limited to reported hardware observations. After clean review, close the roadmap item and retain the current flash candidates.
