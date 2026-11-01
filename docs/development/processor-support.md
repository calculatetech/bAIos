# Processor and APM interfaces

This is a developer reference. User instructions are in the [SL-enhanced processor guide](../sl486-support.md). Hardware initialization, clock recipes and diagnostic results belong to individual ports.

## Identification

`shared/src/pc/cpu.inc` owns guarded CPU recognition. A writable EFLAGS.ID, complete vendor string and available CPUID leaf precede signature interpretation. The name API returns CS:SI and preserves other registers and EFLAGS. Unknown observations remain unknown. A CPU identity does not establish motherboard wiring.

`board_cpu_detect_name` owns presentation. `board_cpu_sl_query` returns CPU profile evidence in AX and available board functions in DX. AX0 means unknown, AX1 identifies a supported Intel desktop SL candidate, and AX2 identifies a compatible Am5x86 candidate. DX bit0 records successful board SMM readiness. A board adapter must not derive readiness from the CPU name alone.

The original mobile 486SL remains distinct. Desktop qualification requires documented vendor, type, family and model observations. It does not use a universal family-four enable rule.

## SMM services

`board_smm_prepare` owns hardware qualification and calls the shared bounded installer. The board owns SMRAM mapping, reservation, protection, first-fetch coherency, reset interlocks and source activation. Installation alone authorizes none of those hardware operations.

`smm_install` accepts profiles1/2, DI8000h, length2..7E00h, and a source that does not wrap the segment. It checks bounds before writing, copies forward, verifies bytes and preserves caller state except AX/CF. AX0 means success,1 unavailable,2 invalid bounds and3 verification failure.

The installed handler is stackless. It changes only documented writable save-state fields and returns with RSM. A board acknowledgment macro identifies the source. Software commands require the request cookie and fresh reply. Relocation needs a prepared, protected target and the supported revision bit. Port documents own the actual addresses and controller sequence.

## APM idle

`shared/src/firmware/apm.inc` owns the real-mode, protected16 and protected32 APM entries. Board-selected code segments, state loaders and data lengths must match the descriptors returned by the connection service.

Paired `board_stop_grant_query` and `board_stop_grant_idle` macros are optional. They must support both assembly operand sizes. The query reports available hardware. The entry owns request, wake release and interrupt handoff. Shared code preserves the caller and falls back to HLT after a pre-entry decline.

Disabled APM Idle performs no hardware query or sleep. Installation reports policy and hardware capability separately. Clock slowing is advertised only when the board provider is available. The real-mode entry under a virtual memory manager defaults to the monitor's halt path. An adapter can define `BOARD_STOP_GRANT_V86` only when its idle caller needs no privileged cache or control-register instruction. Such an adapter owns first-fetch coherency and any privileged work inside SMM.

A successful hardware path restores the required run state before interrupt delivery and preserves the pending wake. A decline must leave no clock request asserted or wake consumed. A PCI divider is preserved rather than used as a test-coverage gate.

Whole-system standby, device power management and literal external-clock removal need separate implementations. Hardware observations and detailed validation remain in the relevant port's developer documentation.
