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

Persistent manual reservations, BIOS/OS configuration control and one-shot Clear ESCD are required by the user. Standard ESCD services require a real, capacity-qualified backing adapter; use the published ESCD 1.02A specification. Docking/event notification, DDIM, ACPI, network-boot policy and CPU tuning are outside this task. No PS/2 mouse initialization is added to boards that prohibit it. Existing cache activation and retained firmware inputs remain unchanged.

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
| B27 | RTC/NVRAM adapter and storage ownership contracts. Physical write address and owner. | Trace admitted writes, retain protected adjacent data, AT geometry/clock/century and timing storage, and maintain the AT checksum. Exercise actual cold/warm strap and advanced-timing owners. | Qualify every additional ESCD backend write path. |
| B28 | BIOS functions09h/0Ah, if provided. Complete replacement versus accumulation. | Outside P0. | Replace A/B by B/C, return complete rounded-up coverage and prove subsequent allocation releases A. Explicit manual reservations keep their authority. |
| B29 | ESCD functions41h/42h/43h. Real capacity, complete external format and persistence. | Outside P0. | Contrast representable, invalid and genuinely over-capacity full blocks, including a distinct final record. Independently decode results, restart, consume them and preserve previous valid data after rejection. |

The exact P0 check is `python -B shared/tests/test-pnp-settings.py --port all`. Each startup/recovery continuation uses the existing board hardware seam and the real firmware owner. A settings-loader round trip alone cannot attest a reset or stackless recovery path.

## Implementation checkpoints


0. **P0: Reservation persistence and Setup policy.** Preserve all legacy logical settings in a compact, versioned record; use proven existing CMOS/NVRAM access only. Add manual IRQ/DMA exclusions, two I/O reservation windows, upper-memory reservation blocks and BIOS/OS/one-shot-clear controls through the shared draft/save/discard owner. Do not advertise PnP before the remaining protocol and boot integration is complete.
1. **P1: Public BIOS interface and onboard descriptions.** Add the shared service/structure and independent real/protected callers. Connect actual board-resource descriptions. Validate mandatory service semantics and caller preservation without advertising incomplete production support.
2. **P2: ISA protocol and allocation.** Add isolation, resource parsing, atomic selection/commit and shared reservations. Compose actual onboard policy and PCI routing, with complete device census tests.
3. **P3: Boot integration and 64 KiB delivery.** Complete PnP ROM connection/failure handling, fit the complete feature in the established layouts, build all ports, update user/developer guides and run final validation/trace closure/native review. Lossless compaction or deduplication may support the size goal; existing features must not disappear to make room.

Each checkpoint has a native review and coherent local commit after its focused proof. Final review covers the complete candidate. Current release images remain available until replacements pass integrity checks.

## Open decision


C1 is resolved: the user requires persistent manual reservations and typical BIOS/OS and Clear ESCD controls. Clear ESCD invalidates learned allocations, preserves explicit reservations and unrelated saved settings, and retires its pending request only after successful rebuild. Manual reservations remain authoritative in both configuration policies.

The exact ESCD backing/capacity for each port remains under technical research. Do not advertise writable flash based on ROM size alone, or call a private reservation record standard ESCD. The standard permits compressed private backing, but public reads and writes must preserve the complete external format. Reconstructing onboard data does not retain independent expansion-card choices. This does not block the independently useful reservation persistence checkpoint.

## Decision log


- Shared PnP is ahead of remaining CPU performance, by the current user instruction.
- Use the original published specifications and existing owners. Optional persistence and dynamic events are not inferred from a valid PnP signature.
- Keep 64 KiB system images and retained physical layouts; make size accounting a normal build check.

## P0 storage and proof card


Existing owner: shared settings and per-port chipset readers/writers, including early timing and recovery selection. Use a single versioned codec for the new complete record. Old formats remain readable without writes; only complete verified Save migrates. Keep the existing base record, RTC clock/century, AT disk geometry, RAM-test marker and MP386 OEM NVRAM records unchanged.

Candidate storage budget: existing extended configuration bytes 33h-35h and 40h-7Fh plus the source-audited, presently unowned ordinary AT bytes 11h, 13h and 2Dh. This is 70 addressable bytes through existing adapters, not assumed extra RTC capacity. A three-byte format/checksum header at 33h-35h and independent recovery byte at69h leave 66 payload bytes. Payload uses40h-7Fh excluding69h, plus11h/13h/2Dh. Retaining69h preserves the stackless Presario recovery producer; new-format selectors on other ports must route recovery there too. Audit each write path before claiming those three AT bytes.

Lossless payload fields retain full IDE geometry bytes, valid type/translation/block/enable encodings, every mask-owned chipset bit and all eight peripheral selectors. New reservation payload: IRQ mask (16 bits), DMA mask (8), two I/O base/length pairs (64), C0000h-EFFFFh memory blocks in 16 KiB units (12), BIOS/OS policy and pending-clear bits. Pending Clear ESCD is preserved during P0 POST; only the later real ESCD rebuild owner may consume it. Existing and new logical values must fit the proven per-port budget before changing runtime readers. Unused or out-of-range bits are rejected. Recovery is outside the payload checksum and cannot corrupt unrelated settings when it selects safe timing.

P0 boundaries extend B22-B27: Save/Discard/Defaults ownership; old-format nondefault migration; complete reservations including empty, overlapping and later distinct windows; round-up of memory reservations; physical write ownership; cold reload; pending-request preservation through two cold/warm resets, Discard and unrelated saves. Retirement is a P2/P3 obligation after the actual rebuild. Planned check: `python -B shared/tests/test-pnp-settings.py --port all`, exercising old formats through actual Save/reload and port NVRAM adapters. ROM compaction remains P3; measure P0 image growth with the normal builds.

The P0 implementation does not claim a standard ESCD store. ESCD 1.02A original PostScript and extracted text are retained locally; capacity and storage adapters will be fixed before those APIs are exposed.

CMOS37h remains owned by existing Presario strap capture and PB430 timing recovery. It is excluded from the new store; cold/warm startup and advanced timing must prove it remains unchanged by reservation persistence.

P0 must migrate nondefault values, execute each actual recovery publication path, then restart through early timing. The checksummed payload must remain byte-identical, Compatibility selection must work, prior D2 must survive a failed complete Save, and only a verified whole Save may release it through the established board completion hook. No new RAM/stack dependence is allowed in stackless producers.

The single verified NV6 publication supersedes the independent-component partial-commit expectation in `presario-800/tools/test-chipset.py` at base `6b399086798b`. Scope: only the ordinary failed-F10 assertion that attempted chipset settings reload after base verification fails. The error/menu keeps the active hardware and draft unchanged and does not reset. The unpublished record selects Compatibility on a later restart without fabricating a RAM comparison-failure marker or notice. Independent legacy readers and actual RAM-failure recovery keep their existing contracts.

Firmware target versions for this feature are M9190.19.0, MP3860.6.0, PB4300.5.0 and Presario8000.5.0. No release or publication is authorized by the implementation request alone.
