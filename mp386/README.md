# Mitsubishi MP386/25

This port targets the 25 MHz 386DX board with the TI TACT83000 chipset and Intel 82385 cache controller. The Mitsubishi OEM ROM supplies the memory-controller, cache and board-wiring reference. The working hardware has 2 MiB onboard and four 4 MiB banks on the expansion card.

The port boots on the physical board with expansion RAM, ROM shadowing and working 32 KiB cache. The user confirmed the reviewed POST and Setup image works. Software checks do not establish electrical stability or qualify faster RAM timings.

The [v0.2.0 release](docs/releases/v0.2.0.md) provides combined and split programmer images. It includes the legacy IDE and DOS A20 fixes and retains the existing firmware identity.

## Build and program

From the repository root, run:

    python -B mp386/tools/build.py

The build writes these files under `mp386/build/`:

| File | Bytes | Purpose |
| --- | --- | --- |
| `baios-mp386.bin` | 65536 | Complete system ROM |
| `baios-mp386-even.bin` | 32768 | Low/even byte EPROM |
| `baios-mp386-odd.bin` | 32768 | High/odd byte EPROM |

Use the even/odd assignments established by the original `mp386even.bin` and `mp386odd.bin` inputs. The build checks the reset entry, system checksum, sizes and complete lane recombination. `rom-checksums.json` includes the additive byte sum, `SUM32`, for each file.

The system ROM uses the VGA ROM on the installed video card. It does not contain a VGA ROM. Boot order defaults to CD-ROM, floppy, hard disk, then Disabled. Existing saved boot choices are retained. The shared disk services support the primary IDE master and slave.

Auto-detected CHS disks receive device-parameter initialization before the first read and after a channel reset. LBA disks retain their existing path. For a single WD Caviar WDAC2420, use the drive's Single configuration, with no jumper on J8.

The boot handoff clears the motherboard A20 override and leaves the keyboard-controller gate available to DOS. HIMEM.SYS can then enable and disable A20. Run hardware benchmarks without EMM386 if they use operations that its virtual machine does not support. The reported Landmark DMA-mode error under EMM386 remains an unconfirmed compatibility issue.

## POST and configuration

Power-cycle the board after programming. If POST reports invalid configuration, press Enter to save defaults or Delete to open Setup. Saving defaults causes one restart. F10 saves Setup changes and restarts. No external OEM Setup disk is needed.

The port uses ordinary RTC bytes through index 3Fh. It stores the remaining bAIos configuration in Mitsubishi NVRAM 0200h..023Fh through the OEM port-48 protocol. This replaces part of the old OEM configuration. It does not restore or maintain the OEM format.

The board adapter initializes DRAM and keeps external cache off before using RAM. It qualifies the contiguous memory range, prepares the system-ROM shadow, and enters the shared bAIos POST flow. POST qualifies cache before the visible RAM test. The shared RAM sweep runs with either cache-switch setting and supports the normal Pause, Escape and Delete controls. Shadow and cache activation remain after RAM testing and the final Setup entry gate.

The Intel cache transition remains in the hardware adapter. Its temporary mappings and register order differ from the direct SRAM aperture used by other ports. POST and the summary show `32 KB` when the requested cache passes qualification, `Disabled` when the switch is off, and `Cache test failed` after a restored data-test failure. A controller failure that leaves the hardware state unverified still stops POST.

CMOS checksum warnings do not qualify cache. The physical switch, SRAM test and current qualified memory range determine cache activation. Configuration warnings remain separate.

Onboard peripheral routing remains controlled by the board switches. Devices displays the supplied SW1/SW3 switch guide. Turn power off before changing a switch. The page does not claim a live SW1 readback because that input mapping is incomplete.

Fast Boot is on the Boot page. Disabled is the default and runs the full RAM sweep. Enabled limits that sweep to memory below 1 MiB. It does not reduce detected capacity. F9 restores all Setup defaults. Save applies changes after restart.

If power loss or a hard reset interrupts a timing trial, the next start uses working timing defaults so Delete can reach Setup. This does not report a RAM failure or consume a RAM retry. The saved timing data remain stored. Discard and canceled or failed Save keep safe timing selection; a fully verified Save releases it. Ctrl+Alt+Del retires an ordinary trial and retries the saved choices. Only an actual failed RAM comparison uses the RAM failure and retry path.

Chipset groups follow this order: Bus and DMA, Memory and ROM, Onboard Banks 1-2, then Expansion Banks 1-4. They expose bus clock selection and division, bus waits, DMA timing, refresh and memory-cycle timing, system-ROM shadowing, and separate timings for each RAM bank. Default values retain the working board timings. Page Mode and RAM Interleave remain automatic. The [timing contract](docs/research/timing-controls.md) records the decoded fields and preserved bits.

Cache has no software enable option in Setup. SW3/1 controls its request. The processor has no internal cache. Intel documents 32 KiB for the 82385, and the physical CACHECHK result agrees.

## Accepted memory behavior

With 18 MiB installed, the current qualified contiguous range ends at physical address `FE0000`. This gives 15,232 KiB of extended memory. The OEM reports the same 15,872 KiB total when it includes its 640 KiB base count. bAIos reserves 8 KiB for its workspace, so INT12 reports 632 KiB of base memory.

Both BIOSes expose sampled copies of the system ROM at `FF0000` and `FF8000`. Separate aperture tests show accessible backing RAM and RAM above 16 MiB. These results do not prove that the overlay is permanent or that RAM is defective. The user accepts the OEM-compatible contiguous limit until the chipset user's guide becomes available. The extra 2 MiB recovery and split-range E820 experiment are removed.

The OEM CACHECHK run repeatedly checks below 1 MiB instead of progressing. The working bAIos benchmark behavior is accepted. Attempts to change this mapping are deferred. [MP386-002](docs/roadmap.md) records this decision.

## Software checks and evidence

Run each focused check from the repository root:

    python -B mp386/tools/test-port.py --case image
    python -B mp386/tools/test-post.py
    python -B mp386/tools/test-cache.py --image mp386/build/baios-mp386.bin --case instructions
    python -B mp386/tools/test-port.py --case boot
    python -B mp386/tools/test-port.py --case setup
    python -B mp386/tools/test-port.py --case ram
    python -B mp386/tools/test-port.py --case retained
    python -B mp386/tools/test-setup-controls.py --image mp386/build/baios-mp386.bin --boot
    python -B mp386/tools/test-ata-chs.py --image mp386/build/baios-mp386.bin
    python -B mp386/tools/test-a20-handoff.py --image mp386/build/baios-mp386.bin

The checks require NASM, Python, Unicorn and Capstone from the existing project toolchain. Reference comparisons use the supplied OEM even/odd ROMs. The retained-port check needs the existing PB430 reference inputs. Building this port itself requires no vendor ROM file. The cache, memory and shadow test commands also provide individual reference-comparison cases through their `--case` options.

The device fixtures execute the assembled firmware from its reset vector. They model external AT devices, VGA services, TI register access, DRAM probe aliases, and a conservative 64-byte RTC with separate Mitsubishi NVRAM. The independent signed boot sector uses the installed disk and extended-memory services. These synthetic results establish source integration and reference agreement. They do not establish electrical behavior, real VGA compatibility, RAM stability or cache operation on the board.

Startup progress codes precede and follow the reference routines. `10` means startup entered, `11` enters cold TI initialization, `12` returns from it, `20` starts the early keyboard-controller transaction, `21` completes it, `22` enters the normal memory-map continuation, and `23` reaches RAM workspace setup. `E1` stops on an unusable memory result. `E2` stops on an early keyboard-controller failure. No progress output occurs inside the TI routines.

The [reference assessment](docs/research/initial-reference-assessment.md) describes the supplied images and missing register guide. The [port roadmap](docs/roadmap.md) tracks the port and accepted limits.

Preview build cleanup with:

    powershell -NoProfile -File tools/clean-build.ps1 -Port mp386 -WhatIf

The port retains current images, the active worktree, original diagnostics, research inputs and current comparison results.
