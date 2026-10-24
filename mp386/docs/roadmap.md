# Mitsubishi MP386/25 roadmap

This roadmap owns MP386 port work. The root roadmap owns shared repository work. Task identifiers are permanent.

## Active

No task is active.

## Planned next

No task is planned next.

## Planned later

No task is planned later.

## Accepted residual risk

- **MP386-002: Accept the OEM memory boundary and benchmark quirks.** With 18 MiB installed, retain the contiguous 15,232 KiB extended-memory limit. The OEM also reports 15,872 KiB including its 640 KiB base count and mirrors ROM below 16 MiB. Do not recover the last 2 MiB. The OEM CACHECHK run repeatedly checks below 1 MiB; the working bAIos behavior is accepted. Revisit these limits when the TACT83000 user's guide becomes available. Accepted by the user on 2026-10-23.

## Declined

No task is declined.

## Completed

- **MP386-003: Correct legacy IDE initialization and DOS A20 handoff.** Initialize Auto CHS disks at detection and after channel reset through the shared owner. Keep Presario's duplicate aligned. Release the Mitsubishi A20 override before boot so HIMEM can control the keyboard-controller gate. Keep both fixes covered by cold/warm boot checks and verify the other ports' shared paths.

- **MP386-001: Integrate the working port with shared bAIos POST and Setup.** Use the standard RAM test, cache lifecycle, fixed cache size, boot controls and Fast Boot. Keep the Mitsubishi memory map and complete cache sequence. Provide the switch guide, decoded timing controls and logical hardware groups. Recover unconfirmed timings without treating interrupted POST as a RAM failure. Keep empty-bank categories navigable. Retain the accepted memory boundary. Deliver combined and split programmer images. [Specification](plans/MP386-001-port.md).
