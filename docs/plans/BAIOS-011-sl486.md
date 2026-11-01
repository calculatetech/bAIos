# SL-enhanced CPU identification design

This developer specification describes the shared identification boundary. Board readiness and hardware programming belong to adapters. User instructions are in the [SL-enhanced processor guide](../sl486-support.md).

## Identification contract

Use the guarded observations in `shared/src/pc/cpu.inc`. Require a writable EFLAGS.ID, a complete recognized vendor string and an available signature leaf before interpreting CPUID.

The board-facing query returns CPU evidence in AX. Zero means unknown. Profile1 identifies a documented Intel desktop SL candidate. Profile2 identifies a compatible Am5x86 candidate. Preserve upper EAX, all other registers and EFLAGS in the shared query.

An adapter returns hardware readiness independently in DX. CPU identification cannot establish motherboard wiring or enable a controller. Unknown hardware readiness remains zero. Generic firmware must not bypass the adapter to invoke private qualification helpers.

## Names and compatibility

Keep the CS:SI name contract. Preserve caller state while selecting a name. The board presentation adapter can append SL identification without changing the shared catalogue for unrelated ports.

Keep the original mobile 486SL separate from desktop SL Technology. Unknown vendors, unavailable signatures and undocumented models stay unknown. Reserved feature bits or a retained reset signature must not manufacture a positive result.

Without CPUID, retain the established legacy identification path. Do not introduce configuration-port writes or 486-only operations on a 386 processor.

## Related services

Identification is separate from SMM installation and CPU idle. The [SMM design](BAIOS-004-smm.md) and [processor interface reference](../development/processor-support.md) describe those services. Port implementation records own code-placement constraints and physical observations.
