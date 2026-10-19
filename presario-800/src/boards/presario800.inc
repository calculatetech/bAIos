; Assembly-time board composition. No runtime board detection.
%define BOARD_DISPLAY_NAME 'Compaq Presario 800'
%define BOARD_VENDOR 'Compaq'
%define BOARD_PRODUCT 'Presario 800'
%define BOARD_CHIPSET_POLICY "chipsets/vl82c481/policy.inc"
%define BOARD_CHIPSET_SETUP_POLICY "chipsets/vl82c481/setup-policy.inc"
%define BOARD_CHIPSET_CAS_SETUP "chipsets/vl82c481/setup-cas.inc"
%define BOARD_CHIPSET_SETUP "chipsets/vl82c481/setup-data.inc"

%define CHIPSET_INDEX       0x00EC
%define CHIPSET_DATA        0x00ED
%define CHIPSET_CONFIG_OFF  0x00F9
%define CHIPSET_CONFIG_ON   0x00FB

%define RAMTMG_REG          0x01
%define RAMTMG_VALUE        0xBF    ; Latest start,4T/4T,longest CAS; OEM baseline was96h.
%define CACHE_PROBE_RAMTMG  0x96    ; Physically tested OEM timing for direct SRAM detection.
%define RAMCFG0_REG         0x02
%define RAMCFG0_VALUE       0x8C    ; Bank 0: single-sided 1M devices = 4 MiB.
%define RAMCFG0_DOUBLE      0x8D    ; Bank 0: onboard plus optional side = 8 MiB.
%define RAMCFG1_REG         0x03
%define RAMCFG1_VALUE       0x88    ; Banks 2 and 3 absent.
%define RAMSET_REG          0x04
%define RAMSET_VALUE        0x16    ; OEM lower bits; interleave disabled unless explicitly enabled.
%define RAM_INTERLEAVE_MODES 0x1B    ; Modes 1/2/4/5; physical pair 1/2 fails (modes 3/6).
%define NTBREF_REG          0x05
%define NTBREF_VALUE        0x00    ; Synchronous refresh, 15.625 us.
%define CLKCTL_REG          0x06
%define CLKCTL_VALUE        0x00    ; OEM ISA clock divider, not reset-default 1Bh.
%define DMACTL_REG          0x08
%define DMACTL_VALUE        0x38    ; OEM DMA waits and SYSCLK/2 DMA clock.
%define BUSCTL_REG          0x09
%define BUSCTL_VALUE        0x30    ; OEM fast disk I/O and 24 mA slot drive.
%define FAST_CPU_PORT       0x00F5  ; OEM F000:8516/857F selects the fast CPU clock.
%define MISCSET_REG         0x07
%define PRIMARY_CACHE_EN    0x08
%define EXTERNAL_CACHE_REG  0x19
%define EXTERNAL_SEGMENT_EN 0x80  ; Apply A0000-FFFFF cacheability controls to L2.
%define EXTERNAL_CACHE_DIRECT 0xB7 ; OEM begins with two banks, 9-bit tag, direct access.
%define CACHE_REGION_FIRST  0x13    ; A0000-EFFFF: non-cacheable, as OEM table 8659.
%define CACHE_REGION_ROM    0x18    ; F0000-FFFFF: cacheable and write-protected.
%define ROMSET_REG          0x0C
%define ROMSET_VALUE        0x18    ; OEM startup ROM location code.
%define VGA_ROMSET_VALUE    0x28    ; Working MR BIOS relocation code exposes the lower ROM at C0000.
%define VGA_SHADOW_REG      0x0F
%define SYSTEM_SHADOW_REG   0x12    ; OEM warm entry clears E0000-FFFFF shadows.
%define VGA_SHADOW_CLEAR    0x0F    ; Read and write shadow RAM for C0000-C7FFF.
%define VGA_SHADOW_FILL     0x05    ; Read ROM, write shadow RAM for C0000-C7FFF.
%define VGA_SHADOW_RUN      0x0A    ; Read shadow RAM, write ROM bus for C0000-C7FFF.
%define VGA_ROM_WORDS       0x4000  ; Header size 40h is 32 KiB.

%define SUPERIO_INDEX       0x03F0
%define SUPERIO_DATA        0x03F1

%define DMA1_MASTER_CLEAR   0x000D
%define DMA2_MASTER_CLEAR   0x00DA
%define FDC_DOR             0x03F2
%define FDC_MSR             0x03F4
%define FDC_FIFO            0x03F5
%define FDC_CCR             0x03F7
%define FLOPPY_DEFAULT_TYPES 0x40   ; A: 1.44 MB, B: not installed; not a probe result.
%define SUPERIO_FDC_MODE     0x6C   ; OEM F000:8837: AT, enhanced TDR, DRATE outputs.
%define SYSTEM_PORT_B       0x0061
%define PIT_CHANNEL1        0x0041
%define PIT_COMMAND         0x0043

%define POST_PORT           0x0080

%define KBC_DATA            0x0060
%define KBC_STATUS          0x0064
%define KBC_COMMAND         0x0064
%define KBC_PLATFORM_REG    0x1D    ; VL82C114 KBDCTRL, not the 8042 command byte.
%define KBC_PLATFORM_VALUE  0xC5    ; OEM F000:8673: PS/2 pin/command mode (bit 1 clear).

%define ATA_DATA            0x01F0
%define ATA_ERROR           0x01F1
%define ATA_COUNT           0x01F2
%define ATA_LBA0            0x01F3
%define ATA_LBA1            0x01F4
%define ATA_LBA2            0x01F5
%define ATA_DRIVE           0x01F6
%define ATA_STATUS          0x01F7
%define ATA_COMMAND         0x01F7
%define ATA_CONTROL         0x03F6

%define VGA_SEGMENT         0xC000
%define VGA_ENTRY           0x0003
%ifdef VGA_BIOS_141
%define VGA_INIT_JUMP_WORD  0x28E9
%define VGA_INT10_ENTRY     0x2897
%else
%define VGA_INIT_JUMP_WORD  0x62E9
%define VGA_INT10_ENTRY     0x27B7
%endif

%define STATE_SEG                0x9FC0
%define KBC_OUTPUT_PORT_VALUE    0xCF
%define KBC_INITIAL_COMMAND_BYTE 0x5C
%define RTC_CENTURY_REGISTER     0x32
%define RTC_NMI_SELECT_MASK      0
%define RTC_INTERRUPT_LABEL      int1a
