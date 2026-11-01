# Shared PIO0 through PIO4 design

This developer specification owns the common ATA mode service. Controller recipes and their validation records belong to each port.

## Capability and policy

Support PIO0 through PIO4. Auto chooses the fastest mode allowed by drive capability, the port ceiling and the saved request. A separate controller or missing timing registers does not by itself establish a lower supported ceiling.

Use valid IDENTIFY capability and cycle-time fields. Advanced modes require the advertised IORDY capability. The generic host retains existing strobes and requires a controller that honors IORDY. Device acceptance alone does not prove this electrical property.

## Completion and reset

Wait for accepted SET FEATURES completion before accelerating host timing or publishing the effective mode. Previous-command ERR does not reject a new command. ERR from SET FEATURES itself does reject it. Unresolved BSY or DRQ blocks replacement commands until recovery.

Restore both peers on the affected channel after reset. Preserve the other channel. Keep identity and physical position stable across missing or disabled devices. Setup must not probe devices to choose which saved record to edit.

## Ownership

`shared/src/firmware/ide-pio.inc` owns negotiation. Shared status, reset, inventory, transfer and rendering owners compose with it. A port sets its ceiling and supplies qualified timing operations where required. Preserve peer bits during every timing write.

PIO mode, block mode and16/32-bit transfer width are separate policies. Display the effective accepted PIO mode. Preserve older saved records and reject invalid stored encodings without shifting unrelated fields.

The [controller implementation plan](../../m919/docs/plans/BAIOS-010-pio.md) retains exact controller fields, source evidence and boundary identifiers. Other port details belong in their developer records. Software availability and physical timing margins remain separate facts.
