# MP386 POST codes

All values are hexadecimal bytes written to I/O port `80h`. A code means that its marker was reached. It does not prove that the next operation finished. Codes are not in numeric execution order, and some values have different meanings in different phases.

These tables describe normal bAIos builds. Diagnostic ROMs can use additional codes. The pending shared-update Presario build adds the final `FF` marker and primary-channel `84`/`85`/`86` markers; older Presario images can omit them. A card display of `--` is not a bAIos code.

For disk discovery, mouse, keyboard and common stops, see [shared device codes](../../docs/post-codes.md). In particular, `85` means primary IDE initialization returned; it is not itself an IDE error.

| Code | MP386 marker reached |
| --- | --- |
| `10` | Reset entry and reset classification. |
| `11` | Enter the TI cold controller/memory initialization sequence. |
| `12` | TI cold controller/memory owner returned; legacy video/AT preparation follows. |
| `20` | Begin legacy video/AT-device preparation. |
| `21` | Early 8042 self-test/output-port sequence completed. |
| `22` | Enter the TI warm controller/map sequence. |
| `23` | Controller map returned; construct the stack, BIOS state and vectors. |
| `24` | Begin qualifying and copying the F000 BIOS shadow backing. |
| `25` | F000 shadow copy verified and staged; activation comes later. |
| `26` | Enter the Intel cache-controller SRAM qualification sequence. |
| `27` | Cache qualification passed; activation comes later. |
| `3C` | Begin checking the VGA option ROM at C000. |
| `3D` | VGA header/length accepted; verify the checksum. |
| `3E` | VGA checksum passed; call the VGA ROM next. A stop here means its return has not been reported. |
| `3F` | VGA ROM returned; restore bAIos stack/state next. |
| `40` | VGA mode-3 initialization returned. |
| `42` | VGA ROM stack/state restored; validate INT10 and set mode 3 next. |
| `70` / `80` / `84` / `85` / `86` | Shared IDE stages; see the shared table. |
| `CA` | Device/FPU work returned; final Setup/cache/shadow policy follows. |
| `E2` | Early 8042 initialization failed; halted. |
| `E3` | Cache data qualification failed; return with L2 unqualified/off. |
| `E4` | No successful boot target; fresh-key retry wait. |
| `E5` | VGA provider or returned INT10 rejected; halted. |
| `E7` / `E8` | Phase-specific keyboard, RAM-recovery or parity stop; see the shared table. |
| `FB` | Timing trial/recovery marker could not be saved and verified; halted. |
| `FF` | Final summary completed; bootstrap follows. |

`C9` can remain visible through the RAM test because this port does not emit a new code for each RAM block. An early memory/map failure can halt without a new marker. Cache-controller prerequisite checks can also stop before `26` without a new error marker. The accepted OEM-compatible upper-memory limit is not assigned a separate POST error code.

Sources: [startup](../src/hardware/startup-core.inc), [VGA](../src/hardware/video.inc), [shadow](../src/hardware/shadow.inc), [cache](../src/hardware/cache.inc), and [IDE](../src/hardware/ata-core.inc).
