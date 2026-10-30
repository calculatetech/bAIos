%define BOARD_DISPLAY_NAME CFG_IDENTITY_VENDOR,' ',CFG_IDENTITY_MODEL
%define BOARD_VENDOR CFG_IDENTITY_VENDOR
%define BOARD_PRODUCT CFG_IDENTITY_MODEL
%define BOARD_CHIPSET_SETUP_POLICY "hardware/chipset-ui.inc"
%define BOARD_CHIPSET_CAS_SETUP "hardware/chipset-options.inc"
%define BOARD_PORTS_ROWS 5,6,7,8,9,10,10,12
%define BOARD_PORTS_VALUES u_acc_uart_values,u_acc_uart_values,u_acc_pair_values,u_parallel_values,u_mode_values,u_seek_values,u_seek_values,u_seek_values
%define BOARD_PORTS_MODES u_printer,u_bidirectional
%define BOARD_PORTS_MODE_HELP 'Compatible printer or bidirectional mode.'
%define BOARD_PORTS_SETUP_STRINGS "hardware/ports-setup.inc"
%define BOARD_PORTS_PAIRS 0x338,0x238,0x3E8,0x2E8,0x2E8,0x3E8,0x220,0x228
%define BOARD_MOUSE_DIAGNOSTIC_LABEL ' ACC3221 DB='
%define BOARD_LATE_POST_TRACE
%ifdef PB430_VGA60
%ifdef PB430_INTERLEAVE_PROBE
%define BOARD_LATE_CDBOOT
%elifdef PB430_CACHE_BURST_PROBE
%define BOARD_LATE_CDBOOT
%endif
%endif
%define BOARD_FAST_BOOT_SETTING (C_CHIP+6)
%define BOARD_POST_RAM_ROW 6
%define BOARD_RAM_POLICY_BEFORE_TEST
%define BOARD_RAM_TRIAL_BEGIN chipset_timing_trial_begin
%define BOARD_RAM_TRIAL_FINISH chipset_timing_trial_finish
%define BOARD_SETTINGS_SAVED chipset_timing_saved
%define BOARD_RAM_FAILURE_RESTORE pb430_timing_restore
%define BOARD_RAM_CACHE_FINISH chipset_ram_cache_finish
%macro BOARD_RAM_TEST_PREPARE 0
    mov al,4
    call acc_read
    test al,1
    jnz .retry ; The visible RAM test must never run through L2.
%endmacro
%ifdef PB430_CACHE_BURST_PROBE
%define BOARD_LATE_MEMORY_POLICY chipset_burst_policy
; Normal-mode reset adaptation; never used in the stock temporary tag window.
%macro pb430_burst_clear 0
    mov al,4
    out 0xF2,al
    out 0xED,al
    in al,0xF3
    and al,0xF7
    out 0xF3,al
    out 0xED,al
    in al,0xF3
    test al,8
    jz %%done
    mov al,0xE9
    out 0x80,al
    jmp hard_halt
%%done:
%endmacro
%else
%define BOARD_LATE_MEMORY_POLICY chipset_memory_policy
%endif
%include "hardware/timing-reset.inc"
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
%define FLOPPY_DEFAULT_TYPES 0x40
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
%define SUPERIO_INDEX 0xF2
%define SUPERIO_DATA 0xF3
%define CHIPSET_INDEX 0xF2
%define CHIPSET_DATA 0xF3
%define VGA_SEGMENT 0xC000
%define BOARD_ROM_COMPAT_SOURCE "hardware/rom-extensions.inc"
%define STATE_SEG CFG_PLATFORM_STATE_SEG
%define HW_BANK_CODES 0x1000
%define HW_ROUTING 0x1002
%define HW_CACHE_PRESENT 0x1003
%define HW_CACHE_CODE 0x1004
%define HW_CACHE_QUALIFIED 0x1005
%define HW_CACHE_ENABLED 0x1006
%define HW_VGA_REQUIRED 0x1007
%define HW_FDC_VERSION 0x1008
%define HW_FDC_ENHANCED 0x1009
%define HW_CACHE_LAST 0x100A ; Last alias witness, never a capacity qualifier.
%define HW_CACHE_WARM 0x100B
%define HW_CACHE_VALID 0x100C
%define HW_CACHE_CHECKED 0x100D ; 0=not tested,1=passed,2=failed.
%define CACHE_STATE_VALID 0xA8
%define HW_VIDEO_SS 0x1010
%define HW_VIDEO_SP 0x1012
%define HW_CACHE_SS 0x1014
%define HW_CACHE_SP 0x1016
%define HW_CACHE_FLAGS 0x1018
%define HW_CACHE_ENTRY_FLAGS 0x101A
%define HW_CACHE_FAIL_ADDRESS 0x101C
%define HW_CACHE_FAIL_EXPECTED 0x1020
%define HW_CACHE_FAIL_READ 0x1024
; OEM E115..E131: establish refresh and DMA cascade before using DRAM.
%macro pb430_refresh_dma 0
    mov al,0
    out 0x8F,al
    mov al,0x54
    out PIT_COMMAND,al
    mov al,0x12
    out PIT_CHANNEL1,al
    out DMA1_MASTER_CLEAR,al
    out DMA2_MASTER_CLEAR,al
    mov al,0xC0
    out 0xD6,al
    mov al,0
    out 0xD4,al
%endmacro
%macro ata_port 1
    mov dx,%1
%endmacro
%macro cd_port 1
    mov dx,%1
%endmacro
%include "setup/layout.inc"

%ifdef EMULATOR_SETUP_TEST
%define EMULATOR_EXIT_REQUIRED
%endif

%ifdef EMULATOR_BOOT_RETRY_EXIT
%define EMULATOR_EXIT_REQUIRED
%endif

%ifdef EMULATOR_RAM_SKIP_TEST
%define EMULATOR_EXIT_REQUIRED
%endif
%ifdef EMULATOR_PAUSE_ONLY
%define EMULATOR_EXIT_REQUIRED
%endif

%ifdef PB430_BOOT_RETRY_PROOF
%define BOARD_BOOT_RETRY_TEST_SOURCE "../tests/core-boot-retry.inc"
%endif
