# Presario 800 POST codes

All values are hexadecimal bytes written to I/O port `80h`. A code means that its marker was reached. It does not prove that the next operation finished. Codes are not in numeric execution order, and some values have different meanings in different phases.

These tables describe normal bAIos builds. Diagnostic ROMs can use additional codes. The pending shared-update Presario build adds the final `FF` marker and primary-channel `84`/`85`/`86` markers; older Presario images can omit them. A card display of `--` is not a bAIos code.

For `70`–`86`, `A5`–`A7`, `B2`/`B3`, keyboard codes and their error meanings, see [shared device codes](../../docs/post-codes.md). The same number can mean something different on another board.

| Code | Presario marker reached |
| --- | --- |
| `10` | Reset entry. |
| `11` | Ordinary warm reset recognized. |
| `12` | Begin direct external-SRAM presence check. |
| `13` | Begin SRAM capacity, independence and data checks. |
| `14` | SRAM check failed; leave L2 disabled and continue. |
| `15` | L2 initialized in normal cache mode. |
| `16` | SRAM absent or unresponsive; leave L2 disabled and continue. |
| `20` | Begin the early low-memory test before a RAM-backed stack is trusted. |
| `21` | Begin onboard-bank geometry/interleave detection. |
| `22` / `23` | Onboard bank accepted as single-sided / double-sided. |
| `24` | Reuse the retained warm memory map. |
| `25` / `26` / `27` | Bank 1 probe begins / accepted / absent or aliased. |
| `28` / `29` / `2A` | Bank 2 probe begins / accepted / absent or aliased. |
| `28`, after memory initialization | Begin system-BIOS shadowing. |
| `2B` / `2C` / `2D` | Bank 3 probe begins / accepted / absent or aliased. |
| `2E` | A candidate bank would exceed the controller's 64 MiB limit; omit that bank. |
| `30` | Early low RAM is usable; rebuild the stack, BIOS state and memory map. |
| `40` | Begin interrupt-vector and PIC/PIT initialization. |
| `48` | Keyboard initialization returned; arm normal keyboard service. |
| `50` | Begin VGA initialization. |
| `60` | VGA ROM returned; mode 3, monitor setup and keyboard initialization follow. |
| `90` | Controlled reset entry. |
| `91` | Keyboard handoff and shadow removal completed; enter software warm restart. |
| `94` | Enter the software warm-restart path while retaining the memory map. |
| `B0` / `B1` / `B9` | Begin DMA/refresh prerequisites / DMA reset completed / prerequisites returned. |
| `CA` | Final device/FPU work returned; final Setup and late cache work follow. |
| `E0` | System-BIOS shadow verification failed; halted. |
| `E1` | Early low-memory test failed; halted before trusting the first stack. |
| `E4` | No successful boot target; fresh-key retry wait. |
| `E7` / `E8` | See the phase-specific keyboard, RAM, cache-recovery and parity stops in the shared table. |
| `FF` | Summary completed in the shared-update candidate; bootstrap follows. |

The normal cold and warm paths differ. Bank/cache codes can repeat or be skipped. `28` is deliberately reused for a bank probe and BIOS shadowing; use its preceding sequence.

Sources: [startup/reset/cache](../src/bios.asm), [memory](../src/memory.inc), and [late cache/recovery policy](../src/chipsets/vl82c481/policy.inc).
