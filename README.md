# bAIos

bAIos is an experimental replacement BIOS for selected 386- and 486-era PCs. It combines shared firmware services with board-specific chipset, cache, and controller initialization.

The project focuses on reliable startup, useful diagnostics, configurable memory timings, and compatibility with real DOS software. Hardware evidence and working reference behavior guide each port.

## Ports

| Port | Status |
| --- | --- |
| [Compaq Presario 800](presario-800/README.md) | Original implementation and behavior baseline. |
| [Mitsubishi MP386/25](mp386/README.md) | Physically tested port with expansion RAM, 32 KiB cache, shared POST and decoded timing controls. |
| [Packard Bell PB430](pb430/README.md) | Physically tested development port with extensive timing and cache controls. |
| [PC-Chips M919](m919/README.md) | Experimental port. Physical cache stability remains unresolved. |

Read the selected port's documentation before building or flashing. A passing source check or emulator test does not establish hardware stability. Keep a known-good ROM and an external programmer available.

## Build

The development tools target Windows with PowerShell, Python 3.11 or later, and NASM on `PATH`. Run PowerShell with `-NoProfile` and Python with `-B`. Model tests also use Unicorn. Some tests need 86Box and separately supplied operating-system media.

Vendor ROMs and manuals are not included. Obtain the exact inputs listed in [Public source and private inputs](docs/public-source.md) when the selected build requires retained vendor firmware. The MP386 build uses original bAIos source without a retained vendor image. Its reference checks require the separately supplied OEM even/odd ROMs.

From the repository root:

```powershell
python -B tools/build-rom.py m919
python -B mp386/tools/build.py
python -B pb430/tools/build.py
pwsh -NoProfile -File presario-800/tools/build.ps1
```

Output stays in each port's `build/` directory. The PB430 build checks the physical image size, system checksum, reset vector, retained VGA bytes, and input identities. Its output includes the additive programmer checksum, `SUM32`.

For source-only checks without vendor inputs:

```powershell
python -B tools/check-public-source.py
New-Item -ItemType Directory -Force build | Out-Null
python -B shared/tests/test-emulator.py build
```

## Repository layout

- `shared/`: common firmware services and test tools.
- Port directories: board adapters, Setup choices, tests, and hardware evidence.
- `docs/`: shared porting guidance, publication rules, and the global roadmap.
- `tools/`: common build, validation, and cleanup commands.

See [porting instructions](docs/porting.md) before starting a port. Keep proven display and service behavior, adapt controller-specific operations, and record physical results separately from model results. The [global roadmap](docs/roadmap.md) tracks shared work; each port owns its own roadmap.

## License

Original bAIos source and documentation are available under the [MIT license](LICENSE). Vendor firmware, manuals, and external test software retain their own terms. They are not tracked in Git. PB430 flash images include retained VGA firmware, which is outside the bAIos MIT license.
