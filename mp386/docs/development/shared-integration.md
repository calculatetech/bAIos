# Shared integration reference

Developer notes moved from repository-wide documents. These are source and validation records, not operating instructions. Each section names its original document. A paragraph can describe a shared change across several ports. Port manuals own current user instructions.

## README.md

| Port | Status |
| --- | --- |
| [Mitsubishi MP386/25](../../README.md) | Physically tested port with expansion RAM, 32 KiB cache, shared POST and decoded timing controls. |

Vendor ROMs and manuals are not included. Obtain the exact inputs listed in [Public source and private inputs](../../../docs/public-source.md) when the selected build requires retained vendor firmware. The MP386 build uses original bAIos source without a retained vendor image. Its reference checks require the separately supplied OEM even/odd ROMs.

```powershell
python -B tools/build-rom.py m919
python -B mp386/tools/build.py
python -B pb430/tools/build.py
pwsh -NoProfile -File presario-800/tools/build.ps1
```

## shared/README.md

The MP386 extended-RTC adapter selects verified AT checksum acknowledgment through `src/pc/cmos-checksum.inc`. Ordinary RTC ports retain the existing checksum writer. Board-selected processor and A20 primitives omit 486-only operations on the 386 target. Devices can select board-owned drawing and help callbacks while retaining the shared Setup renderer.

The existing `BOARD_BOOT_HANDOFF` callback runs at the INT19 bootstrap entry, including direct software restarts. The MP386 adapter uses it to release its motherboard A20 override. Shared memory services still save and restore the adapter's gate token around extended-memory copies. Other adapters retain their existing hook selection and call sequence.

`BOARD_RTC_EXTENDED_READ` and `BOARD_RTC_EXTENDED_WRITE` can store logical indexes40h..7Fh outside the physical RTC. The shared RTC helpers retain their flags and interrupt contract. MP386 uses its OEM NVRAM protocol instead of assuming128 physical RTC bytes. `BOARD_SETUP_READONLY_PAGES` bounds selection when a page has no editable field. Other ports retain their assembled default path.

Normal Setup defaults are owned by `src/setup/defaults.inc`: CD, floppy, then hard disk; supported caches enabled, with WB where the adapter supports it. Both Setup default actions use `setup_defaults`. Valid saved selections remain authoritative, and recovery keeps its separate cache-off policy. Adapters translate the common intent into their existing records; this does not add unsupported cache modes to PB430 or MP386.

## docs/plans/BAIOS-011-sl486.md

Feature versions: M919 0.10.0, PB430 0.3.0, Presario 800 0.3.0, and MP386 0.4.0.

| Boundary | Discriminator and nearest contrast | Production path and oracle | Named check |
| --- | --- | --- | --- |
| B2: Legacy exclusion | Intel desktop evidence versus non-CPUID Cyrix or a 386 CPU. | Real adapter returns unknown without CPUID or any new 486-only instruction when ID is not writable. Existing legacy names remain unchanged. | Shared CPU proof with ID/AC/division inputs on all ports, including MP386. |

## docs/port-updates.md

The `boot-source` check on PB430, MP386 and M919 reuses the Presario failed-HDD, CD and Other producer proof. Port adapters supply existing external devices and enter real cold POST or installed INT19. The selector owns source identity throughout. Installed disk services must retain native geometry and read/write the independently selected sector. M919 uses its existing composed POST context and requires the requested image to match the executed default candidate exactly; differing variants are rejected.

After every current port check passes, the pipeline builds final candidates. It records each file's size, SHA256 and additive byte sum, `SUM32`. It then uses the existing cleanup guard to remove the disposable workspace. The cleanup guard replaces the previous published logs and results before copying new evidence. Each port receives only its own candidates, report, command logs and comparisons in its `build/review/shared-update/` directory. Presario and PB430 each receive a 50/60 MHz pair with the same system BIOS. The PB430 pair uses VGA1.41 and differs from the original stock VGA variant. MP386 receives its combined image and both programmer lanes.

A subset of ports or checks is a partial run. It cannot promote candidates or claim complete validation. Full validation means every current command for every active port. Two retired MP386 bench-probe suites and a frozen whole-ROM source-equivalence check remain historical, with their original conditions and exclusion reasons. The source-equivalence case permits only the old Auto CHS patch, so current shared adoption cannot satisfy it. Its pins are unchanged. They are not reported as passed. Use `--historical` only when those original superseded inputs are available. The pipeline never rebuilds current firmware under their old names.

## docs/post-codes.md

Start with the board reference: [Presario 800](../../../presario-800/docs/post-codes.md), [PB430](../../../pb430/docs/post-codes.md), [MP386](../post-codes.md), or [M919](../../../m919/docs/post-codes.md). Use the preceding codes and the screen to distinguish overlapping meanings.

## docs/repository-layout.md

During bench work, reuse fixed filenames such as `baios-pb430.bin` or the MP386 combined/even/odd names. A new successful normal build updates the bench record. Test and research builds in subfolders do not replace the port's latest pointer.

Use `--directory <port>/build/review/<case>` to finish a recorded build from another allowed output directory. The command validates the assembly hashes and complete artifact group, then writes names such as `baios-mp386-even-v0.1.1-20261027T203000Z.bin` directly in the port's build root. All members share one group identity. The UTC timestamp is the most recent recorded assembly in the group. VGA pairs must share their system BIOS; programmer lanes must reproduce the combined image.

## docs/sl486-support.md

| Port | Established evidence | Remaining limit |
| --- | --- | --- |
| MP386 | The native board is a 386DX platform with a separate upgrade policy. | A desktop 486 requires an identified adapter and its electrical documentation. The query enables no 486 upgrade feature. |

M919 runs this proof through `python -B m919/tools/test-hardware.py --case cpu`. PB430 and MP386 expose a `cpu` case in their existing `tools/test-port.py` commands. Presario's `tools/test-shared-adoption.py --case cpu` uses the selected `BAIOS_BUILD_DIRECTORY`. The normal automated port checks include CPU coverage. These synthetic observations prove firmware decisions, not physical SL wiring or stability.
