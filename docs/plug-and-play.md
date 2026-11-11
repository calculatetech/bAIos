# Plug and Play

Plug and Play identifies compatible expansion cards and assigns free resources. Resources include interrupt lines (IRQs), direct memory access (DMA) channels, I/O addresses, and memory windows. Supported ports provide this feature for 486-class and newer chipsets, including chipsets that support both 386 and 486 processors. The board adapter determines support.

Plug and Play reserves a small amount of memory below 640 KB for startup data. The amount depends on the installed cards.

## Choose who configures cards

Open Setup > Plug and Play. Use Configuration > BIOS for DOS and systems without Plug and Play resource management. The BIOS configures all assignable devices in this mode.

Use Operating System when the operating system manages Plug and Play cards. The BIOS still configures devices needed to start the computer. It leaves optional devices for the operating system. Both choices honor the manual reservations during BIOS allocation.

## Reserve resources for older cards

Older cards can use jumpers or their own configuration program. Reserve their resources so the BIOS does not assign the same resources to another card. Read the card manual or its configuration program first.

Set each used IRQ and DMA channel to Reserved. Keep unused resources Available. Enabled onboard controllers keep their own resources. Available does not disable a controller.

Reserved I/O Ports provides two address ranges. Enter Start in hexadecimal and Port Count in decimal. For example, Start 220h and Port Count 16 reserve addresses 220h through 22Fh. Port Count 0 disables that range and keeps its Start value.

Upper Memory reserves 16 KB blocks. Reserve every block used by a manually configured card.

These reservations guide BIOS assignments. They do not prevent an operating-system driver or a separate card utility from changing hardware configuration.

## Rebuild automatic assignments

Set Clear ESCD to Request, then save and restart. The BIOS rebuilds automatic assignments and keeps manual reservations. After complete reconstruction, the choice returns to Keep. If reconstruction is incomplete, the request remains pending.

The BIOS rebuilds automatic assignments at startup from the detected devices and saved Setup reservations. Boards with a supported storage adapter can also save an Extended System Configuration Data (ESCD) database for configuration utilities. See the board's guide for storage requirements.

## Boot from an expansion card

Use the existing boot-order categories in Boot. Other selects startup programs provided by expansion cards. Place Other before Hard Disk when the expansion card must supply the startup device. The card must contain a compatible startup ROM and a usable boot device.

## Read the startup listing

The device listing appears below the startup summary. It shows detected PCI functions and ISA Plug and Play logical devices, their identities, resources and status. Configured means that the BIOS programmed that device. An incomplete discovery notice remains visible when reconstruction did not finish, even if another device was configured. The listing does not require an operating system.
