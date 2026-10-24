%define BOARD_DISPLAY_NAME CFG_IDENTITY_VENDOR,' ',CFG_IDENTITY_MODEL
%define BOARD_VENDOR CFG_IDENTITY_VENDOR
%define BOARD_PRODUCT CFG_IDENTITY_MODEL
%define BOARD_CPU_386
%define BOARD_ROM_COMPAT_SOURCE "pc/vga-compat.inc"
%define BOARD_SETUP_READONLY_PAGES
%define BOARD_PORTS_SETUP_DRAW mp_ports_draw
%define BOARD_PORTS_SETUP_HELP mp_ports_help
%define BOARD_CHIPSET_SETUP_POLICY "hardware/chipset-ui.inc"
%define BOARD_CHIPSET_CAS_SETUP "setup/enum-ui.inc"
%define BOARD_FAST_BOOT_SETTING C_CHIP
%define BOARD_RAM_TRIAL_FINISH chipset_timing_trial_finish
%define BOARD_SETTINGS_SAVED chipset_timing_saved
%define BOARD_RAM_FAILURE_RESTORE call mp_timing_restore
%define BOARD_A20_READ tiger_a20_read
%define BOARD_A20_WRITE tiger_a20_write
%define BOARD_BOOT_HANDOFF mp_boot_handoff
%define BOARD_RTC_EXTENDED_READ mitsubishi_nvram_read
%define BOARD_RTC_EXTENDED_WRITE mitsubishi_nvram_write
%define BOARD_POST_RAM_ROW 6
%define BOARD_PORTS_ROWS 5,6,7,8,9,10,11,12
%define BOARD_PORTS_VALUES u_uart_values,u_uart_values,u_pair_values,u_parallel_values,u_mode_values,u_seek_values,u_seek_values,u_seek_values
%define BOARD_PORTS_MODES u_printer,u_bidirectional
%define BOARD_PORTS_MODE_HELP 'Set the onboard ports with the board switches.'
%define BOARD_PORTS_SETUP_STRINGS "hardware/ports-setup.inc"
%define BOARD_MOUSE_DIAGNOSTIC_LABEL ' MP386 '
%define BOARD_MOUSE_INIT mp386_mouse_init
%define BOARD_DEFAULT_BOOT_FIRST 3
%define BOARD_DEFAULT_BOOT_REST 0x0201
%define BOARD_LATE_MEMORY_POLICY mp_memory_finish
%define POST_PORT 0x80
%define KBC_DATA 0x60
%define KBC_STATUS 0x64
%define KBC_COMMAND 0x64
%define KBC_OUTPUT_PORT_VALUE 0xCF
%define KBC_INITIAL_COMMAND_BYTE 0x5C
%define RTC_CENTURY_REGISTER 0x32
%define RTC_NMI_SELECT_MASK 0
%define RTC_INTERRUPT_LABEL int1a
%define DMA1_MASTER_CLEAR 0x0D
%define DMA2_MASTER_CLEAR 0xDA
%define FDC_DOR 0x3F2
%define FDC_MSR 0x3F4
%define FDC_FIFO 0x3F5
%define FDC_CCR 0x3F7
%define FLOPPY_DEFAULT_TYPES 0x42
%define SYSTEM_PORT_B 0x61
%define PIT_CHANNEL1 0x41
%define PIT_COMMAND 0x43
%define ATA_DATA 0x1F0
%define ATA_ERROR 0x1F1
%define ATA_COUNT 0x1F2
%define ATA_LBA0 0x1F3
%define ATA_LBA1 0x1F4
%define ATA_LBA2 0x1F5
%define ATA_DRIVE 0x1F6
%define ATA_STATUS 0x1F7
%define ATA_COMMAND 0x1F7
%define ATA_CONTROL 0x3F6
%define VGA_SEGMENT 0xC000
%define STATE_SEG CFG_PLATFORM_STATE_SEG
%define MP_MEMORY_SCRATCH 0x0500
%define MP_MEMORY_MAGIC 0x5833504D
%define HW_BANK_CODES 0x1000
%define HW_BANK_COUNTS 0x1010
%define HW_MCU_COUNT 0x101C
%define HW_F_SHADOW 0x101E
%define HW_STATE_VALID 0x1004
%define HW_VIDEO_SS 0x1008
%define HW_VIDEO_SP 0x100A
%define HW_FDC_VERSION 0x100C
%define HW_FDC_ENHANCED 0x100D
%define HW_CACHE_POLICY 0x100E
%define HW_BOARD_KIND 0x100F
%define HW_CACHE_STATUS 0x101F
%macro ata_port 1
    mov dx,%1
%endmacro
%macro cd_port 1
    mov dx,%1
%endmacro
%include "setup/layout.inc"
