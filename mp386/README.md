# Mitsubishi MP386/25

This port targets the 25MHz386DX motherboard and its expansion-memory card. Onboard devices are routed by the board switches. Read Devices in Setup for the switch guide. Turn power off before changing switches.

## Startup and Setup

Power-cycle after programming. Press Delete during startup to open Setup. If configuration is invalid, Enter saves defaults and restarts. F9 loads defaults in Setup. F10 saves changes and restarts. No original Setup disk is required.

The default boot order is CD-ROM, floppy, then hard disk. The primary IDE channel supports master and slave. Use the drive manufacturer's single-drive setting when a drive requires one.

Fast Boot shortens the RAM sweep. Full testing supports Pause, Escape and Delete. The memory controller and cache remain initialized when a test is skipped.

The physical cache switch controls the 32 KB external cache request. There is no software L2 enable setting. The processor has no internal cache. A failed cache test prevents normal activation.

Chipset settings cover bus and DMA, memory and ROM, onboard banks, then expansion banks. Leave timings at defaults until the computer runs reliably.

## Memory and compatibility

Some configurations with a 3Com 3C509B or 3C509TP can stop during startup. This also occurs with the original BIOS. If that card prevents startup, remove it while troubleshooting. The cause remains unresolved.

With 18 MiB installed, the accepted contiguous map provides15232 KiB of extended memory. The BIOS reserves8 KiB for its workspace, leaving632 KiB of base memory. The remaining installed memory is not exposed as additional contiguous RAM.

HIMEM.SYS can control A20 after boot. A benchmark that performs unsupported operations under EMM386 can require plain DOS instead. CPU recognition does not establish compatibility with every processor-upgrade module.

## Build and program

Run from the repository root:

```powershell
python -B mp386/tools/build.py
```

| File under `mp386/build/` | Bytes | Purpose |
| --- | --- | --- |
| `baios-mp386.bin` |65536| Complete system image |
| `baios-mp386-even.bin` |32768| Low/even ROM chip |
| `baios-mp386-odd.bin` |32768| High/odd ROM chip |

Use the original board's even/odd chip assignments. `build/LATEST.txt` names the current files and programmer checksums. The system uses the installed video card's ROM. Keep backups of the original ROM chips.

## Further reference

Use [POST codes](docs/post-codes.md) for startup troubleshooting. Developers can read the [implementation record](docs/development/implementation.md), [timing reference](docs/research/timing-controls.md), and [roadmap](docs/roadmap.md).
