> Developer reference. Board implementation, research and validation details belong here.

# Stop Grant and board clock-control evidence

## Question

Which retained board sequence can enter architectural Stop Grant and resume correctly, while keeping the external CPU clock running?

Stop Grant stops the CPU's internal clocks after STPCLK is asserted and the CPU's special bus cycle is acknowledged. Full Stop Clock also stops the external CLK input. Auto Halt is a third path, entered by HLT on CPUs that implement it. A clock-divider setting or a firmware label alone cannot distinguish these states.

## Repository constraints

Hardware operations belong in board adapters. CPU identity, controller identity and wiring are separate facts. Preserve the existing cache, RAM, reset and IRQ owners. Do not initialize PS/2 on M919. Do not assume an installed CPU, bus frequency, cache size or original clock-divider value.

M919 SMM activation is a separate completed software checkpoint. Its 0.12.0 bench image remains unchanged by this research and still needs physical testing. Shared APM has real-mode, protected 16-bit and protected 32-bit entry points. A board idle provider must complete request, acknowledgment, wake release and return through each supported entry.

The user requires all available research avenues to be pursued before a feature is put on hold. A partial ROM search is not evidence that a controller lacks the feature. Device power management remains separate from CPU Stop Grant.

## Options

| Path | Established behavior | Requirement before board activation |
| --- | --- | --- |
| Architectural Stop Grant | STPCLK request, acknowledged special bus cycle, internal clocks stopped; external CLK continues. | Identify the complete board request and wake sequence. |
| Full Stop Clock | External CLK stops after Stop Grant. | Additional clock restart and stabilization rules; do not label this fast Stop Grant. |
| Auto Halt | The CPU enters its documented halt power state after HLT. | CPU-specific capability. It does not establish motherboard STPCLK wiring. |
| Clock division | Clock frequency changes under chipset control. | Preserve the actual normal policy and distinguish it from clock stopping. |

The existing HLT path remains usable during investigation. It does not close the separate Stop Grant work.

## Evidence

### Retained source inventory

The UMC input set has 33 distinct image hashes: four original M919 images and 29 comparison images. There are no duplicate input hashes in that set. The comparison inventory's two old `Unknown` classifications resolve to the older AMI `UD 486 GRN.rom` and a modern coreboot/SeaBIOS replacement.

| Source family | Unique inputs | Relevant scope |
| --- | ---: | --- |
| AMI | 7 | Actual APM idle/busy, relocated SMM dispatch, CPU gates, clock requests and normal-state restoration. |
| Award | 21 | Actual APM consumers, timer/APM handshake, clock-selection tables, SMM state owners and wake configuration. |
| Phoenix | 4 | Actual APM consumers, decoded runtime images and distinct clock/wake owners. |
| Modern replacement | 1 | Supplied binary plus the identified source dependencies and local patches; source identity is recorded separately from binary identity. |

Originals, decoded images and complete listings remain outside Git. The ignored research inventory records full input and reference-source hashes. A linear listing proves byte coverage, not execution. The findings below follow actual callers, tables and state producers.

### CPU contract and missing pin data

Intel 241731-002 sections 9.3.4 and 9.6 define the handshake. STPCLK must remain asserted through the Stop Grant bus acknowledgment. An interrupt alone does not deassert that pin. The CPU must receive an active-high release. The special cycle uses address 10h and byte enables 1011; hardware returns RDY or BRDY. Full Stop Clock adds restart requirements that do not apply to Stop Grant with CLK running.

AMD 19751 revision C sections 5.2 through 5.5 describe the Am5x86 equivalents. Its Auto Halt path already supplies a separate internal power-down state. Do not assume every Intel clock-multiplied implementation has the same HLT power behavior.

The pinned UMC documentation project contains a useful input that was absent from the earlier local census: `doc/um8886bf_pinout.ods`. Its pin 33 row identifies the STCK/CYRIXSUSP output and connects it to the 486 G15 STPCLK input. Pin 51 is the separate HCLKO output. This establishes a physical stop-clock interface in the documented design. It does not identify every register that drives it, nor prove every M919 revision's net routing.

### AMI: idle and deeper power states have different owners

All seven AMI CPU-idle paths terminate at HLT or a protected-interface/no-pending-work return. Their Busy paths add no clock request. This is a bounded conclusion about those consumers, not the whole power-management implementation.

May M919 core `9190506.BIN` is the canonical example. Its decoded core SHA-256 is `3311121e2f9d251d121c84213a9d2478163921110691b0398690ee7e24a1f690`. Public idle follows C547/C559/C5D4 to the board halt owner C678. The relocated SMM idle path instead dispatches through original offsets 3B5F/3BAB/3CEB and command table 4950. Its board commands query pending PIC interrupts or return; they do not program a clock.

The separate SMM state dispatcher has real doze, standby, suspend and restore owners at 436A, 43BE, 443F and 44CC. Helpers 458B through 45B1 select ISA clock policy, update A4 with a selected state byte and pulse A4.10. Normal-state restoration restores the saved policy. These states also use event masks, timers and peripheral owners.

The complete M919 cause/acknowledgment/state/clock/wake-helper block is byte-identical across all four original M919 cores after rebasing. Its hash is `aaeaf66041becc8c7d63a951adc13713bad24ae858e507e7a40b1be773ef6a5d`. This justifies reuse of that trace; it does not make the other AMI boards identical.

The A1.20 branch is CPU- and interface-dependent. CMOS33.04 is derived from the inverse of CPU-descriptor flag 80h. Named Intel SL and Am5x86 records set that descriptor flag, while older DX/SX/DX2 records do not. Standard SL/Am5x86 states use the A4 clock owner; the alternative A1 branch cannot simply be renamed the Intel Stop Grant request.

The other three AMI clock families differ in meaningful ways. `03C8881I` uses a different ISA-clock mask and an additional port-90h write. `am8887` and `UD 486 GRN` use board-specific C04h outputs and explicitly clear A1 during normal restoration. UD restores complete saved wake masks; the later M919 family applies filtered masks. `am8887` also has an Intel-specific standby exception for measured 75/100 MHz frequency buckets. Those buckets come from the frequency producer and display table; they are not inferred multipliers. These differences prevent treating one clock tuple as a universal UMC sequence.

One earlier interpretation was wrong: chipset SMM interface value 30h is selected for legacy **UMC** CPUs in these AMI producers, not for AMD merely because an older register note calls it classic AMD. The decoded vendor selectors are Intel=0, Cyrix=1, AMD=2 and UMC=5. May M919 selects interface 00h for AMD and for newer UMC records. Am5x86's documented Intel-compatible format remains the basis for the current adapter.

### Award: register 76h is part of a two-stage protocol

Twenty of the 21 actual Award idle consumers use the register-76h request pattern; `12234IM.BIN` has board idle/busy stubs. The canonical `095051.BIN` decoded core hash is `c2ec138f5a9eb0c72a78adb71c2e7ebbdc8b4bfd06410114db5a3ee628ed9549`.

Its APM idle entry 84F5 invokes helper 8D10 only after a private eligibility flag is set. The helper also checks the saved PM Control By APM choice, ORs 02h into southbridge register 76h and delays. Interrupts are disabled during this request. Busy 8523 is a return stub.

The eligibility producer is the SMM doze-event owner 8E18, selected by A2.02. On the first eligible timer event it asks the connected APM driver for an idle opportunity and returns without changing the clock. The later CPU Idle request sets 76.02; the event owner can then perform the clock transition. Common SMM cleanup 8DF5 clears 76.06, acknowledges the source and restores context. Full-on owner 8F4E restores saved A4 and ISA register 56h.

Therefore 76.02 is a software doze request in this implementation. It is not evidence of a direct STPCLK latch. Setting it without the eligibility, event, clock and wake owners would omit required behavior.

The same family provides an explicit Inactive Mode choice between 1/8 HCLK and STOP CLK. Setup record 6700, normalized CMOS5C.04 and table 8A84 select state byte 93h or 13h. The hardware owner applies its masked A4 recipe; wake uses the saved normal value. This identifies the command-selection meaning. It does not establish whether external CLK continues while that state is active.

Some Award variants use A1.20 when the saved IRQ-versus-SMI/interface policy selects an alternate power-management route. The native SMI path uses the A4 owner. OR-only writes do not prove that A1 clears itself or that every IRQ releases the clock request.

MGV994 has a distinct wake path: it temporarily enables the register-91h IRQ8 wake input, unmasks PIC IRQ8 and enables the RTC alarm interrupt around its clock request. RTC B bit 20h enables alarms, not periodic interrupts. This corrects the earlier research label. The sequence needs an alarm producer before it can supply a scheduled wake. It is not a complete safe transplant: the closed routine does not save and restore RTC B correctly, acknowledge RTC C or restore NMI policy. Any adaptation must account for the alarm inputs and existing RTC/PIC ownership.

`DWT4505B` supplies a stronger restoration sequence at F8FE3..F90B5. It saves register 91h and RTC B, enables IRQ8 wake and the alarm interrupt, applies the selected inactive clock byte, then restores RTC B, flags, the PIC mask, wake mask, A4 and ISA56. It acknowledges RTC C. Its input hash is `c6af022d7d49b5fda17b02b66e7f08b6cb3ab36ac3727ac9cea0be492916591c`; decoded main hash is `041dcf6ad7f35b95fe908d92af0c07a39e1b3137ea0f8028db1a18446f46ad83`. This range does not program RTC alarm registers 1/3/5. A useful adaptation needs a controlled wake source, PIC cascade availability, existing RTC-event ownership and NMI/index restoration. A loop after a clock request cannot act as a timeout while the CPU cannot execute.

The direct alarm producer at F8C6C..F8CA5 reads the WakeUp during Suspend choice from CMOS4F.01. It loads the user's hour, minute and second fields, converts them to BCD, and writes alarm registers 5/1/3. The default is midnight. The temporary path's index CFh selects CMOS4F with NMI masked. It does not select an extended CMOS byte. This is an absolute daily alarm, not a short deadline. MGV994's F921B..F9248 producer likewise loads a configured Inactive Wake-Up Time. Neither sequence supplies a controlled periodic wake.

All 21 Award clock owners were classified, not just their idle consumers. Distinct alternate owners use A1, C04h, register 80h or register 57h. Twenty common cleanup owners clear 76.06; MGV994 clears 76.03. `uud0520s` is an important counterexample: its normal clock helper overwrites the requested byte with the old A4 value, pulses the clock control and restores that original value. Its visible STOP CLK choice therefore does not prove that this path applies the selected state.

### Phoenix: two different controller interfaces

The PCI clock owners in `8810AIO` and `4v-04` use A4 state recipes, saved normal A4/ISA56 and the register-91h IRQ8 wake field. Their doze recipes differ: 8810 uses a selected 14h field, while 4v uses 05h. The 4v image also has an interface-dependent C04h owner. Neither idle consumer directly requests 76.02.

The two `4105` images instead reach indexed-port 22h/24h power owners that set E1.08 and conditionally E0.40. Their bounded request bodies are byte-identical, hash `ffe74c90fcd2d556be377b9399966df14548e5a85c3a97e344df17cd9601c2ca`. The unresolved hardware identity prevents assigning these fields to the PCI UM888x interface. Membership in the comparison directory is not chipset qualification.

### Other maintained ports

| Port | Actual retained firmware evidence | Remaining hardware question |
| --- | --- | --- |
| Presario 800 | Three genuine Compaq images dispatch 5305 to HLT and 5306 to session validation. CPQPOWER calls those services and adds no chipset sequence. | Standby 5307 writes private C5F/C5B/CD4 ports. Their external ASIC/PAL effects and CPU pin routing are not established. |
| PB430 | Factory and ACC386 comparison INT15 handlers reject AH=53. The ACC2168 guide and its archive add no CPU stop-clock programming contract. | No retained schematic or hardware selector connects an SL CPU's STPCLK to an identified control owner. |
| MP386 | Native 386DX and its OEM reject the APM request; no identified upgrade adapter supplies the additional interface. | An upgrade adapter needs its own CPU and electrical contract. Similar-board firmware is not pin-routing evidence. |

The complete VL82C481 CPU interface and register documentation has clock division controls, but no native STPCLK interface. That does not rule out an external Compaq implementation. The private standby transactions are retained as a concrete lead. The ACC2168 archive's single manual member supplies no additional hidden programmer guide.

### Reference implementations and unrelated inputs

The retained 86Box UM8886 implementation stores registers 76h, 90h/91h and A1h without implementing their clock or wake effects. It does implement software SMI through A3. Passing that model cannot establish Stop Grant.

The modern Biostar source pins coreboot and SeaBIOS dependencies. Its bridge initialization supplies wake masks but disables the SMI policy. SeaBIOS CPU Idle delegates to `yield_toirq`; its project patch does not add a UMC Stop Grant handler. It is a useful negative implementation comparison, not a missing hardware manual.

The comparison directory's compatibility-test Word documents describe an Octek Rhino 9/Pentium platform. Their power measurements do not establish UMC 486 register semantics. They are not additional UMC Stop Grant implementations.

## Decision

Keep the feature active and retain the complete request/event/clock/restore analysis. The existing source evidence establishes much more than the earlier three-ROM HLT observation, but does not establish a clock-running Stop Grant contract by itself.

Do not replace that gap with an emulator that defines the desired electrical result when a guessed register is written. Use source comparisons for firmware meaning and software diagnostics for observable wake and restoration behavior. The user has an oscilloscope or logic analyzer but prefers it as a last resort. Preserve the working image while establishing the software experiment's prerequisites. Software timing alone cannot identify the electrical clock state.

## Rejected options

- Set 76.02 alone: omits the reference's eligibility, SMM event and wake lifecycle.
- Set A1.20 for every SL CPU: contradicts the traced CPU/interface gates.
- Copy an entire legacy power manager: imports unrelated device policy and board-specific transactions.
- Treat a STOP CLK string, a longer timing loop or reduced benchmark speed as proof of architectural Stop Grant: none establishes both STPCLK and a continuing external clock.
- Declare a board unsupported from HLT or missing chipset pin names alone: external wiring and distinct state owners must first be accounted for.

## Revisit when

The useful remaining observation is specific: correlate STPCLK, external CPU CLK and wake events during the traced clock request. A successful Stop Grant path must keep CLK running, acknowledge the request and release STPCLK before the retained interrupt is delivered. Test timer and keyboard wake separately. A clock-input stop selects the separate full Stop Clock contract instead.

The DWT temporary RTC wake sequence is a candidate observation mechanism, subject to its alarm prerequisite and ownership adaptations. It is not yet a qualified normal idle backend. First establish a scheduled wake without requesting a clock transition. The [WAKECHK diagnostic](../development/sl486.md#smm-services) checks current SMM readiness and an owned RTC alarm callback without changing the flash image or requesting a clock state. Its physical result is needed before a later clock-transition experiment. Use the scope only if the remaining software results cannot distinguish the behavior needed for activation.

## Sources

- Intel, `241731-002`, sections 9.3.4 and 9.6; retained processor-family data book and searchable text.
- AMD, `19751` revision C, section 5; retained Am5x86 data sheet.
- [UMC reverse-engineering source, pinned commit](https://github.com/pc2005cz/um888x_documentation/tree/fa6924d18c49ae8ea6f9a46c0b9591ade353e7a2), especially the UM8886BF pin spreadsheet and register notes. This is reverse-engineered evidence, not an original chipset user's guide.
- Original M919 and comparison images in the retained private reference set; input and decoded-core identities are recorded with the generated research.
- [Modern Biostar source, pinned commit](https://github.com/alphaonex86/mb-8433UUD-A-BIOS/tree/0f12882abfe773109f794ec6a62cd65f4ce407a3), its `fetch_sources.sh` and coreboot/SeaBIOS patches. The retained binary is not presumed to be an exact build of that source snapshot.

## Native Phoenix request and clock-field ownership

The retained Phoenix8810 native-E inactive path at F8ECE..9055 writes A0 low2=2, SB56 low4=2, port61 low2=0 and A4=(old&60)|9D, followed by eighteen NOPs. Optional RTC alarm wake uses B.20 and SB91.01. Its A2.10 test is a source-cause branch, not a Stop Grant acknowledgment. The CPU classifier at F91A1..92AB selects E after a positive native mode00 SMM test; the actual POST-name table identifies the ordinary Intel486 families and Am5x86-P75 on this route. F is the failed-SMM alternative. The older Phoenix4v adds a hardware-selected D alternative, which is not imported.

A4 low2 also owns the PCI divider. Raw1 is PCI / 1. SB56 low2 owns the ISA divider and bits3:2 own keyboard timing. A literal donor request can therefore change independently selected clock settings. The opt-in M919 trial requires matching live A4 and SB56 encodings before any request, rather than synthesizing a new unproven profile.

The source full-on path clears80.C0 and92.80, pulses A3.20, writes savedA4|10 and restores saved56. The diagnostic retains that ordered transition, then restores the exact captured A4 and remaining controls. This deliberately replaces the donor's persistent inactive branch, timer rearm and device callbacks with one request and owned RTC cleanup. Exact register restoration and a returning alarm do not identify the external CLK state.
