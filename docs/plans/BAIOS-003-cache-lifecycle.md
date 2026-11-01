# Shared cache lifecycle design

This developer specification describes the common process. Controller transactions, migration details and validation records belong to their ports.

## Required behavior

Keep cache discovery, capacity, qualification, initialization and activation as separate facts. Unknown capacity remains unknown. Preserve requested settings, effective saved settings and active hardware state separately.

Use a short startup test with two complementary address-derived write/read passes over the established cache capacity. Where meaningful, add a fixed set of normal-mode address witnesses. The test budget scales with cache capacity rather than installed RAM. Comprehensive stress and DMA checks belong in development validation.

The adapter must make the test exercise external SRAM. A successful DRAM readback is not a cache test. Run the short check each normal boot instead of using a persistent certificate to bypass it.

## Adapter boundary

Use the existing assembly-time board composition. Keep early preparation, after-RAM work, final activation and reset at the board's established entry points. Do not add a runtime board registry or register interpreter.

Preserve each complete reference transition, including its prerequisites, stack, interrupts, NMI, A20, segments, timing, tag initialization, fill and return. A common phase binding cannot insert calls or diagnostic operations into a sensitive temporary mode.

Apply eligible saved policy through the existing activation owner. Preserve disabled, absent, ambiguous and failed outcomes. Recovery and deliberate reset keep their established owners. Optional Fast Boot or skip keys cannot bypass mandatory memory initialization.

## Migration

Share the workload and transition vocabulary first. Then integrate each adapter without changing its hardware transaction. Compare source relocation against its original emitted image. Treat intentional test-policy changes separately from retained initialization.

The [port migration reference](../../pb430/docs/plans/BAIOS-003-cache-lifecycle.md) retains the detailed transition scenarios and implementation stages. Individual ports own their outcomes and evidence. The [shared source contracts](../development/firmware.md) describe reusable primitives.
