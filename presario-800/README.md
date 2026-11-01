# Compaq Presario 800

This port builds bAIos for the Presario800 platform. It provides startup checks, Setup, IDE and floppy services, keyboard and PS/2 mouse support, and serial/parallel ports.

The system BIOS is 64 KiB. The physical ROM image is 128 KiB and also contains the selected VGA firmware and retained resources. Program the complete physical image named by `build/LATEST.txt`.

## Setup and startup

Press Delete during startup to open Setup. F9 loads defaults. F10 saves and restarts. The default boot order is CD-ROM, floppy, then hard disk. Saved boot choices remain in effect until changed.

Use default memory and cache timings first. Fast Boot shortens memory testing without reducing detected capacity. Pause temporarily stops the test, Escape skips optional testing, and Delete opens Setup.

The BIOS supports the primary IDE master and slave. Auto selects a supported transfer mode up to PIO4, subject to drive and controller limits. Block mode and transfer width are separate choices.

The [SL-enhanced processor guide](../docs/sl486-support.md) explains CPU naming and DOS idle power saving. CPU identification alone does not promise every motherboard power-management function.

## Memory and video

Memory support depends on the installed modules and bank arrangement. Configurations above 64 MiB remain unresolved. Read the developer memory notes before using a configuration outside the established range.

The default image uses the selected60 MHz Cirrus video-memory-clock variant. The50 MHz image is a separate choice. Video-memory clock does not set the processor bus clock.

## Build and program

Run from the repository root:

```powershell
pwsh -NoProfile -File presario-800/tools/build.ps1
```

Supply the retained inputs listed in the [implementation reference](docs/development/implementation.md#dependencies) and [input catalogue](../docs/private-inputs.json). Use `build/LATEST.txt` for the exact current filenames, image sizes and programmer checksums.

Keep the original ROM and a way to restore it before programming. VGA firmware and retained resources keep their original license terms.

## Further reference

Use [POST codes](docs/post-codes.md) for startup troubleshooting. Developers can read the [implementation and validation reference](docs/development/implementation.md), [VGA reference](docs/vga141.md), and [memory timing notes](docs/fpm-dram-presets-25-33mhz.md).
