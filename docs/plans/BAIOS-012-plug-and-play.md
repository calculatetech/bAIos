# Shared Plug and Play


Provide ISA Plug and Play enumeration and resource assignment, a standards-based BIOS interface for operating systems, and compatible option-ROM boot handling. Keep common services in shared code and physical controller operations in board adapters. Preserve the existing 64 KiB system-ROM layouts. This work takes priority over BAIOS-005 CPU tuning.

Base: `6b399086798b1245daf210cd875733c74c7003b8`, branch `task/shared-plug-and-play`, one writable checkout. Existing plans BAIOS-003, BAIOS-004 and BAIOS-010 retain their cache, APM and disk contracts. This plan does not reopen those implementations.

## Sources and owners


Implement the May 5, 1994 ISA Plug and Play 1.0a and Plug and Play BIOS 1.0A specifications. Original reference copies remain outside Git. Public references:

- [ISA specification](https://ethw-images.s3.us-east-va.perf.cloud.ovh.us/ieee/7/7f/PNP-ISA-v1.0a.pdf).
- [BIOS specification](https://ethw-images.s3.us-east-va.perf.cloud.ovh.us/ethw/8/8a/PnP-BIOS-Specification-V1.0A.pdf).
- [ESCD 1.02A specification](https://stuff.mit.edu/afs/sipb/contrib/doc/PnP/escd.ps).

Shared POST and runtime composition: `shared/src/firmware/bios.asm` and the retained Presario composition in `presario-800/src/bios.asm`. Existing saved settings and peripheral routing: `setup.inc`, `settings-packed.inc`, `peripherals.inc` and board adapters. Existing expansion-ROM and boot continuation: `boot.inc`. Existing PCI BAR allocation: `shared/src/pc/pci.inc`; physical IRQ routing remains board-owned. Reuse these owners rather than introduce a competing allocator or saved-settings writer.

The approach is fixed by these legacy specifications; this task does not select a new protocol or novel systems mechanism. Current references, not model recollection, define wire formats and API behavior.

## Behavior floor and ceiling


Provide real-mode and 16-bit protected-mode far-call interfaces, including 16-bit arguments on supported 16/32-bit stacks. Preserve caller state except the documented AX result and output buffers. Mandatory services are 00h/01h/02h for onboard nodes, 40h for ISA configuration and 0Bh for existing APM 1.2. Advertise truthful fixed/mutable node capabilities; do not invent device-level APM controls. Return documented errors for unsupported services.

Re-enumerate ISA cards on cold and warm POST, validate identifiers and descriptor streams, preserve CSN/LDN identity, configure complete feasible resource sets and activate last. Include I/O decode aliases, IRQ2/PIC9 ownership, DMA capabilities, dependent alternatives and standard memory descriptors. Reserve actual motherboard, PCI and independently supplied legacy resources. Unassignable devices remain inactive with an explicit result. Do not overwrite saved Setup policy merely to configure an expansion card.

Validate PnP expansion headers and chained metadata before using them. Preserve legacy providers, handle deferred Boot Connection Vectors and disconnect/failure continuation, and pass the proper installation pointer and drive identity at boot.

Persistent manual reservations, BIOS/OS configuration control and one-shot Clear ESCD are required by the user. Baseline PnP must work with OTP ROMs: save manual policy in the existing CMOS store and rebuild automatic assignments on cold and warm POST. Optional static-allocation and ESCD services09h/0Ah/41h/42h/43h return FUNCTION_NOT_SUPPORTED (82h); this task does not add a flash writer. Clear ESCD requests a complete rebuild and preserves explicit reservations. Docking/event notification, DDIM, ACPI, network-boot policy and CPU tuning are outside this task. No PS/2 mouse initialization is added to boards that prohibit it. Existing cache activation and retained firmware inputs remain unchanged.

## Boundary inventory


| ID | Required boundary | Minimal contrast and terminal oracle | Exact planned check |
| --- | --- | --- | --- |
| B1 | Complete image/layout fit | Four production compositions versus fixed entries; exact sizes, checksums, retained bytes and reset targets | `shared/tests/test-pnp.py --case image-contract --port all` |
| B2 | Public calling convention | Real segments versus nonidentity protected selectors and both stack sizes; full caller preservation | `--case abi` |
| B3 | Installation discovery | Independent aligned ROM scan versus mere signature; checksum and successful calls through returned addresses | `--case abi` |
| B4 | Mandatory and unsupported services | 00/01/02/40/0B versus reserved/optional/unknown; exact status and outputs | `--case information-services` |
| B5 | Cold/warm POST ownership | Fresh versus retained card state; sequential CSNs and boot-resource precedence | `--case isolation`, `--case composed-resources` |
| B6 | Isolation protocol | First read-port conflict versus end after valid isolation; timed serial reads and valid checksums | `--case isolation` |
| B7 | Resource stream reopening | Initial isolation versus Wake of assigned CSN; correct nine-byte prefix and readiness polling | `--case resource-reopen` |
| B8 | Complete logical-device census | Duplicate identifiers then different later requirement and null filler; exact CSN/LDN and register ordinals | `--case logical-devices` |
| B9 | IRQ/DMA semantics | Numerically free but incompatible candidate versus legal type/width; actual channel programming | `--case resource-semantics` |
| B10 | Dependent alternatives | Preferred tuple fails late, later tuple succeeds, another device needs rolled-back resources | `--case dependent-alternatives` |
| B11 | I/O placement | Same numeric range under 16-bit versus 10-bit decode; aligned complete nonaliasing ranges | `--case resource-semantics` |
| B12 | Memory and stream translation | 24/32-bit families, length/limit forms, zero checksum versus bad nonzero checksum; exact writes or inactive rejection | `--case memory-and-streams` |
| B13 | Transactional activation | Complete assignment versus failure after tentative ownership; deactivate/write/activate/Wait-for-Key chronology | `--case dependent-alternatives`, `--case memory-and-streams` |
| B14 | Onboard node inventory | Enabled/disabled embedded controller versus attached/expansion device; complete handle traversal and actual resources | `--case nodes` |
| B15 | Configuration ownership | Current versus next-boot and fixed versus mutable node; Get/Set/reset through existing owners | `--case set-node` |
| B16 | Actual ISA information | No cards versus multiple cards after read-port relocation; exact count/port | `--case information-services` |
| B17 | APM mapping | Actual empty/nonempty ownership and short/full buffers; required size without partial copy | `--case information-services` |
| B18 | ROM initialization | Valid chained PnP metadata versus legacy/malformed chain; complete provider census and arguments | `--case option-roms` |
| B19 | Boot connection and reopening | BCV-only provider succeeds/fails/INT18/INT19; disconnect and next-provider handoff | `--case boot-continuation` |
| B20 | Independent legacy resource vectors | Reported static conflict versus absent report; supplied ranges reserved without claiming unknown discovery | `--case option-roms` |
| B21 | Shared resource writers | ISA-owned candidate versus actual owner disabled after save/reset; final PCI routes/ELCR/ISA decode agree | `--case composed-resources` |

Each named case must follow its production input through its real owners to the terminal oracle. Synthetic cards and ROMs model the external specifications; they do not replace in-scope firmware calls or prove electrical stability. No full Cartesian product or repeated unchanged passing suites is required.

The user's manual-reservation amendment adds these boundaries. P0 closes only the persistence and Setup obligations below. Allocation, public APIs and actual ESCD rebuild remain under the same identifiers for later checkpoints.

| ID | Source and discriminator | P0 production path and terminal oracle | Later obligation |
| --- | --- | --- | --- |
| B22 | User amendment and BIOS specification legacy-resource clauses. Complete reservation membership, including empty, overlapping and later distinct entries. | Real Setup edits and complete Save, component patches, cold/warm startup and reload preserve every admitted IRQ/DMA/I/O/memory value. Commit an individual release and retain other reservations. | ISA/PCI exclusion and reuse after release. |
| B23 | User amendment and BIOS/OS allocation clauses. Saved BIOS versus OS policy. | One Setup owner, Save/reload, Discard and Defaults preserve the selected policy and unrelated values. | Both policies isolate and configure required boot devices. Optional activation follows policy. |
| B24 | User amendment. Pending clear versus successful rebuild. | Save a request, execute cold and warm startup, Discard edits and save an unrelated setting. Request and manual reservations remain intact. | Real learned-state invalidation, successful rebuild, retirement and no repeated clear on following boot. |
| B25 | User amendment and existing Setup draft/commit contract. Terminal Setup action. | Contrast real Save with Discard and Defaults followed by Discard. Check persisted bytes, subsequent values, one menu owner and restart only after successful Save. | None for P0 controls. |
| B26 | Existing settings-format, complete-commit and recovery owners. Recognized legacy versus NV6 format. | Nondefault legacy Load remains read-only. Complete verified Save preserves full IDE geometry, peripheral and chipset choices. Actual recovery publication then early restart selects safe timings without changing payload. Failed whole Save retains prior D2. | None for P0 owners. |
| B27 | RTC/NVRAM adapter and storage ownership contracts. Physical write address and owner. | Trace admitted writes, retain protected adjacent data, AT geometry/clock/century and timing storage, and maintain the AT checksum. Exercise actual cold/warm strap and advanced-timing owners. | Reuse these verified owners for request retirement; no new storage adapter. |
| B28 | Optional BIOS functions09h/0Ah. | Outside P0. | Outside the OTP baseline: return82h without mutation. Do not describe Setup reservations as a standard09h store or guarantee arbitrary OS-driver allocation. |
| B29 | Optional ESCD functions41h/42h/43h. | Outside P0. | Outside the OTP baseline: return82h without mutation. Do not advertise a private settings record as standard ESCD backing. |

The exact P0 check is `python -B shared/tests/test-pnp-settings.py --port all`. Each startup/recovery continuation uses the existing board hardware seam and the real firmware owner. A settings-loader round trip alone cannot attest a reset or stackless recovery path.

## Implementation checkpoints


0. **P0: Reservation persistence and Setup policy.** Preserve all legacy logical settings in a compact, versioned record; use proven existing CMOS/NVRAM access only. Add manual IRQ/DMA exclusions, two I/O reservation windows, upper-memory reservation blocks and BIOS/OS/one-shot-clear controls through the shared draft/save/discard owner. Do not advertise PnP before the remaining protocol and boot integration is complete.
0a. **P0S: Recover space for the remaining services.** Compact eligible Setup strings without changing text, layout, table identity or saved settings. Keep the normal build owners and fixed ROM entries. Prove rendered compatibility and measure net space after the dictionary and decoder. Review and checkpoint this foundation before P1.
1. **P1: Public BIOS interface and onboard descriptions.** Add the shared service/structure and independent real/protected callers. Connect actual board-resource descriptions. Validate mandatory service semantics and caller preservation without advertising incomplete production support.
2. **P2: ISA protocol and allocation.** Add isolation, resource parsing, atomic selection/commit and shared reservations. Compose actual onboard policy and PCI routing, with complete device census tests.
3. **P3: Boot integration and 64 KiB delivery.** Complete PnP ROM connection/failure handling, fit the complete feature in the established layouts, build all ports, update user/developer guides and run final validation/trace closure/native review. Lossless compaction or deduplication may support the size goal; existing features must not disappear to make room.

Each checkpoint has a native review and coherent local commit after its focused proof. Final review covers the complete candidate. Current release images remain available until replacements pass integrity checks.

## Configuration policy


C1 is resolved: the user requires persistent manual reservations and typical BIOS/OS and Clear ESCD controls. Clear ESCD invalidates learned allocations, preserves explicit reservations and unrelated saved settings, and retires its pending request only after successful rebuild. Manual reservations remain authoritative in both configuration policies.

The user explicitly requires OTP-compatible operation and rejects chip qualification as a prerequisite. Source: the current user amendment, superseding only the unfinished P2/P3 flash-backing requirement in this plan. P0 storage and P0S/P1 contracts remain. BIOS specification4.4.1 makes ESCD services optional; an official AMI comparison has a valid PnP interface with no usable ESCD storage. Dynamic POST reconstruction is the selected baseline. It does not retain per-card choices made by an OS. The firmware honors explicit reservations under both POST policies; it does not control arbitrary drivers after handoff.

## Decision log


- Shared PnP is ahead of remaining CPU performance, by the current user instruction.
- Use the original published specifications and existing owners. Optional persistence and dynamic events are not inferred from a valid PnP signature.
- Keep 64 KiB system images and retained physical layouts; make size accounting a normal build check.
- Use CMOS policy and dynamic POST reconstruction on OTP and rewritable ROMs alike. Optional ESCD backing and general flash programming are outside this implementation, by the user's amendment.

## P0 storage and proof card


Existing owner: shared settings and per-port chipset readers/writers, including early timing and recovery selection. Use a single versioned codec for the new complete record. Old formats remain readable without writes; only complete verified Save migrates. Keep the existing base record, RTC clock/century, AT disk geometry, RAM-test marker and MP386 OEM NVRAM records unchanged.

Candidate storage budget: existing extended configuration bytes 33h-35h and 40h-7Fh plus the source-audited, presently unowned ordinary AT bytes 11h, 13h and 2Dh. This is 70 addressable bytes through existing adapters, not assumed extra RTC capacity. A three-byte format/checksum header at 33h-35h and independent recovery byte at69h leave 66 payload bytes. Payload uses40h-7Fh excluding69h, plus11h/13h/2Dh. Retaining69h preserves the stackless Presario recovery producer; new-format selectors on other ports must route recovery there too. Audit each write path before claiming those three AT bytes.

Lossless payload fields retain full IDE geometry bytes, valid type/translation/block/enable encodings, every mask-owned chipset bit and all eight peripheral selectors. New reservation payload: IRQ mask (16 bits), DMA mask (8), two I/O base/length pairs (64), C0000h-EFFFFh memory blocks in 16 KiB units (12), BIOS/OS policy and pending-clear bits. Pending Clear ESCD is preserved during P0 POST; only the later real ESCD rebuild owner may consume it. Existing and new logical values must fit the proven per-port budget before changing runtime readers. Unused or out-of-range bits are rejected. Recovery is outside the payload checksum and cannot corrupt unrelated settings when it selects safe timing.

P0 boundaries extend B22-B27: Save/Discard/Defaults ownership; old-format nondefault migration; complete reservations including empty, overlapping and later distinct windows; round-up of memory reservations; physical write ownership; cold reload; pending-request preservation through two cold/warm resets, Discard and unrelated saves. Retirement is a P2/P3 obligation after the actual rebuild. Planned check: `python -B shared/tests/test-pnp-settings.py --port all`, exercising old formats through actual Save/reload and port NVRAM adapters. P0S recovers text space before P1; P3 still proves that the complete feature fits.

The P0 implementation does not claim a standard ESCD store. Optional standard storage services remain unsupported in the selected OTP baseline.

CMOS37h remains owned by existing Presario strap capture and PB430 timing recovery. It is excluded from the new store; cold/warm startup and advanced timing must prove it remains unchanged by reservation persistence.

P0 must migrate nondefault values, execute each actual recovery publication path, then restart through early timing. The checksummed payload must remain byte-identical, Compatibility selection must work, prior D2 must survive a failed complete Save, and only a verified whole Save may release it through the established board completion hook. No new RAM/stack dependence is allowed in stackless producers.

The single verified NV6 publication supersedes the independent-component partial-commit expectation in `presario-800/tools/test-chipset.py` at base `6b399086798b`. Scope: only the ordinary failed-F10 assertion that attempted chipset settings reload after base verification fails. The error/menu keeps the active hardware and draft unchanged and does not reset. The unpublished record selects Compatibility on a later restart without fabricating a RAM comparison-failure marker or notice. Independent legacy readers and actual RAM-failure recovery keep their existing contracts.

Firmware target versions for this feature are M9190.19.0, MP3860.6.0, PB4300.5.0 and Presario8000.5.0. No release or publication is authorized by the implementation request alone.

## P0S space and compatibility card


Source: the accepted 64 KiB requirement and existing Setup text, layout, choice and renderer owners. Scope: unfinished P3 space recovery moves before P1 as P0S because the persistence foundation leaves insufficient room for the remaining services. P0 remains unchanged. P3 retains complete-feature fit and delivery.

Keep canonical strings in their current source files. Use an opt-in `ui_string` NASM macro with a fixed 128-entry pair dictionary. Each pair contains ASCII bytes or earlier dictionary tokens. Assert acyclicity and expansion depth at most 32. A small standard-library trainer can update the fixed dictionary, but ordinary builds must not run it. Encode at assembly time only when the marker, tokens and terminator occupy fewer bytes than the literal. Keep real source labels; an optional second macro argument names a generated compile-time cache key. A cache hit must match the exact full plaintext, and new or changed text automatically uses the same ordered encoder. Keep this derived metadata beside the dictionary, with no runtime catalogue, build step or dependency. No new persistent state or whole-ROM compression is allowed. Short, empty and unsuitable strings remain literal. Preserve all labels and table identities.

The existing `setup_text` owner streams expanded bytes through `setup_color`. Dictionary reads use CS. Input retains DS:SI, existing register/segment preservation, and existing output layout. Only DS=CS compiled ROM input can use the leading 01h marker. DS!=CS input always remains literal, including a leading 01h and CP437/control bytes. Check raw compiled string declarations for marker collisions. Keep strings shared with teletype warnings and POST length-scanned fragments literal. Audit their actual consumers before converting a declaration.

Freeze a test-only plaintext manifest from the P0 compiled images before changing representations. It is an independent oracle, not a second runtime catalogue. The new test assembles current sources through existing build owners in each port's `build/tests/ui-text/`. Reuse current Setup/hardware fixtures and actual renderer calls. Existing width and sorted-choice checks must compare rendered text, not encoded byte lengths. Do not duplicate the renderer as the expected-output oracle.

| ID | Source clause and discriminator | Production path and required contrast/oracle | Exact planned check |
| --- | --- | --- | --- |
| B30 | Existing complete text and collection identity. | Every selected compiled string through actual `setup_text` equals its frozen P0 bytes. Include empty, duplicate, repeated prefix with later different suffix, short literal fallback and newly authored strings compiled without retraining. Dictionary expansion is bounded and labels/table entries retain their identity. | `python -B shared/tests/test-ui-text.py --port all --case strings` |
| B31 | Existing renderer ABI, literal inputs and theme ownership. | Compiled encoded DS=CS versus literal RAM DS!=CS beginning 01h, plus high/control bytes, through the actual renderer. Exact characters, colors, neighbor canaries, preserved caller registers/segments/stack and relocated-EBDA theme state must agree. No newly promised FLAGS contract. | `python -B shared/tests/test-ui-text.py --port all --case renderer` |
| B32 | Real Setup composition and fixed saved meanings. | All four actual Setup owners execute mapped choice Apply/Cancel, help, theme change, Save and Discard. Verify visible choices, committed bytes/reload, and absent writes/reset on Discard. Preserve Presario calculated-range and CAS composition through their real owners. | `python -B shared/tests/test-ui-text.py --port all --case setup`; Presario `test-modular-setup.py --case numeric --case abi` and `test-chipset.py --case ui`, selecting the same current output directory. |
| B33 | Warning/POST raw consumers and terminal rendering. | Shared warning strings and POST concatenation fragments remain literal and retain their exact output through actual warning/POST owners. The existing POST-UI and summary checks run against the compacted images. | `python -B shared/tests/test-ui-text.py --port all --case compatibility` |
| B34 | Net space and all fixed physical images. | Normal four-port compositions retain system/physical sizes, checksums, reset targets, fixed entries and selected retained bytes. Measure actual savings after dictionary, decoder and marker costs. This does not establish that the later complete PnP feature fits. | `python -B shared/tests/test-ui-text.py --port all --case image-contract` |

`python -B shared/tests/test-ui-text.py --port all` executes this complete focused inventory. Freeze exact source/artifact hashes and per-scenario results before the P0S trace and checkpoint review. Existing unrelated cache and electrical qualification are outside this representation change.

## P1 interface and state card


The original BIOS specification sections 4.2 through 4.5, function40h, function0Bh and Appendix C map to B2/B3/B4/B14/B15/B16/B17. Their argument widths, descriptors, timing controls and error values are required boundaries. Existing cache/APM/disk implementations are opaque. ISA isolation, allocation and ROM boot connection remain later checkpoint obligations; optional storage APIs remain unsupported. P1 must not publish a valid installation structure in normal production images. A dedicated test composition exposes the genuine structure and callable entries for independent discovery.

Use one shared real/PM16 far-call dispatcher and node encoder in both firmware compositions. The installation structure is aligned, 21h bytes long, version10h, checksummed, with event control zero. Its fixed data address is real0040h/physical00000400h. PM code uses the supplied BiosSelector, never a raw EBDA segment. Decode 16-bit argument slots with the actual stack addressing width. Preserve full caller registers, segments, FLAGS and ESP. Do not change modes, caller GDT/IDT, or install a private selector.

Reserve BDA ADh..FFh, exactly 83 bytes: canonical active payload66, base record8, detected RAM end4, ISA count/read port3, and status/provenance2. Define and assert exact field boundaries. Publish after actual settings, routing and memory application without persistent writes. Current nodes describe applied resources. Next-boot nodes use verified saved policy, or the complete legacy snapshot until migration. Public mutation uses selector-safe primitives within the existing NV6/base publication owner. Keep the Setup verification trace facade separate from its selector-safe verification core. Preserve unrelated payload, drafts, manual exclusions, pending clear and recovery. A first legacy Set must perform a complete verified migration, not a partial component publication.

Board adapters describe actual embedded controllers and their accepted resources. MP386 switch routing remains fixed. Exclude filtered Presario UART B and attached or expansion devices. Equal UART IDs have distinct stable handles. Include the three terminated descriptor blocks and truthful configure/disable attributes. Generic VGA I/O ranges must not claim LPT3BCh. Software-routable UART/LPT/FDC nodes can expose existing alternatives as next-boot-only. No new hot-controller reconfiguration feature is added. A changed unsupported current configuration returns SET_FAILED without changing hardware. Control3 is not Function01's invalid-control case: an unchanged current request can succeed together with a verified static commit. Never return7Fh without actual dynamic success and static failure. Ignore extraneous node metadata and recognize complete zero-resource disable requests.

Function00 writes a BYTE count and WORD maximum size. Function01 takes a FAR BYTE handle pointer, supports current1 or next-boot2, rejects0/3/reserved bits, and returns the next handle orFFh. Function02 takes a by-value handle and complete ordered allocated resources. Return exact standard status values for unsupported, unknown, invalid-handle, bad-parameter, failed-Set and short-buffer cases. Function40 returns the truthful six-byte zero-card structure until P2 supplies its real producer. Existing APM has no individual managed devices, so function0Bh returns a successful empty mapping with required size zero. Do not invent a nonempty provider to claim coverage.

The following checks extend the existing B# inventory, with the same independent callers and production owners on all four ports:

- B2/B3: `python -B shared/tests/test-pnp.py --case abi --port all`. An independent aligned ROM scanner finds test entries, then calls them. Compare real16, PM nonidentity SS16 with nonzero upper ESP and SS32 with ESP aboveFFFFh, including a temporary frame crossing64KiB. Preserve full caller state and canaries, keep ROM read-only, move EBDA and poison the old location. Normal production scans must find no incomplete installation.
- B4/B16/B17: `--case information-services --port all`. Contrast all required, reserved, optional and unknown calls and invalid controls/handles. Check exact widths/status/canaries, zero-card revision/count/port/reserved, no ISA writes and empty APM behavior at zero/nonzero capacity. Positive enumeration and nonempty managed-device obligations remain deferred.
- B14: `--case nodes --port all`. Independently decode the entire onboard collection, count/max size, duplicate UART IDs and a later distinct node, enabled/disabled resources and exclusion of external probes/attached drives. Actual cold/warm publication must not write BDA ACh or physical0500h. Drive the real IRQ1 E1 prefix owner after publication, then Get the unchanged current nodes and complete normal keyboard decoding. Observe writes at both snapshot boundaries.
- B15: `--case set-node --port all`. Contrast current and saved next-boot values, fixed/static-only capabilities and controls1/2/3, metadata ignored versus relevant complete resources, and disable/re-enable. Preserve distinct unrelated saved policy and Setup drafts. Execute actual cold/warm reload and hardware application before Get, then actual Setup Save/Discard through the same owner. Rejected Set has no persistent mutation. Explicitly perform a genuinely changed first Set from a nondefault legacy record with nonidentity selectors and SS32 aboveFFFFh crossing64KiB. Poison the low16-bit stack alias and old EBDA, retain a distinct draft, and independently decode base/payload/checksums before reset/Get.
- B1: `--case image-contract --port all`. Use all four normal build owners and the fixed physical-image integrity oracles. P0S savings are not a substitute for this check.

## Optional storage boundary


The official ROM comparison establishes a normal no-storage configuration continuation. The selected implementation rebuilds assignments in RAM, saves manual policy in CMOS and returns82h for optional storage services. It does not identify flash chips, change programming voltage or add an updater. The hardware flash-voltage jumper remains a board concern.
