# Shared ROM footprint


## Outcome and product boundary


Reduce occupied ROM space without removing supported features. Keep one shared owner for common firmware code, module interfaces, build accounting and validation. A fresh build must report resident bytes, private-module storage, temporary RAM and usable free space separately. Fixed-size flash files do not become smaller when their contents improve.

The user requested this work to leave room for future ACPI support. ACPI itself remains BAIOS-013. There is no assumed ACPI byte budget. Preserve current POST, Setup, Plug and Play, boot, disk, APM and cache behavior. Physical stability remains a separate hardware result.

The task base is `3b9bfdf160472f3ec582b38cc2b9105d929a0dca`, on the existing isolated branch renamed to `task/rom-footprint` in the single root worktree. The accepted uncommitted PnP, early-video and POST presentation changes are input, not disposable work. Their exact source and assembled-image identities are recorded in the ignored `.agent/test-results/rom-footprint.json`. Local and fetched main agree. No additional checkout is needed.

## Prior plan reconciliation


Carry the PnP contracts from `BAIOS-012-plug-and-play.md`, the shared contracts in `../development/firmware.md`, and the current accepted source. In particular, resource allocation precedes option-ROM use; resident publication follows the last private far return; early Setup cannot probe IDE; MP386 does not adopt PnP. The current POST presentation changes extend the earlier plan. This task changes their placement and common ownership, not their behavior. The preceding cache, PIO and SMM specifications remain opaque hardware and runtime contracts.

Applicable instructions are the root AGENTS file, `../repository-layout.md`, `../porting.md`, and each affected port's instructions and validation declaration. Existing hardware initialization sequences, source inputs and retained image regions remain authoritative. No pending Plan capture adds a conflicting requirement.

## Existing owners and supported model


| Owner | Classification | Responsibility |
| --- | --- | --- |
| `shared/src/firmware/setup.inc`, `post.inc` and their includes | composes | Setup control flow, read-only tables, rendering and POST presentation currently share a resident segment. |
| `shared/src/firmware/pnp-module.inc` and board module transports | composes | Private POST execution, imports and temporary-memory lifetime. |
| `shared/src/firmware/pnp-entry.inc`, `pnp-peripheral-post.inc`, `boot.inc` | composes | Public runtime entry, final private use, publication, release and boot continuation. |
| `shared/tools/rom.py`, port builders, candidate tools and validation declarations | composes | Assembly, placement, integrity, retained inputs and complete flash groups. |
| Controller, CPU, cache, disk and SMM hardware adapters | opaque | Preserve bytes and operations unless a directly changed interface requires a mechanical adaptation. |
| ACPI, new hardware features and new operating-system services | deferred | Separate tasks; this task provides measured capacity rather than speculative implementations. |

Normal use includes cold and warm start, early and final Setup, Save/Discard/Defaults, both retained VGA variants, public real/protected PnP calls after temporary storage is released, normal boot and natural resource-capacity limits. Preserve existing saved encodings, fixed device positions, literal foreign-segment text and all current user choices.

## Smallest implementation and subtasks


**F1 — shared POST and Setup code placement.** Extract the cooperating `setup_main`, video-mode, `setup_draw`, POST screen, summary and header bodies into shared include owners. Eligible ports place these bodies in their existing private POST module; ports without that transport include the same bodies inline. Keep read-only tables, persistence, public runtime services, renderer and final base-memory refresh helpers resident. Introduce a small explicit resident/private call boundary and a common module export/import owner. Preserve existing board transports and their memory exclusions. Measure net savings after bridges and alignment, not gross moved bytes. The current estimates are about 4.7 KB before overhead. No compression is required for this first placement boundary.

**F2 — measured packing and remaining duplication.** Use the selected packing and Setup extraction contract below. Shared storage and reporting belong under `shared/tools`; board adapters describe geometry and hardware access. Remove exact duplicated common BIOS bodies through in-place includes, proving complete image equality for that mechanical step. Do not merge merely similar hardware implementations. Do not replace controller algorithms or redesign whole-image shadowing.

**F3 — documentation and closure.** Update the shared implementation and porting guides with the actual module ABI, lifetime, build contract and lessons. Put board layouts and measurements in each port's developer documentation. Add one shared footprint report and regression checks. Run the affected complete validation declarations, boundary trace closure and native correctness review. The routine-update hold on a port remains intact; explicit task checks must include that port without changing its routine eligibility. Use one final coherent checkpoint for the completed implementation and documentation. No public release is requested by this task.

F1 has independent value but all retained outcomes belong to this task. Actual commands, results and correction evidence go in the ignored task result, not this plan. F2 cannot silently expand the supported hardware or remove a feature to create space.

## Boundary inventory


| ID | Source and invariant | Contrast and required oracle | Entry and proof |
| --- | --- | --- | --- |
| B1 | User request; build policy: usable net capacity and common ownership | Same features before/after; occupied ranges plus all loader, table and RAM overhead, not file length or an arbitrary FF run | Production builders; S1 |
| B2 | Port ROM geometry and fixed firmware entries | Every variant preserves size, checksum, independent retained regions, reset target and compatibility ABI | Build and verify; S2 |
| B3 | `setup_text`, UI macros and renderer | Encoded authored text versus literal foreign-segment/control text; exact bytes, cells and caller state | Real renderer; S3–S4 |
| B4 | AGENTS Setup ownership; settings schemas and NV6 | All choices, sorted display/storage mapping, Save/Discard/Defaults and migration unchanged | Actual Setup; S8, S10 |
| B5 | Startup and early/final Setup owners | Cold/warm, early/final entry reach their proper continuation without a new probe or wait | Real POST; S5–S8 |
| B6 | PnP product scope | Eligible ports retain PnP; excluded port remains ordinary non-PnP firmware | Build and actual Setup; S10 |
| B7 | Journal, transport and resident publication owners | Module live versus released; complete far return, prefix, BDA budget, current EBDA and selectors remain valid | Install through final boot; S5–S9, S11 |
| B8 | PnP allocation/provider/Clear contracts | Complete unassignable versus incomplete, every actual provider, no synthetic count caps | Census through publication; S11–S12 |
| B9 | Public PnP/APM, disk and boot contracts | Current runtime pointers and caller state survive private-module release and EBDA relocation | Public real/protected entries and boot; S9, S13–S14 |
| B10 | Opaque hardware adapters | Complete original operation order, table bytes and reset prerequisites unchanged | Cold/warm adapter entry; S15 |
| B11 | Candidate identity and build policy | Complete matching system/VGA or lane groups; exact recorded version, time and SUM32 | Finish candidate; S16 |
| B12 | Documentation ownership and user request | Shared capability and instructions versus board recipes; no public private-source artifacts | Documentation/source guards; S17 |

These rows dispose of the accepted source clauses: feature parity and footprint map to B1; layouts and fixed entries to B2; text and Setup rules to B3/B4; startup to B5; adoption to B6; lifetime and capacity to B7/B8; runtime ABI to B9; hardware invariants are opaque under B10; artifacts and documentation map to B11/B12. Future ACPI and unrelated controller tuning are deferred, not gaps. No undefined supported result is selected.

## Scenario Proof


Each runtime row composes through the listed owner to its terminal result. Cases vary the named discriminator rather than multiplying unrelated hardware choices. Opaque hardware is checked by preservation, not requalified by an emulator.

| ID | Discriminator and contrast | Production path and terminal oracle | Runnable check |
| --- | --- | --- | --- |
| S1 | Identical features, baseline versus candidate | Real assembly → named sections → net ROM and RAM report, with overhead charged | `python -B shared/tests/test-rom-footprint.py` plus all port builds |
| S2 | Every declared image variant | Assembly → composite/lane builder → integrity verification; retained independent input bytes and fixed entries exact | Each port's declared build/image checks; `python -B shared/tests/test-ui-text.py --port all --case image-contract` |
| S3 | Empty, new, equal-prefix and changed cached text | Authored `ui_string` → actual renderer; byte-exact text with no stale suffix or required dictionary retraining | `python -B shared/tests/test-ui-text.py --port all --case strings` and `--case compatibility` |
| S4 | Encoded resident text versus foreign literal/control bytes | Installed module's real moved drawing export → resident imports → exact VRAM cells; DS=F000 at encoded renderer entry and original return-state contract with nonzero sentinels/current EBDA | New `python -B shared/tests/test-rom-footprint.py --port all --case private-ui`; direct foreign/literal contrast: `python -B shared/tests/test-ui-text.py --port all --case renderer` |
| S5 | Cold versus warm private ROM execution | Actual reset/startup → unchanged module install → execution in installed private CS → final far return → publication/release → working boot loader; protected prefix retained | New `python -B shared/tests/test-rom-footprint.py --port m919 --case startup`; supporting `test-live-post.py --port m919 --case screen` and `--case summary` |
| S6 | Onboard versus external retained video | Actual reset/startup → unchanged bank-window transport/scratch exclusion → installed private CS → restored mapping → final resident return/publication → working loader | New `python -B shared/tests/test-rom-footprint.py --port pb430 --case startup`; declared chipset checks support hardware preservation |
| S7 | Cold versus warm top-alias transfer | Actual reset/startup → unchanged AH87 transport → installed private CS → final resident return/publication → working loader; IF/A20/NMI and memory charge preserved | New `python -B shared/tests/test-rom-footprint.py --port presario-800 --case startup`; declared chipset checks support transport contracts |
| S8 | Early/final Setup; Save/reset, Discard/resume, Defaults/Cancel | Real gate → installed moved Setup → Save through resident reset producer and following startup to working loader; Discard through real later-POST continuation to boot with live journal intact | New `python -B shared/tests/test-rom-footprint.py --port all --case setup-continuation`; storage/default/cancel support: `python -B shared/tests/test-pnp-settings.py --port all` and `test-ui-text.py --port all --case setup` |
| S9 | Live module versus released/relocated runtime state | Last private far return → complete promotion → release → real public service → two warm rebuilds; aliases and original memory budget correct | `python -B shared/tests/test-pnp.py --port all --case composed-resources` and `--case boot-continuation` |
| S10 | PnP adoption versus inline non-PnP | Ordinary build → actual Setup Save and boot; no PnP module or interface on excluded port | `python -B shared/tests/test-pnp.py --port mp386 --case mp-negative` and shared Setup checks |
| S11 | Natural sufficient/insufficient staging and complete/incomplete resources | Actual census/allocator → verified publication → pending Clear retirement only for complete result | Shared `test-pnp.py` composed-resources case and selected existing capacity cases |
| S12 | Empty, one, equal-product distinct providers and later provider success | Discovery → actual resources → provider attempts/disconnect → boot terminal; all owed records represented | Shared `test-pnp.py` option-roms and boot-continuation cases |
| S13 | Real, PM16 and PM32 public caller selectors | Public entry after release/EBDA relocation → output and full caller state; no private runtime dependency | Shared `test-pnp.py` abi, information-services and set-node cases |
| S14 | Native/floppy/CD/APM boot continuations directly affected by placement | Current runtime service and buffer owners → intended loader return/boot without stale module references | Applicable declared port runtime tests and shared boot-continuation case |
| S15 | Directly affected adapter interfaces versus opaque hardware bodies | Complete operation/byte comparison and preserved cold/warm prerequisite; no electrical claim | Focused preservation assertions; cache transition checks only if their owner changes |
| S16 | Valid complete artifact group versus missing/mismatched member | Recorded assembly → `tools/finish-candidate.py` → matching latest and timestamped exact-byte SUM32 group | Candidate tooling regression checks and finish each port group |
| S17 | Shared instructions versus board-specific evidence | Final diff → authoritative owner → source/privacy/layout guards; claims match implementation | `python -B tools/check-public-source.py` and applicable documentation/rule-owner checks |

Test commands are completed with the existing runner's supported selectors; new focused checks must exercise actual module installation, private callers and terminal continuation rather than replacing those hops. Fault-injected hardware instability, future ACPI semantics and arbitrary unsupported media are outside this task. Collection cases apply to text/provider/artifact sets; they do not apply to fixed instruction-preservation comparisons.

## Decision Log


- Preserve existing transport and extract code first. Available private storage accommodates a useful first move, avoiding a new loader before it is needed.
- Keep renderer, strings, tables, saved settings and public services resident. Cooperating near jumps stay in one segment; foreign strings remain literal. The final released-module memory refresh still uses resident drawing helpers.
- Do not force whole-ROM shadowing. That would change hardware initialization and user choices for a placement problem.
- Prior-art research found no applicable tiny firmware decoder in the fetched arXiv encoder papers (1202.5233, 1409.5641, 1706.03035 and 1504.06712). Their compression-factorization results do not establish a runtime footprint or ratio here. Use primary format/source specifications and actual payload measurements for F2. ZX0, LZSA and the LZ4 block format are candidate mechanisms, not selected dependencies.
- Keep public source free of vendor ROMs and disassemblies. Preserve current independent images only in ignored comparison directories until their last consumer finishes.
- The independent challenge identified three proof gaps, all accepted: direct renderer tests do not prove private callers; first-header/allocation fixtures do not prove reset-to-boot; stopping at the reset label does not prove Save continuation. F1 adds named composed checks using the existing startup/boot machinery for those boundaries.

## Selected F2 packing and extraction


Move the remaining cooperating Setup change/choices, help/edit, IDE, peripheral and PnP UI bodies into the existing private composition. Include the shared chipset-menu control flow where it borrows `setup_choices.draw` or `.enum`. Keep that entire near-jump cohort together. Reuse the single `post-ui-api.inc` declaration owner, existing cross-segment frames and explicit resident data segment. Strings, tables, renderer, persistence, hardware policy, public services and the post-release memory refresh remain resident. The no-module composition includes the same bodies inline.

Use forward ZX0 version 2 streams from the official version 2.2 compressor. Baseline payload measurements justify this selection; the decoded bytes must remain identical to assembler output. Reject classic, backward and prefix-dependent streams. Pin the compressor source to `einar-saukas/ZX0` commit `ecde3a2ae05061fe06469ed46df81a33b7de7d86`. Its official Windows encoder SHA-256 is `e6aec5cdfc3535b808610cb54412ce375b5b13e17b59f2bc878a54a00a8acbac`. The optional independent host decoder is `b232d119fea7be2f671b9d62953bea3e08a5db731eb6cff910ae6c81b78bdb83`. Keep generic tools under the existing dependency owner, document installation and fail explicitly if a required tool is absent. Do not download during a normal firmware build.

Adapt the licensed 8088 decoder from `emmanuel-marty/unzx0_x86` commit `b2beaa04daf11ed67d68b911393ba6c04260e113`, source SHA-256 `e480de4a90d22e6329cbc519afe26abaefc7398cc4e895e898eedba092dc1d76`. Retain its zlib notice and identify the bounded adaptation. The main source's FE seed already implements v2 inverted offset bits through negative arithmetic. There is no need for a second format or dictionary. Keep the existing source and binary license obligations with their owners.

The smallest packed layout changes only the existing top-alias transport's storage consumer. It already emits a fixed 64 KiB resident section followed by `post_payload start=0x10000 vstart=0`. Emit the raw module without padding as an explicitly nonflash assembler intermediate. The shared packer requires the complete intermediate to equal exactly 65536 plus the raw header's declared length, validates its entry and complete extent, and constructs the existing 16 KiB bank. This is one assembly: the stored length never positions resident labels or private import addresses. There is no second-pass binding cycle, runtime relocation or blind truncation. Keep the intermediate out of normal flash-image filenames. Final builders retain their existing system/composite/variant contracts and record only checked final bytes.

A valid even raw extent up to 3FFEh bytes uses the existing raw header. An extent of 4000h bytes must use the packed representation because the final bank byte belongs to its independent checksum. The packed header identifies the format and carries the decoded length, stored length and decoded checksum. Its stream plus header must end before the bank checksum byte. Check the complete serialized bank after its final checksum, decode it again and compare every raw byte. If it cannot fit, reject the build without dropping features. Other existing transports retain raw storage while it fits their declared windows; do not force a RAM copy or decoder into a direct-ROM adapter.

The packed loader keeps the existing whole-bank AH87 high-alias transfer and its IF/A20/NMI contract. Charge that 16 KiB source allocation to the existing journal. For a packed bank, allocate a separate paragraph-rounded decoded extent before reconstruction. Source and destination are disjoint. Charge both reservations until the existing final release; do not charge only stored bytes. Keep the module pointer zero until complete bounded decoding, decoded-header/entry checks and checksum verification succeed. Use the existing failed-install release path. Do not create a new hardware-recovery policy.

The shared near decoder takes DS:SI and a packed byte count, ES:DI with DI zero, and the expected decoded length below 64 KiB. It clears DF and returns CF status. Preserve BP, DS and ES; the loader already owns its general-register and flags frame. Bound every bit refill, literal copy, offset fetch, Elias shift and match copy. Reject length overflow and lookback before produced output. EOF requires exact input consumption and output length; remaining bits in the final control byte are padding, extra bytes are not. A single failure epilogue must unwind nested near frames without stranding DS. The outer loader checks the decoded checksum before publishing. These internal parser checks do not add an advertised hostile-firmware recovery service.

Use one normal-build footprint report for all ports. Bind it to final artifact identity and distinguish resident free intervals, private raw/stored extents, header/decoder/alignment costs and charged temporary RAM. Device-record storage remains variable. Do not present gross relocation as a reduction in total stored bytes or private-bank savings as resident headroom.

### F2 boundary inventory and Scenario Proof


P-B1 through P-B10 refine B1–B10 for the new representation. Physical artifacts still use B11 and documentation B12. Their source clauses have these dispositions: raw byte/entry identity maps to P-B1; geometry, retained regions, fixed entries and complete groups to P-B2; board transport prerequisites and exit state to P-B3; decoded allocation, returning consumers and release to P-B4; complete call/data ABI to P-B5; text classification to P-B6; Setup drafts, modal control flow and saving to P-B7; runtime residency to P-B8; no-PnP composition to P-B9; actual net accounting to P-B10. Hardware algorithms, device allocation and boot algorithms remain opaque. ACPI remains deferred. General repository ownership rules are non-boundary instructions. No supported contract gap is unresolved.

Direct sources add `shared/src/setup/chipset-menu.inc` to the F1 packet: its <=10 popup borrows a PUSHAD frame and jumps into `setup_choices.draw`; its >10 path owns a separate paged key loop. The packing decisions above supply the missing internal format details without altering the user contract.

| IDs | Discriminator and contrast | Complete production path and oracle | Runnable check |
| --- | --- | --- | --- |
| P-S1 / P-B1 | Full byte identity; equal prefix with changed late/terminal byte; raw 3FFEh versus packed 4000h | Assembler/source bytes → production encoder → final serialized bank including checksum → native bounded decoder/actual loader → every raw byte and dispatch identity match | Extend `test-rom-footprint.py --port all --case roundtrip`; include literal/repeat/offset/refill and bounded-parser vectors |
| P-S2 / P-B2 | Every owned/retained boundary and artifact member | Normal builds → final checksums/composition → independent retained inputs, reset/F065 and matching system/VGA/lane groups → recorded final bytes | Shared PnP/UI image-contract and footprint artifact checks; declared builds and candidate-tool tests |
| P-S3 / P-B1,P-B3 | Direct-ROM source and protected neighboring owner | Actual cold/warm startup → unchanged E-bank preservation → install → actual private fetch/return → publication/release → loader; prefix remains exact | `test-rom-footprint.py --port m919 --case startup` |
| P-S4 / P-B1,P-B3 | ROM versus distinct shadow, internal/external video | Actual startup → existing window transport → full installed code → mapping restore → video scratch use → private return/release → loader | `test-rom-footprint.py --port pb430 --case startup` with both supported video branches |
| P-S5 / P-B1,P-B3 | Raw 3FFEh versus packed 4000h, actual decoded module beyond old bank extent | Actual top-alias/AH87 transfer → final-bank validation → full decoded allocation/output → verified dispatch → return/publication/release → loader; IF/A20/NMI contract retained | Presario startup case and roundtrip/actual-loader threshold cases |
| P-S6 / P-B4 | Largest natural fitting population versus first additional allocation | Same real module/budget → normal producers/allocator → complete versus incomplete publication/release; no failed-allocation mutation, scratch collision or lost pending Clear | Add `--case capacity`; existing placement/composed resource checks support it |
| P-S7 / P-B4,P-B7 | Discard with/without a returning ROM's extra memory reservation | Real early gate → Discard → RAM/peripheral work → returning ROM lowers budget → later allocation → final private return → resident promotion/release → boot; no persistent writes or lost reservation | Add `--case lifetime`, reusing actual startup/runtime owners |
| P-S8 / P-B4,P-B7 | Confirmed Save versus canceled confirmation/Discard; two warm rebuilds | Actual gate/editor → verified Save → resident reset producer → external reset pulse → actual startup/reconstruction → saved setting and original-budget accounting → working loader | Existing `--case setup-continuation` extended for packed storage |
| P-S9 / P-B5 | Every applicable entry, nonzero caller state, returned BX/CF and nested crossing | Actual facade → installed private entry → actual resident callback/nested private call → entry-specific outputs, segments, balanced stack and original terminal | Extend `--case private-ui` and emitted API inventory; both CF outcomes where meaningful |
| P-S10 / P-B6 | Same marker byte, resident encoded versus foreign literal/control/CP437 input | Actual moved caller → real renderer/dictionary/literal gate → independent expected cells, neighboring cells and ABI preserved | Private UI plus shared UI renderer case |
| P-S11 / P-B7 | <=10 short versus >10 paged chipset choices; modal Cancel/Apply, Help/redraw; fixed absent/disabled positions | Actual Setup Select → respective borrowed-frame or paged loop → Help/redraw → Cancel/Apply → proper Setup terminal, exact draft delta and no probe/persistent mutation | Add named popup contrasts to private-ui/Setup checks; shared PnP settings and UI suites cover moved menu families |
| P-S12 / P-B8 | Public services after actual release and later EBDA relocation | Private final return → real promotion/release/reuse → real/PM16/PM32 public entry and native/floppy/CD/provider/APM continuation → existing outputs with no released-code fetch | Shared PnP `--case all --port all` plus directly affected runtime checks once after final changes |
| P-S13 / P-B9 | Eligible versus inline composition | Normal no-PnP build → ordinary Setup Save/load/Discard → compatibility/lane contracts; no module/protocol/control leakage | MP negative and UI checks; reuse whole-image equality when instructions stay identical |
| P-S14 / P-B10 | Gross movement versus final usable capacity, every affected normal builder | Normal build → packing/checksums → final identity → shared report; separate resident/private/RAM numbers including all overhead | Footprint measurement case and final normal builds |

The same second challenger independently derived this inventory, then challenged the complete design. Both findings are accepted: threshold proof must use the final serialized bank and actual loader, and both chipset popup paths must traverse their real borrowed-frame/paged control flow. They are explicit above. No alternate hardware policy or new public service is inferred.

### F2 decision record


ZX0 wins the measured small-decoder comparison. LZ4 stored one measured payload in 10996 bytes versus ZX0's 9000; DEFLATE stored it in 9115 but requires a more complex decoder. XZ's smaller payload does not justify its runtime machinery. These are payload measurements, not final net-savings claims. The final report charges the assembled decoder and loader. Pinned primary sources: [ZX0](https://github.com/einar-saukas/ZX0/tree/ecde3a2ae05061fe06469ed46df81a33b7de7d86) and [x86 decoder](https://github.com/emmanuel-marty/unzx0_x86/tree/b2beaa04daf11ed67d68b911393ba6c04260e113).

The target versions for this coherent optimization are 0.22.0, 0.8.0 and 0.8.0 for the affected eligible images. The inline image retains its 0.7.1 identity if its complete bytes remain unchanged. Rebuilds and exact source-only extraction do not consume another version. Final documentation must explain the installed mechanism and measured restrictions, with board-specific layouts and results kept in their port owners.
