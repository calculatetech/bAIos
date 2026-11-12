# PC-Chips M919

This port provides bAIos for motherboard revisions 1.5 and 3.4. Read the known limitations below before programming. Use the ROM selected by `build/LATEST.txt`.

## Startup and Setup

Press Delete during startup to open Setup. F9 loads defaults. F10 saves and restarts. Use default timings until the machine runs reliably. Settings remain saved after power-off. The normal boot order is CD, floppy, then hard disk.

The BIOS detects RAM and cache capacity. Setup provides CPU/cache, PCI, local-bus, ISA, memory and ROM settings. Keep clock dividers consistent with the installed processor and cards. Fast Boot shortens the RAM test without reducing detected memory.

Primary Master, Primary Slave, Secondary Master and Secondary Slave are fixed IDE positions. Their settings stay with those positions when drives are removed. Auto selects a drive-supported PIO mode up to PIO4. Block mode and 32-bit transfers are separate choices. Onboard IDE Controller can enable both channels, only the primary channel, or neither channel.

Normal defaults request enabled caches and write-back where supported. A failed or unknown cache configuration remains off. `SL Enhanced` in the CPU name describes processor capability. Read the [power-saving guide](../docs/sl486-support.md) for DOS POWER.EXE.

This board uses serial mice and has no PS/2 mouse connector. PS/2 mouse initialization is disabled. There is no game-port setting. Floppy Controller is in Drives, parallel-port DMA is in Devices, and DRAM timings are in Chipset > Memory.

Setup > Plug and Play assigns resources to compatible expansion cards. Read the [Plug and Play guide](../docs/plug-and-play.md) for BIOS/operating-system policy and manual reservations for older cards.

In Chipset > PCI Interrupts, leave each Slot Using INT# setting on Auto. Auto reads the interrupt pin reported by the card. INTA through INTD name physical pins, not IRQ numbers or a selection order. The board connects each slot's INTA to a different route. Help shows pins that share a route. Select a pin manually only when the card reports it incorrectly. Changing this setting does not change the card's wiring.

The BIOS assigns free IRQs to routes used by installed devices before sharing an IRQ. Reserved IRQs and active ISA devices remain excluded. Older IRQ-number choices reset to Auto when loaded. Other saved settings remain unchanged.

Intel ICU and WINICU use the ESCD database in the BIOS flash. Saving it requires a supported writable chip and the correct programming-voltage setting for that chip. This port supports the Macronix MX28F1000P and SST29EE010. The MX28F1000P requires a 12 V programming setting. Use your board revision's jumper diagram. The Intel utility may list only motherboard and ISA devices even when the startup summary detects PCI cards.

## Known limitations

Revision3.4 can fail to warm reset with Microsoft EMM386 loaded. Its recurring floppy-controller problem is also unresolved. A successful boot with different memory managers does not remove those limitations.

VLB graphics can show incorrect colors during sampled digital sound. This also occurs with the original BIOS. Music-only and PC-speaker sound do not show that interaction. The sound-crackle improvement does not fix these colors.

## Build and ROM files

Run from the repository root:

```powershell
python -B tools/build-rom.py m919
```

`m919/build/baios-m919.bin` is the 131072-byte physical image. Use the programmer checksum recorded in `build/LATEST.txt`. Keep the original ROM and a way to restore it.

## Further reference

Use [POST codes](docs/post-codes.md) to interpret a diagnostic card. Developers can read the [implementation reference](docs/development/implementation.md), [SL/SMM reference](docs/development/sl486.md), [register guide](docs/research/m919-registers.md), and [port roadmap](docs/roadmap.md).
