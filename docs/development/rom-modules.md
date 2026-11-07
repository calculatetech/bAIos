# Shared ROM modules

<!-- cpk-rule-owner: rom-module-composition -->
<!-- cpk-rule-guard: Publish runtime state only after the final private far return. -->
<!-- cpk-rule-guard: Do not use normal flash-image names for nonflash assembler intermediates. -->

A private POST module contains code used only during startup and Setup. Resident code remains available after startup. Ports select an existing transport and its physical storage window. The shared composition does not infer another bank or change chipset shadow policy.

## Source and data ownership

`shared/src/firmware/pnp-module.inc` composes the private code. The cooperating Setup bodies use shared include files. The composition without a private transport includes those same bodies inline. Board adapters retain hardware access, source mapping and reset policy.

`post-ui-api.inc` declares the private exports and resident imports once. `post-ui-aliases.inc` resolves their source names for each composition. Resident facades retain the established labels. Private code uses the existing real-mode dispatcher. Public PnP, APM, disk and interrupt services remain resident.

Tables, strings, the text renderer, storage codecs and settings validation remain in F000. Normal Setup drawing supplies DS=F000 for those tables. The renderer retains its existing literal-input contract for other data segments. Private CS must never stand in for the resident data segment.

Keep a complete near-jump cohort together. The short chipset popup borrows the generic choices routine's PUSHAD frame. The paged popup owns a separate frame and key loop. Help, redraw, Cancel and Apply must return through their original frame. A far bridge cannot replace one borrowed near-jump target independently.

## Calls and lifetime

A resident facade saves FLAGS and BX, then selects a private export. The private shim restores the original inputs before calling the body. It copies the body's returned BX and FLAGS into the facade's slots. Other returned registers retain the body's established behavior. Resident import callbacks use the original near service and return with RETF. Nested crossings follow the same contract.

Preserve each entry's original register, segment, flags and stack behavior. In particular, do not use a blanket register restore around a getter that returns BX or CF. Explicit resident far transfers own nonreturning reset and halt edges.

Dispatch resolves its module pointer through the current BDA EBDA pointer. A caller's FS can select a device record. It must reach the private body unchanged. The dispatcher builds the ordinary far-call return frame, restores its temporary registers, then uses RETF to enter the selected target. The export shim therefore retains the same frame offsets and returned-register contract.

The module and its journal remain live through early Setup, RAM and peripheral work, returning ROMs and the last private finalizer. Resident code then promotes the required runtime records, publishes them and releases the temporary arena. Public services resolve the current EBDA after release. They cannot call the old module or depend on its former location.

A returning ROM can reduce conventional memory below the arena. The existing allocator preserves that independent ceiling. Module storage and decoded output consume the same capacity as device records. Capacity failure keeps the module pointer zero or reports incomplete reconstruction through the existing owner. It does not fabricate successful device configuration or retire a pending rebuild request.

## Storage and encoding

Raw modules begin with `BAIPNP2` and a zero byte. Two little-endian words contain the complete raw length and entry offset. The extent is even, below 64 KiB and includes its header. The entry is the real dispatcher inside that extent.

The adapter supplies its serialized bank size to `shared/tools/post_module.py`. That format reserves the last bank byte for an independent SUM8 checksum. An even raw module fits only when its complete extent ends before that byte. In a 16 KiB serialized bank, 3FFEh fits raw and 4000h requires packing. Direct-ROM and window-copy raw transports retain their existing image checksum scopes.

Packed banks use this header:

| Offset | Field |
| --- | --- |
| 0 | Eight bytes: `BAIZX02` and zero |
| 8 | Decoded module length, WORD |
| 10 | ZX0 stream length, WORD |
| 12 | Decoded additive SUM16, WORD |
| 14 | Decoded entry offset, WORD |
| 16 | Forward ZX0 version 2 stream |

Unused serialized-bank bytes are FFh. The serializer computes the final checksum, reads the complete serialized bank again, decodes it and compares every raw byte. The decoded header, size, entry and checksum must agree. Remaining bits in the final control byte are padding. Extra input bytes are not padding.

The shared packer selects raw storage when it fits. It uses the pinned ZX0 encoder when packing is required. Direct-ROM and window-copy adapters retain raw storage while their declared windows fit. They do not gain a decoder or another memory copy implicitly.

## Assembly and loading

The top-alias composition assembles its fixed resident section followed by a raw module section with logical origin zero. `tests/post-module/raw-assembly.bin` is a nonflash intermediate. Its file length must equal the resident extent plus the header's complete raw extent. The host packer constructs the fixed bank and writes the final resident file. Stored length never changes resident or import addresses, so no second assembly or runtime relocation is needed.

The top-alias loader copies the complete serialized bank through its existing AH87 owner. Packed storage requires a separate, paragraph-rounded decoded allocation. Source and destination remain disjoint. Both reservations remain charged until final release. The pointer is published only after bounded decoding and complete decoded-header, entry and checksum validation. Failure uses the existing release path.

`zx0_decode` accepts DS:SI and BX as the exact source, ES:DI with DI zero, and CX as the exact output length. It preserves BP, DS and ES, clears DF and returns status in CF. The caller owns the other register and flags frame. Input refills, literal copies, Elias arithmetic, offsets and match copies are bounded. Match copies intentionally support forward overlap. Failure unwinds the internal stack through BP before returning.

The source derives from Emmanuel Marty's [8088 decoder](https://github.com/emmanuel-marty/unzx0_x86/tree/b2beaa04daf11ed67d68b911393ba6c04260e113). Its zlib notice remains in the bounded adaptation. The current emitted decoder is measured from its assembler labels. Do not treat a historical byte count as a size guarantee.

## Build dependency and reporting

Install the pinned Windows tools explicitly:

```powershell
python -B tools/install-zx0.py
python -B tools/install-zx0.py --check
```

The helper uses the immutable [ZX0 commit](https://github.com/einar-saukas/ZX0/tree/ecde3a2ae05061fe06469ed46df81a33b7de7d86) and checks each binary's SHA-256. Binaries remain under the ignored dependency owner `tools/deps/zx0`. Normal builds never download tools. A missing or changed required encoder stops the build with the installation command.

Every normal builder writes `rom-footprint.json` through `shared/tools/rom_footprint.py`. The report binds the final image's size, SUM32 and SHA-256. It separates resident free intervals, raw and stored module bytes, storage metadata, decoder code, bank padding, allocation alignment and temporary RAM. Raw length includes the raw header. Packed stored length includes the packed header. Variable device records remain an additional charge.

A fixed-size flash file does not shrink when occupied space falls. Resident headroom, packed-bank savings and temporary RAM are different measurements. Keep board offsets, transport recipes and measured board results in the port's developer guide.

## Validation and maintenance

`python -B shared/tests/test-rom-footprint.py --port all --case all` is the common executable check. Its named cases cover measurement, native roundtrip and rejection, real private rendering, popup frames, startup, Setup continuation, natural capacity and lifetime. The port validation declarations select this owner. The ordinary update hold for a port remains independent of its declared coverage.

Component fixtures establish the advertised BIOS state prefix and invoke the existing private loader before testing private facades. Full startup fixtures begin without a preinstalled module. External device models bind to the current candidate, never another port's disposable build.

Use existing media models for sector data and command variants. A model that only answers device identification cannot stand in for a complete CD drive.

Boot fixtures must model every controller that the boot path resets, including floppy IRQ delivery before disk or CD selection. Missing devices must return the modeled absent-media result. Do not let an incomplete fixture consume the firmware's full hardware timeout.

After an actual reset or runtime promotion, fixture models refresh cached state segments and bases from BDA `40E` before reading the result. A correct hardware register does not make a read from the former EBDA valid.

Seed test input through the memory model's write owner when that model supplies CPU reads. A host write to emulator memory alone can disappear on the next modeled read. When a firmware notice enables interrupts, track real interrupt entry and return frames separately from the synchronous writes under test. Keep the original write bounds for all other code.

Validation declarations name executable checks. An imported helper without a command entry point is not a passing check. Select its real caller once and retain the named case result.

Exercise selected-device segments as well as the root state segment. Follow the real commit order when testing failed saves: arm a verification fault at commit start, before the relevant byte is read back. Retain old-format inputs for migration tests, but compare a successful Save with the current format.

Retain an independent plaintext or screen oracle before moving code. A direct renderer test alone does not prove a private caller's segment contract. A successful component save alone does not prove reset and boot continuation. Exercise the actual transport, final serialized bank, private entry, resident callback, final return and intended loader.

Diagnostic firmware and boot sectors keep their original physical limits. Place test observers in available resident space before fixed compatibility entries. Share repeated guest operations and retain every oracle instead of enlarging an image to make a test fit.

Compile an unchanged decoder once for its vector checks. Keep its temporary files under the tested port. Each vector still receives a fresh CPU, guarded output buffer and caller-state checks.

Keep immutable listing caches local to each loaded candidate. In instruction observers, check the relevant address before reading state. Reuse unchanged CPU state within one memory callback. Use short equivalence checks for these harness optimizations; do not replace real guest operations or reduce fault coverage to hide test cost.

Build the listing's label-row index once. Compile each lookup pattern once, then search label rows rather than every instruction line. `python -B shared/tests/test-listing.py` checks scoped labels and cache ownership without a firmware run.

Use the normal zero POST delay setting when a fixture does not test the delay. Keep the default delay in its dedicated checks. Attach memory callbacks only while the modeled device needs them, with the same address bounds and fault checks.

Reuse a completed named case when its executable bytes, inputs and assertions remain applicable. After a failure, resume the unproved case and suffix. Do not repeat a qualified startup prefix to reach that case.

Before reusing a startup snapshot, match the image hash, device inputs and required terminal state. An expected allocation-failure snapshot is not a successful startup seed, even when its image hash matches. Keep each saved case under its own name.

Give each emulated case a specific terminal result. Supply the keyboard input that its expected notices require. Stop at an unexpected notice with the current instruction address, notice text and relevant state; do not spend the instruction budget waiting for input that the fixture will never send. Filter instruction observers by address or instruction length before reading CPU state.

Keep reusable mechanisms in the shared owners. Factor exact common bodies in place only when complete image identity proves the extraction. Preserve deliberate board selection and hardware differences. Software and emulator results do not establish physical electrical margins.
