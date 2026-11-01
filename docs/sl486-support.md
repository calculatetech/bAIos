# SL-enhanced processors and power saving

An SL-enhanced processor has extra functions for power management. The BIOS can identify supported processors and use those functions when the motherboard provides the required connections and controller support.

The CPU name can include `SL` or `SL Enhanced`. This describes the processor. It does not mean that the computer is currently asleep or that every motherboard power-saving function is available.

## What idle power saving does

Idle means that software has no work for the processor. When software reports this condition, the BIOS can place the processor in a lower-power state. An enabled hardware interrupt wakes it so work can continue. Timer interrupts therefore produce short idle periods during normal DOS use.

The BIOS uses APM, a standard interface for power management. An APM driver tells the BIOS when the processor is idle. A program that remains busy does not enter this path unless software reports idle time.

CPU idle does not turn off the computer, suspend the operating system, or switch off drives and displays. Those functions need separate support. There is no automatic inactivity timer for this CPU idle service.

## Enable idle reporting in DOS

For MS-DOS 6.22, add this line to `CONFIG.SYS`, then restart:

```dos
DEVICE=C:\DOS\POWER.EXE ADV:REG
```

Use the path where DOS is installed. `ADV:REG` balances power saving and normal application use. Another APM-aware idle driver can provide the same idle reporting.

Run `POWER` without arguments to view its status. See the [Microsoft POWER.EXE help](https://www.infania.net/misc/dos622help/power.exe.html) for its other modes.

## Availability and limitations

The BIOS uses a motherboard adapter for hardware power control. It checks the processor, required controller interface and installed handler. Without that support, the idle service uses the processor's normal halt instruction and waits for an interrupt.

Power saving preserves the selected PCI bus clock divider. It does not require one particular divider setting.

A memory manager such as EMM386 controls protected processor operations. A motherboard adapter can support clock saving in this environment by keeping those operations inside its system-management handler. Other adapters use the normal halt path.

In Windows 3.1, install the APM system driver through Windows Setup and use the Power control panel to select a power-saving mode. Windows reports its own idle time to the BIOS. Its idle periods can differ from those in DOS.

Read your port manual for available hardware functions and known limitations. Driver compatibility and diagnostic results belong to that port's developer documentation. [Shared interface details](development/processor-support.md) are available for firmware developers.
