# M919 POST codes

All values are hexadecimal bytes written to I/O port `80h`. A code means that its marker was reached. It does not prove that the next operation finished. Codes are not in numeric execution order, and some values have different meanings in different phases.

These tables describe normal bAIos builds. Diagnostic ROMs can use additional codes. The pending shared-update Presario build adds the final `FF` marker and primary-channel `84`/`85`/`86` markers; older Presario images can omit them. A card display of `--` is not a bAIos code.

For disk discovery, mouse, keyboard and common stops, see [shared device codes](../../docs/post-codes.md). These are bAIos codes, not the original AMI table.

| Code | M919 marker reached |
| --- | --- |
| `10` | Normal reset path selected; initialize chipset and memory next. |
| `20` | Chipset baseline/refresh preparation reached; enter flat addressing and DRAM geometry discovery. |
| `24` | Begin ordinary L2 qualification after RAM checks, when required. |
| `70` | Begin disk discovery across the primary and secondary channels. |
| `71`–`83` | Shared ATA/ATAPI selected-device stages. |
| `80` | At least one BIOS hard disk found. |
| `B4`–`C9` | Keyboard-controller/device stages; see the shared table. |
| `CA` | Device/FPU work returned; final Setup and late cache activation follow. |
| `E2` | No supported DRAM geometry/map found; halted before normal BIOS state exists. |
| `E3` | Early physical-memory data check failed; halted. |
| `E4` | No successful boot target; fresh-key retry wait. |
| `E5` | Video initialization failed; halted. |
| `E7` | Keyboard timeout or a repeated RAM failure at recovery settings; distinguish by phase/screen. |
| `E8` | Keyboard self-test timeout or RAM parity stop; distinguish by phase/screen. |
| `FF` | Final summary completed; bootstrap follows. |

There are few early markers. `20` can remain displayed while geometry probing, cache discovery, PCI or VGA initialization runs. `C9` can remain through the visible RAM test. A stop at one of these values does not isolate a single component. This port does not emit the primary-channel `84`/`85`/`86` markers. The configured board has no auxiliary mouse port and emits no `A5`/`A6`/`A7` mouse markers. Older builds that omitted the post-RAM cache callback can omit `24`.

A failed L2 qualification uses the existing recovery/restart path. Use its screen message as well as the last code. A CMOS shutdown-service continuation bypasses ordinary POST and can leave an old card value visible.

Sources: [startup](../src/hardware/startup-core.inc), [memory](../src/hardware/memory.inc), and [cache/recovery policy](../src/hardware/chipset-core.inc).
