# MP386 timing and Setup contract

The working Mitsubishi memory mapper is authoritative for controller discovery, bank capacity, interleave and page maps. MR BIOS V010B302 supplies names, display units and normal-write masks for timing fields. Its cold memory mapper does not support this board's expansion card and is not used.

The native MR Setup decoder establishes 30 field descriptors. Fourteen describe the same seven bank timing fields in two groups. bAIos applies those fields separately to all six Mitsubishi banks. Together with ten bus/DMA fields, four common memory fields and system-ROM shadow, Setup has 57 chipset controls. Fast Boot is a separate control on Boot. Page Mode and RAM Interleave are automatic information fields. L2 cache has no software enable control.

## Hardware writes and defaults

Apply settings after the complete Mitsubishi initialization and before cache qualification and the visible RAM sweep. Preserve the native cache sequence. The table lists only fields with a named consumer. Each update reads the current word, merges the requested bits, writes the merged word, and retains the normal writer's two delay operations.

| Owner | Writable mask | Retained mask | Working default |
| --- | --- | --- | --- |
| ATU0801 | 07EF | F810 | 06A4 with the observed clock strap |
| ATU0802 | 003F | FFC0 | Low byte 15; observed word readback 1515 |
| Each MCU0003 | 7003 | 8FFC | 4101 for equal populated banks |
| Each MCU0004/0005 | 1FFF | E000 | Onboard10E4; expansion36E4 |

Defaults follow the OEM clock strap, including its alternate low-clock branch. Only CLK0/CLK1 and divisors1-4 are displayed. A 24 MHz source for CLK1 is an inference from the observed divisor and the switch chart, not a documented oscillator specification. Setup does not present that inference as a measured frequency.

| ATU field | Mask | Native encoding and displayed values | Observed default |
| --- | --- | --- | --- |
| Clock source | 0400 | 0=CLK0;1=CLK1 | CLK1 |
| Clock divisor | 0300 | Encoded value +1; divisors1-4 | /3 |
| Bus trigger | 0080 | 0=Mid;1=End | End |
| Posted writes | 0040 | 0=Disabled;1=Enabled | Disabled |
| BALE width | 0020 | 0=1 clock;1=0.5 clock | 0.5 clock |
| 8-bit bus wait | 0003 | Encoded value +4;4-7 clocks | 4 clocks |
| 16-bit bus wait | 000C | Encoded value +1;1-4 clocks | 2 clocks |
| DMA delay | ATU802:0030 | Encoded value +1;1-4 SCLK | 2 SCLK |
| DMA pulse width | ATU802:000C | 2*(encoded value +1);2,4,6,8 SCLK | 4 SCLK |
| DMA recovery | ATU802:0003 | Encoded value +1;1-4 SCLK | 2 SCLK |

SCLK denotes the bus clock unit in the native Setup. The first seven rows use ATU801. The next table uses each MCU's control word3.

| Memory field | Mask | Native values | Working default |
| --- | --- | --- | --- |
| Refresh period | 0003 | 7.5,15,30,60 microseconds | 15 microseconds |
| Read address timing | 4000 | 0=Mid;1=End | End |
| Write timing | 2000 | 0=Mid;1=End | Mid |
| Address edge | 1000 | 0=Rise;1=Fall | Rise |

The OEM clears Page Mode00F0 on the captured zero-revision MCUs. Interleave depends on bank population and equality. Retain those results. Do not apply a generic MR checkbox or its separate population mapper. Unknown CTRL8000, BANK8000, board92/E7 and the unused second pair in the MR timing tables remain unnamed and unexposed.

| Per-bank field | Word mask | Displayed CLK2 steps | Onboard default | Expansion default |
| --- | --- | --- | --- | --- |
| CAS to RAS | 1800 | 1-4 | 3 | 3 |
| Column address setup | 0400 | 1-2 | 1 | 2 |
| Row address hold | 0200 | 1-2 | 1 | 2 |
| CAS precharge | 0100 | 1-2 | 1 | 1 |
| CAS width | 00C0 | 1-4 on captured old revisions | 4 | 4 |
| RAS precharge | 0038 | 1-8 | 5 | 5 |
| RAS width | 0007 | 1-8 | 5 | 5 |

CLK2 is the memory timing unit named by the native Setup. A bank's upper E000 bits retain its detected geometry and unnamed fields. Empty banks are not editable. Faster nanosecond presets from other boards are not imported. Electrical stability of changed values needs bench testing.

## Configuration ownership

Logical configuration40..7F uses Mitsubishi NVRAM0200..023F through the complete OEM port48 protocol. The timing record uses logical69..7F, which maps to0229..023F. Its signature is D3, followed by a checksum and 21 data bytes. The in-memory policy has24 bytes; the last three bytes remain zero. No timing-record write reaches OEM memory records0240..02FF.

Fast Boot occupies policy byte0, system shadow byte1, ATU801 bytes2-3, ATU802 byte4 and common MCU timing bytes5-6. Bytes7-18 hold the six bank timing words. The remaining bytes are reserved. Validate every permitted bit, select safe signature D2 before a write, and verify all data. Only the board completion hook after the entire shared Save verifies can publish and verify D3. Failure retains D2. A missing or safe-selected record loads defaults.

CMOS36 marker AB describes an unfinished timing trial. It is armed before timing application and retired after the final summary. If it survives an external reset, the adapter takes complete cold initialization before retained warm RAM access, selects D2 without changing the stored payload, then uses the shared RAM-marker normalizer. It creates no RAM failure notice or retry. Deliberate warm reset restores target timing/cache prerequisites and retires only the ordinary trial. Actual measured RAM failure retains the shared retry markers and limit. D2 remains selected through Discard, rejected Save and POST completion; only a verified whole Save releases it.

Category order follows the user's requested hardware grouping. Sorting an option list does not change its saved hardware encoding. Reversed binary encodings use separate display and popup orders. End/Mid, Fall/Rise and BALE width are tested in both directions.

## Local evidence

The supplied V010B302 image has SHA256 `5e0c0e389252ba6d2cb96398900d48fed0ba2d555ecc8f0d22b049a314729a14`. Its native Setup is decoded by its own original decoder. The focused research packet records the exact reader, setter, masks and table bytes. Complete vendor disassemblies and manuals remain local inputs outside Git.

Native Setup readers2077/207F establish DRAM nanosecond labels. Normal writer98AB uses table9892 and helperAE9C. Mitsubishi OEM10A3..10D3 and0FC7..0FD4 establish the old-revision Page Mode rule. Captured MCU bank words10E4/36E4 establish the working defaults. The supplied MP3220 switch chart establishes the Devices guide. The Intel 82385 datasheet specifies32 KiB, consistent with the observed benchmark result.
