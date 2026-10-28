# PB430 POST tracing

Quick lookup for normal images:

| Code | Next area to check |
| --- | --- |
| `10` / `20` | Reset classification / cold RAM initialization. |
| `12` / `1D` | Cache detection / cache data check. |
| `30` / `34` | BIOS state construction / system shadowing. |
| `50` / `3C` | VGA initialization / VGA provider selection. |
| `60` / `C9` | Keyboard initialization / keyboard enabled. |
| `7B` / `7C`, before IDE | Selected-timing RAM test begins / returned. |
| `70` / `84` / `85` | IDE probing / both slots probed / disk publication and IRQ handoff returned. |
| `CA` / `7F`, after IDE | Final Setup gate / late stock-cache parent. |
| `64` / `69` | L2 activation begins / controller returned to normal mode. |
| `FF` | Summary completed. Later `5D`/`5E`/`5F` mark clock sync and boot handoff. |
| `E4`, after `FF` | No successful boot target; fresh-key retry wait. |

The card shows the last marker reached, which can remain during the following work. For detailed ATA/ATAPI and keyboard stages, see [shared device codes](../../docs/post-codes.md). Other boards: [Presario](../../presario-800/docs/post-codes.md), [MP386](../../mp386/docs/post-codes.md), [M919](../../m919/docs/post-codes.md).


Codes are hexadecimal bytes written to port 80. The most recent code identifies the active operation. A following completion code proves that the preceding owner returned. RAM, cache and shadow details use the existing POST mechanism; the screen layout is unchanged. A stopped machine needs the last code and its preceding sequence because shared device codes can overlap board codes in other phases.

| Code | Meaning |
| --- | --- |
| 10 | Normal reset classified; cold or warm work follows |
| 05 / 0A without 10 | CMOS shutdown service resume selected; normal POST is bypassed |
| 11 | Ordinary warm path; stock9631 teardown/fill runs before retained state is copied |
| 1B | Earlier warm teardown returned and the retained BIOS-state address is valid |
| 20 | Cold memory initializer begins |
| 27 / 2B | Bank 0 probe begins / completes |
| 28 / 2C | Bank 1 probe begins / completes |
| 29 / 2D | Bank 2 probe begins / completes |
| 2A / 2E | Bank 3 probe begins / completes |
| 2F / 31 / 32 in interleave image | Early mode transition / map readback accepted / full address-pattern check passed |
| E2 / E3 before 21 in interleave image | Page-mode bit stayed set / unsupported bank layout |
| E4 / E5 / E6 before 21 in interleave image | Register00 map rejected / register12 geometry rejected / failed memory validation |
| 7A / 7B / 7C in cache-burst image | Stock pattern ready / burst readback accepted / L1 enabled and read verification begins |
| 7D / 7E in cache-burst image | Both patterns passed / experiment skipped by cache policy or RAM size |
| E9 / EC / ED / EF in cache-burst image | Burst clear failed / enable rejected / cached read failed / unexpected starting state |
| 21 | Supported map and routing written |
| 22 | Protected alias-aware count begins |
| 23 | Conventional 640 KiB span responded |
| 26 | First extended 64 KiB clear completed; omitted at 1 MiB |
| 24 | Physical count complete: absent/aliased span or the 64 MiB limit |
| 25 | Low workspace and actual first-stack region passed |
| 30 | EBDA, BDA and public vectors constructed |
| 12 | SRAM presence probe begins |
| 1F | SRAM probe and saved RAM restored; unambiguous size qualified |
| 16 | SRAM probe and saved RAM restored; size unknown, L2 remains off |
| 1D | Short SRAM check begins; temporary mode has not been entered |
| 1E / 1A | Short SRAM check passed / failed; normal controller mode restored |
| 34 | Initial system-shadow owner begins |
| 35 | Full system image staged; map changes execute at 3000 |
| 36 | New system mapping copied; executing F000 again |
| 37 | System shadow protected or already mapped |
| 40 | Initial system-shadow owner returned; PIC/PIT begins |
| 41 | PIC/PIT returned; RTC begins |
| 42 | RTC returned; SIO baseline begins |
| 43 | SIO baseline returned; AT prerequisites begin |
| B0 / B1 / B9 | Later refresh/DMA setup begins / completed; AT prerequisites completed. Initial refresh already precedes RAM work |
| 50 | Video initialization begins |
| 3C | Video-provider selection begins |
| 3D / 3E | Video image staged / selected C000 mapping copied |
| 3F | Full C000 header and checksum passed |
| 60 | Video owner returned; keyboard initialization begins |
| B4 / B5 / B6 | Keyboard settle / keyboard interface disabled / auxiliary interface disabled and drain begins |
| C0 / C1 / C2 | Keyboard-controller checks / drain completed / self-test passed |
| B7 / B8 / BA | Output-port command / write / completion |
| C3 / C4 / C5 | Command byte programmed / settle completed / keyboard reset begins |
| C6 / C7 / C9 | Reset acknowledged / basic-assurance test passed / keyboard enabled |
| D3 | Keyboard silent after bounded reset polling; controller remains usable |
| 48 / 49 | Keyboard reset owner returned / IRQ1 service armed |
| 51 | Existing POST presentation started |
| D0 / D1 / D2 after 51 | Settings loaded / NumLock policy returned / keyboard-presence policy returned |
| D3 / D4 after 51 | Chipset policy entered / retained L2 disabled before shadow policy |
| 38 / 39 / 3A | Saved system-shadow policy begins / staged transition / F000 continuation |
| 52 | Saved chipset policy applied; L2 still off |
| DA / DB after 3A | Additional shadow windows begin / copy and protection complete |
| DC after DA | Additional shadow mapping, copy or protection failed |
| 70 | Primary ATA/ATAPI discovery begins |
| 86 / 84 / 85 | Primary channel reset / both device slots probed / public disk state and IRQ handoff complete |
| 80 | At least one BIOS hard disk found |
| CA | Device/FPU initialization returned; final Setup gate follows |
| 53 / 54 | Cache body begins / body completed; parent CMOS B4 and C7/20 still follow |
| 64 | Qualified L2 activation begins |
| 69 | Transient mode cleared and effective L2 state published |
| 56 | Stock cache sequence, saved timing policy and visible RAM test returned; success tone follows |
| D6 / D7 during timing application | RAS timeout policy begins / readback accepted |
| D9 after D6 | RAS timeout readback failed; stock value restored |
| 76 / 79 / 7A / 77 in normal image | Timing cookie accepted / CAS advance accepted / other fields accepted / final CAS timing accepted |
| 78 during timing application | Advanced timing skipped: unsupported jumper, L1 off, unqualified cache or unexpected stock state |
| 7B / 7C | Early RAM test with selected timings and both caches off begins / returned (including an Esc skip) |
| 7F | Final Setup gate returned; restore stock timings and run the late stock cache parent |
| F0 before 76 | Timing recovery marker could not be set |
| F1 / F2 / F3 / F4 during timing restoration | Register 0B / 16 / 18 / 19 failed to restore |
| F5 / F6 / F7 / F8 during timing restoration | Register 12 / 14 / 04 / 05 failed to restore |
| F9 / FA during timing restoration | RAS timeout failed to restore / recovery marker could not be cleared |
| FB | Pending-trial or safe-recovery CMOS state could not be written and verified |
| 7D / 7E after timing application | Optional cache burst-write / CAS-before-RAS refresh write begins |
| FC / FD during timing restoration | Original cache burst-write / CAS-before-RAS refresh bits failed to restore |
| EB after timing application | Timing readback failed; stock restoration completed before stopping |
| 5B / 5C | Final summary entered / returned |
| FF | Final summary completed; clock sync and bootstrap follow |
| 5D / 5E / 5F | Clock synchronization returned / INT19 requested / native INT19 entered |
| 90 | Controlled reset begins; changed saved L1/L2 choices select cold initialization |
| 91 / 92 / 93 | Controller C7/20 returned / cache teardown and shadow/NMI preparation returned / reset pulse follows |
| D5 | Reference controller transaction timed out |
| E1 | Conventional/low memory failed before first firmware stack |
| E5 | Missing, malformed or bad-checksum video provider |
| EA after bank completions | Unsupported mode-1 bank pattern; no guessed map |
| E4 after FF | No boot target succeeded; existing fresh-key retry wait |
| EE | Warm-reset controller transaction failed |
| FE in normal timing restoration | Jumper-selected ISA divider readback failed |

Keyboard failures keep the shared owner: D0 resend, D2 missing basic-assurance result, D4 failed basic-assurance result, EB reset write failure, E7 controller input timeout, E8 self-test timeout, E9 bad controller self-test, EA command transaction failure. B4-B8 can also identify their own failed preconditions. Later RAM E7 is a failed test at defaults; E8 after RAM parity output is a parity stop. Use the preceding phase to distinguish them.

Earlier trace images emitted the live register04 byte before fill. That byte could be `FF`, before the summary. Later stock-parent and stock-map images emitted constant `66` there. The stock-transition candidate removes all four added writes65-68 from temporary tag mode. Original stock and the previously booting013BEE00 image contain none. Current64 precedes the uninterrupted transition and69 follows normal-mode restoration. A stop64 now identifies that whole transition, not an individual fill instruction. Interpret historical66 reports using their image identity.

The cold SRAM probe also runs without added diagnostic I/O in temporary mode. Codes13/14/17/18/19 from earlier images are retired. Code12 precedes the probe;16 or1F reports its result only after normal mode and saved RAM are restored.

Floppy diagnostics retain the read-only FDC stage, status, IRQ count and controller results. `FLOPPY_DIAGNOSTIC` displays these through the existing diagnostic owner. `KEYBOARD_DIAGNOSTIC` and `MOUSE_DIAGNOSTIC` use their existing output. They do not add another presentation system. The normal build retains all port-80 stages.

The test adapter checks the cold bank/count sequence, warm owner sequence, silent-keyboard continuation, failed keyboard basic-assurance branch, each cache candidate and the final cache/boot boundary. Native diagnostic builds also execute the real callbacks. Test-only `PB430_TRACE_STAGE` and `PB430_TRACE_FAILURE` can terminate at a selected board stage through the existing 86Box Unit Tester protocol; these definitions are absent from the normal image.
