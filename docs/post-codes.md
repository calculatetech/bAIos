# Shared POST and device codes

All values are hexadecimal bytes written to I/O port `80h`. A code means that its marker was reached. It does not prove that the next operation finished. Codes are not in numeric execution order, and some values have different meanings in different phases.

These tables describe shared startup stages. Ports can omit a stage or reuse a value. Their own code tables take precedence. Diagnostic ROMs can use additional codes. A display of `--` is not a bAIos code.

Start with the board reference: [Presario 800](../presario-800/docs/post-codes.md), [PB430](../pb430/docs/post-codes.md), [MP386](../mp386/docs/post-codes.md), or [M919](../m919/docs/post-codes.md). Use the preceding codes and the screen to distinguish overlapping meanings.

## Disk discovery and boot

| Code | Marker reached |
| --- | --- |
| `70` | IDE discovery starts. Scan the channels enabled by the port. |
| `71` | Select an ATA/ATAPI device. |
| `72` | Wait for the device to stop being busy; this can take up to 30 seconds. |
| `73` | Check the packet-device signature. |
| `74` | Issue ATA IDENTIFY DEVICE. |
| `75` | Begin packet-device identification; mask its interrupts. |
| `76` | Wait for the packet device to settle. |
| `77` | Issue ATAPI IDENTIFY PACKET DEVICE. |
| `78` | Wait for identification data. |
| `79` | Reset an unresponsive packet device. |
| `7A` | Wait for packet-device reset to finish. |
| `7B` | Retry packet-device identification. |
| `7C` | Read the 512-byte identification block. |
| `7D` | Wait for identification transfer completion. |
| `7E` | Decode the model string and configure the detected disk. |
| `7F` | Identification failed. Other devices or boot targets can still work. |
| `80` | At least one BIOS hard disk was found. |
| `81` | Save identification status and task-file register values. |
| `82` | Selected-device probe reaches its return path. |
| `83` | Display the selected device's result. |
| `84` | Both primary-channel positions were probed; publish disk state next. |
| `85` | Primary-channel publication and IRQ handoff completed. |
| `86` | Reset the primary IDE channel before probing. |
| `B2` | An INT13 CHS disk read has an address/geometry error. This can occur after POST. |
| `B3` | An INT13 CHS disk read has an I/O error. This can occur after POST. |
| `CA` | Device/FPU initialization returned; the final Setup gate follows. |
| `E4` | No boot target succeeded. Wait for a fresh key to retry; this is not a hard halt. |
| `FF` | Final POST summary returned. Clock synchronization and bootstrap follow. Later boot/device codes can replace it. |

`71` through `83` can repeat for master and slave on each scanned channel. Use the port table to interpret values shared with another stage.

## Keyboard and mouse

| Code | Marker reached |
| --- | --- |
| `A5` | PS/2 mouse initialization starts. |
| `A6` | Mouse initialization succeeded. |
| `A7` | Mouse unavailable or initialization failed; boot can continue. |
| `B4` | Keyboard power-on settling, before disabling its interface. |
| `B5` | Keyboard interface disabled; disable the auxiliary interface next. |
| `B6` | Auxiliary interface disabled; drain controller output next. |
| `B7` | Begin the keyboard-controller output-port transaction. |
| `B8` | Output-port command accepted; write its value next. |
| `BA` | Output-port transaction completed. |
| `C0` / `C1` / `C2` | Controller checks begin / output drained / controller self-test passed. |
| `C3` / `C4` / `C5` | Command byte programmed / settling finished / keyboard reset starts. |
| `C6` / `C7` / `C9` | Reset acknowledged / keyboard self-test passed / keyboard interface enabled. |
| `C8` | Keyboard self-test response timed out; retry reset if attempts remain. |
| `D1` | Unexpected keyboard-reset reply while polling continues. |
| `D3` | A silent keyboard can be accepted after controller checks pass. An unexpected-reply stream can also halt with this code. |

`C9` can remain on the card while later settings or RAM work runs. It does not identify a RAM-test address.

## Stops and overlapping error codes

| Code and phase | Meaning |
| --- | --- |
| `A0`–`AF`, during an INT13 CHS read | Geometry trace. These values overlap mouse markers. |
| `B4`–`B8`, during keyboard initialization | The corresponding controller precondition failed; halted. |
| `D0`, during keyboard initialization | Keyboard requested resend; halted. |
| `D2`, during keyboard initialization | Keyboard self-test result did not arrive after retries; halted. |
| `D4`, during keyboard initialization | Keyboard self-test failed; halted. |
| `E5`, during video initialization | Video provider missing, malformed or rejected; halted. |
| `E7`, during keyboard initialization | Controller input timeout; halted. |
| `E7`, after RAM retry | RAM still failed with recovery/default settings; halted. |
| `E8`, during keyboard initialization | Controller self-test timed out; halted. |
| `E8`, during RAM/runtime operation | RAM parity stop. |
| `E9`, during keyboard initialization | Controller self-test returned a bad result; halted. |
| `EA`, during keyboard initialization | Controller command transaction failed; halted. |
| `EB`, during keyboard initialization | Keyboard reset command could not be written; halted. |


Sources: [shared POST shell](../shared/src/firmware/bios.asm), [boot selector](../shared/src/firmware/boot.inc), [keyboard controller](../shared/src/pc/keyboard-controller.inc), and [mouse](../shared/src/firmware/mouse.inc). These are bAIos meanings, not OEM, AMI, Award or MR BIOS code tables.
