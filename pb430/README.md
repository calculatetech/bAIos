# Packard Bell PB430

This port provides bAIos startup, Setup, disk and floppy services for the PB430. Use the image selected by `build/LATEST.txt` and keep a backup of the original ROM.

## Setup and startup

Press Delete during startup to open Setup. F9 loads defaults. F10 saves and restarts. The default boot order is CD-ROM, floppy A, then hard disk.

Chipset settings cover general controls, RAM timing, cache and memory, refresh, bus and ROM timing, and shadowing. Normal uses the baseline timings. Fast selects the combined faster memory settings. Manual permits individual adjustments. Use Normal first if a timing change makes the computer unreliable.

Refresh controls how often RAM is refreshed. Longer intervals can improve speed but can lose data with unsuitable RAM. Use the default interval unless the installed memory operates reliably with another choice.

Fast Boot shortens the visible RAM test without reducing detected memory. Pause stops the test temporarily. Escape skips the optional test. Delete opens Setup.

External cache requires enabled processor cache and a known cache capacity. `Present / unknown` means the BIOS cannot safely select its cache configuration. A valid saved cache choice remains authoritative.

## Video and compatibility

The default image uses the 60 MHz video-memory-clock variant. A matching50 MHz variant is also available. This choice concerns video memory, not the processor clock.

Onboard video requires its fixed ROM shadows. Leave optional shadows disabled where an expansion card uses that address range as RAM. Monitor type follows the board jumper.

Power saving and passwords are separate unfinished features. Read the [SL guide](../docs/sl486-support.md) for the distinction between CPU identification and available motherboard power control.

## Build and program

Run from the repository root:

```powershell
python -B pb430/tools/build.py
```

The physical image is `pb430/build/baios-pb430.bin`,131072 bytes. `baios-pb430-system.bin` is the 65536-byte system portion, not the complete programmer image. Use `--vga50` for the 50 MHz variant and `--stock-vga` for the original video provider. These variants use separate build directories.

Read `build/LATEST.txt` for the current candidate and programmer checksum. Retained VGA firmware remains subject to its original terms.

## Further reference

Use [POST codes](docs/post-codes.md) for startup troubleshooting. Developer material includes the [implementation record](docs/development/implementation.md), [register descriptions](docs/register-map.md), [validation reference](docs/validation.md), and [hardware evidence](docs/hardware-evidence.md).
