# bAIos

bAIos is a replacement BIOS for selected 386- and 486-era computers. It starts the computer, checks memory, provides Setup, and loads an operating system.

Choose the manual for your motherboard before downloading or programming a ROM:

| Port manual |
| --- |
| [Compaq Presario 800](presario-800/README.md) |
| [Mitsubishi MP386/25](mp386/README.md) |
| [Packard Bell PB430](pb430/README.md) |
| [PC-Chips M919](m919/README.md) |

Each port manual describes its hardware, available settings, ROM files and known limitations. A ROM for a different motherboard can prevent the computer from starting.

## Find the right ROM

Open the selected port's `build/LATEST.txt`. It lists the current image files, version and programmer checksums. A checksum is a number used to compare file contents.

A completed candidate includes its version and build time in the filename. A fixed filename is a development image that can change between tests. Follow the port manual when an image uses separate ROM chips or includes video firmware.

Keep a backup of the original ROM and a way to restore it before programming. Use the image size and chip arrangement specified by the port manual.

## Setup and startup

Press Delete during startup to open Setup. The help panel explains the selected setting. Save changes when you want to use them after restart. Discard changes to keep the previous settings.

F9 loads the default settings. F10 saves settings and restarts. Saved settings take precedence over defaults during ordinary startup.

The default boot order is CD-ROM, floppy disk, then hard disk. A boot device must contain a usable operating system or boot program.

POST Delay in Boot pauses before the summary. The default is 5 seconds. Choose 0 to skip this pause. This choice does not add a pause before the startup screen.

On ports with PCI display selection, Video Init Order chooses PCI/ISA or ISA/PCI. PCI/ISA is the default. The BIOS uses the other bus when the preferred bus has no usable display.

Supported Plug and Play ports show a device listing below the startup summary. It reports detected expansion devices, assigned resources and configuration status. See the [Plug and Play guide](docs/plug-and-play.md).

Fast Boot shortens memory testing. It does not reduce the amount of detected memory. Leave timings at their defaults until the computer runs reliably.

## Features and help

Cache keeps frequently used data near the processor. Write-through also writes data to RAM immediately. Write-back can postpone those writes for better performance. Setup offers only the modes available through the port.

IDE Auto mode selects a transfer mode supported by the drive and its controller. A higher PIO number means a shorter transfer cycle. The BIOS supports PIO0 through PIO4, subject to the controller and drive limits. Transfer width and block mode are separate settings.

The [Plug and Play guide](docs/plug-and-play.md) explains automatic card configuration and manual resource reservations.

The [SL-enhanced CPU guide](docs/sl486-support.md) explains processor power-saving support and DOS POWER.EXE. The [POST-code guide](docs/post-codes.md) explains startup codes shown by a diagnostic card.

## Build and development

Build commands and required inputs belong to each port manual. Developers can read the [shared source guide](shared/README.md), [porting instructions](docs/porting.md), [update guide](docs/port-updates.md), and [repository layout](docs/repository-layout.md).

Board research, register descriptions and validation records live under each port's `docs/` directory. The [roadmap](docs/roadmap.md) tracks shared work.

## License

Original bAIos source and documentation use the [MIT license](LICENSE). Vendor firmware, manuals, operating systems and external tools keep their own terms. They are not included in the public source repository. See [public source and private inputs](docs/public-source.md).
