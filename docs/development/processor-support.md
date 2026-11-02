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

## CPU performance candidates

CPU recognition does not enable performance controls. Add these through board adapters, with shared code for the exact CPU profile and register access. Preserve unrelated bits, restore temporary register mappings, and coordinate changes with cache, DMA, SMM and reset owners.

For Cyrix/IBM indexed registers, select the index at port22h before each individual port23h read or write. A read-modify-write operation needs two index selections. The guides state that later port23h transfers without a new selection go to the external bus.

| CPU family | Useful controls to investigate | Required distinction |
| --- | --- | --- |
| Cyrix 5x86 and IBM 5x86C | Memory bypass (`MEM_BYP`), directory-entry cache (`DTE_EN`), I/O recovery (`IORT`), branch prediction (`BTB_EN`), return stack (`RSTK_EN`) and loop handling (`LOOP_EN`). | Read device, stepping and revision information. The manufacturers' compatibility tables restrict speculative features. A register definition is not approval to enable it on every revision. |
| Cyrix 5x86 and IBM 5x86C bus interface | Linear bursts (`LINBRST`), burst write-back (`BWRT`), load/store reordering (`LSSER`) and the L1 write-back interface. | Match the chipset's burst order, memory-mapped device ordering and snoop protocol. Program the CPU and controller as one transaction. |
| AMD Am5x86 and write-back Intel 486 parts | Correct L1 write-back operation, memory cacheability and coherent external-master access. | CPU pins, reset selection and chipset protocol determine availability. Do not reuse the Cyrix interpretation of CR0.NW or force WB from a family-four identity alone. |
| Intel Pentium OverDrive for 486 systems | Correct cache/burst protocol and the supported write-back interface. | Socket write-back support is optional. Its Pentium execution features do not imply a universal firmware performance switch. |

Start with the documented Cyrix/IBM memory-bypass and directory-entry-cache controls, then coordinate I/O recovery with the board. Treat branch, return-stack, loop and fast-FPU options separately for each documented revision. The IBM guide defines `FP_FAST`, while the cited Cyrix guide marks that CCR4 bit reserved; do not copy a shared register mask between them without a matching reference.

Primary references are the [Cyrix 5x86 BIOS Writer's Guide, revision1.12](https://bitsavers.org/components/cyrix/94246-00_5x86_CPU_BIOS_Writers_Guide_199510.pdf), the [IBM 5x86C BIOS Writer's Guide, September1995](https://datasheets.chipdb.org/IBM/x86/5x86/40038.PDF), [AMD19751C, sections2 and4](https://datasheets.chipdb.org/AMD/486_5x86/19751C.pdf), and the [Intel Pentium OverDrive datasheet290544-001](https://www.ardent-tool.com/CPU/docs/Intel/Pentium/290544-001.pdf). These are manufacturer documents held by archives. Obtain the matching revision errata before selecting defaults for the restricted features.
