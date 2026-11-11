# Shared firmware source

This directory contains services used by more than one port. Motherboard adapters supply hardware initialization, controller access and board wiring. Shared code must not contain model-specific register recipes.

`src/firmware/` provides POST, Setup, disk and floppy services, boot selection, memory testing, Plug and Play and APM. `src/pc/` provides reusable PC mechanisms. `tools/` and `tests/` contain common development helpers.

User instructions start in the [project manual](../README.md). Developers can read the [implementation contracts](../docs/development/firmware.md), [ROM modules](../docs/development/rom-modules.md), [processor interfaces](../docs/development/processor-support.md), [porting guide](../docs/porting.md), and [update guide](../docs/port-updates.md).

Keep board details and validation results in the relevant port. Include shared source through the port's established build configuration. Do not keep private copies of shared implementations.
