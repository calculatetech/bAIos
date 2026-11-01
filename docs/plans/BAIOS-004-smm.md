# Shared SMM and CPU idle design

This developer specification owns the reusable service boundary. Board initialization, experiments, register recipes and validation records belong to port-local plans.

## Required behavior

Identify supported CPU capabilities through board adapters. Keep CPU evidence separate from motherboard permission. Preserve the original mobile processor identities and the existing name ABI.

Provide a bounded SMM installer and stackless Intel-compatible handler. Require valid bounds, protected destination ownership, fresh replies and qualified relocation before publishing readiness.

APM supports real-mode, protected16 and protected32 callers. Optional board idle providers own clock request, wake release and interrupt handoff. Shared code retains HLT when no provider is available. A disabled policy must perform no sleep.

Preserve caller registers, flags, segments, stack, cache data and interrupt ownership. Hardware qualification must follow real technical requirements. Missing physical test coverage alone does not justify a divider, revision or speed veto.

## Ownership and restrictions

The [processor interface reference](../development/processor-support.md) defines shared entry contracts. Hardware mapping, routing, SMRAM protection, reset and controller recipes stay in adapters. Existing cache initialization remains with its complete reference owner.

CPU naming does not enable a device or prove electrical support. Whole-system power states and device power management remain separate work. Do not add a generic controller interpreter, new Setup policy or runtime board registry for this service.

## Port implementation plans

The exact activation and clock-work boundaries remain in the [port implementation plan](../../m919/docs/plans/BAIOS-004-smm.md). The [port research report](../../m919/docs/research/stop-grant.md) owns register and signal evidence. Those records retain their boundary identifiers and source decisions.

The [user guide](../sl486-support.md) explains operation without validation details. Shared service changes require their applicable compiled-entry checks. Port physical results do not become claims about other hardware.
