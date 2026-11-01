# Shared integration reference

Developer notes moved from repository-wide documents. These are source and validation records, not operating instructions. Each section names its original document. A paragraph can describe a shared change across several ports. Port manuals own current user instructions.

## README.md

| Port | Status |
| --- | --- |
| [Packard Bell PB430](../../README.md) | Physically tested development port with extensive timing and cache controls. |

```powershell
python -B tools/build-rom.py m919
python -B mp386/tools/build.py
python -B pb430/tools/build.py
pwsh -NoProfile -File presario-800/tools/build.ps1
```

Output stays in each port's `build/` directory. The PB430 build checks the physical image size, system checksum, reset vector, retained VGA bytes, and input identities. Its output includes the additive programmer checksum, `SUM32`.

Original bAIos source and documentation are available under the [MIT license](../../../LICENSE). Vendor firmware, manuals, and external test software retain their own terms. They are not tracked in Git. PB430 flash images include retained VGA firmware, which is outside the bAIos MIT license.


## shared/README.md

`src/pc/cache-test.inc` owns the short direct-SRAM workload: two complementary word-pattern write/read passes and retained unique address witnesses across the detected span. The board adapter supplies safe SRAM access, capacity, scratch ownership, reference controller transitions and result publication. PB430 is the first consumer; this does not establish a shared phase or reset driver for all ports.

`src/pc/ram-test-state.inc` owns normal-startup marker classification. An unfinished test does not create a detected-memory-error notice. Explicit pending notices remain pending. Adapters retain their reset gates and RTC access; PB430 only clears its unfinished marker at that entry, while Presario retains its existing broader startup placement.

`BOARD_POST_RAM_ROW` selects the live RAM counter and status row. Its default preserves existing layouts. PB430 selects row6, leaving a blank row after L2 and placing the bank list on row7.

Normal Setup defaults are owned by `src/setup/defaults.inc`: CD, floppy, then hard disk; supported caches enabled, with WB where the adapter supports it. Both Setup default actions use `setup_defaults`. Valid saved selections remain authoritative, and recovery keeps its separate cache-off policy. Adapters translate the common intent into their existing records; this does not add unsupported cache modes to PB430 or MP386.

`src/firmware/floppy.inc` initializes the global AT DMA cascade before checking the optional floppy-controller policy. Disabled FDC policy still issues no FDC commands, DMA2 transfer programming or IRQ6 enable. Other ISA DMA devices keep their cascade path. PB430 also retains its earlier refresh/DMA preparation. Focused compiled checks cover all four port entry points and a guest-programmed DMA1 payload.

## docs/plans/BAIOS-011-sl486.md

Feature versions: M919 0.10.0, PB430 0.3.0, Presario 800 0.3.0, and MP386 0.4.0.

PB430 places its normal CPU helpers in the existing late ROM extension owner. This preserves the fixed F065 VGA entry as the module grows. Diagnostic builds that already move CD boot late keep CPU helpers early. The board's CPU composition file has one definition at either placement. Both VGA configurations and these diagnostic layouts retain the same query contract and require their existing image-integrity checks.


## docs/port-updates.md

Use the existing Windows toolchain with Git, Python, NASM, PowerShell and the recorded emulator installations. Supply the private inputs from [the input catalogue](../../../docs/private-inputs.json), the port references, installed resources and test media. PB430 reference mapping also requires its annotated `pb430/reference/maps/entries.json` seed map. The pipeline does not download resources or change the source checkout. PB430 and the Presario native network check need the recorded b10408 emulator and accompanying libraries. Other native checks use the existing installed emulator.

The `boot-source` check on PB430, MP386 and M919 reuses the Presario failed-HDD, CD and Other producer proof. Port adapters supply existing external devices and enter real cold POST or installed INT19. The selector owns source identity throughout. Installed disk services must retain native geometry and read/write the independently selected sector. M919 uses its existing composed POST context and requires the requested image to match the executed default candidate exactly; differing variants are rejected.

After every current port check passes, the pipeline builds final candidates. It records each file's size, SHA256 and additive byte sum, `SUM32`. It then uses the existing cleanup guard to remove the disposable workspace. The cleanup guard replaces the previous published logs and results before copying new evidence. Each port receives only its own candidates, report, command logs and comparisons in its `build/review/shared-update/` directory. Presario and PB430 each receive a 50/60 MHz pair with the same system BIOS. The PB430 pair uses VGA1.41 and differs from the original stock VGA variant. MP386 receives its combined image and both programmer lanes.

```powershell
python -B tools/update-ports.py --port pb430 --check cache-check
```

## docs/porting.md

Read this document before selecting source for a port. Apply it to the Presario, M919, PB430, and future donors.
The modular base supplies reusable services. It does not establish that donor hardware setup works on another board.
The [repository cache rule](../../../AGENTS.md#reference-cache-setup) owns the requirements for matching the reference cache sequence.

The current worked example is [the PB430 porting lessons](../porting-lessons.md).
Its physical results qualify only the tested PB430 configuration. They do not make its hardware owners portable to another chipset.

## docs/post-codes.md

Start with the board reference: [Presario 800](../../../presario-800/docs/post-codes.md), [PB430](../post-codes.md), [MP386](../../../mp386/docs/post-codes.md), or [M919](../../../m919/docs/post-codes.md). Use the preceding codes and the screen to distinguish overlapping meanings.

`71` through `83` can repeat for master and slave on each scanned channel. PB430 also uses several `76`–`7F` values during timing/cache work; its board table gives that context. M919 does not emit the separate primary-channel `84`/`85`/`86` markers.

`C9` can remain on the card while later settings or RAM work runs. It does not identify a RAM-test address. PB430 has additional markers after keyboard initialization.

PB430 reuses `D0`–`D4`, `E8`, `EA` and `EB` in other phases. Its detailed table takes precedence for those phases. A hardware stop can also leave an earlier progress code displayed without emitting an error code.

## docs/public-source.md

- PB430: `pb430/reference/pb430-m27c1001.bin`, `pb430/reference/acc386.BIN`, and `pb430/reference/gd542x-141-vga60.rom` for the default build. The `--stock-vga` build does not require the separate VGA60 file.
- Presario 800: `presario-800/reference/COMPAQ_PROLINEA_MT_05-02-94.BIN`, `presario-800/reference/gd5428_1-41.bin`, and `presario-800/reference/baios-presario800-vga141-bus07.bin` for the default build.
- Other hardware and comparison tests require the ROMs and media named in their port documentation. A checksum match identifies an input; it does not grant distribution rights.

Historical RAM/cache comparison code is retained as original-source fixtures in `m919/tests/baselines/`. PB430 shared-source comparisons use a checked-in hash table. These checks do not require private Git objects. The completed private document-relocation audit is retired from this distribution.


## docs/repository-layout.md

During bench work, reuse fixed filenames such as `baios-pb430.bin` or the MP386 combined/even/odd names. A new successful normal build updates the bench record. Test and research builds in subfolders do not replace the port's latest pointer.

## docs/roadmap.md

- **BAIOS-003: Share cache initialization and transition tests across controllers.** PB430 consumes a shared short SRAM workload and shared interrupted-RAM-test marker policy. Presario and PB430 use the maintained shared firmware owners. The [automated port update pipeline](../../../docs/port-updates.md) builds and validates maintained ports. Preserve each controller's complete reference setup and reset sequence. The complete common cache phase/transition driver and remaining M919 cache migration stay separate unfinished work.See the [cache lifecycle design and migration plan](../../../docs/plans/BAIOS-003-cache-lifecycle.md).

- **BAIOS-007: Add boot and Setup passwords. Very low priority.** Define shared password behavior, storage and owner recovery before port-specific integration. This is separate from the current PB430 hardware settings work.

## docs/sl486-support.md

| Port | Established evidence | Remaining limit |
| --- | --- | --- |
| PB430 | The retained ACC2168 documentation does not define the SMRAM and SMI source controls needed here. | SL signal routing remains unknown. The different ACC2087 register map must not be transplanted. |

M919 runs this proof through `python -B m919/tools/test-hardware.py --case cpu`. PB430 and MP386 expose a `cpu` case in their existing `tools/test-port.py` commands. Presario's `tools/test-shared-adoption.py --case cpu` uses the selected `BAIOS_BUILD_DIRECTORY`. The normal automated port checks include CPU coverage. These synthetic observations prove firmware decisions, not physical SL wiring or stability.
