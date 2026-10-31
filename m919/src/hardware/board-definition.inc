%define BOARD_KBC_NO_AUX_COMMANDS 1
%define BOARD_RESET_NEAR 1
%define BOARD_LATE_POST_TRACE 1
; No RAM stack is available at the reset entry. Keep the old scanout blank
; until the VGA BIOS restores it, preserving clock bits and the selected index.
%macro board_video_blank 1
    mov dx,0x3C4
    in al,dx
    mov ah,al
    mov al,1
    out dx,al
    inc dx
    in al,dx
%if %1
    or al,0x20
%else
    and al,0xDF
%endif
    out dx,al
    dec dx
    mov al,ah
    out dx,al
%endmacro
%define BOARD_PCI_FIXED_RESOURCES board_pci_fixed_resources
%define BOARD_WIDE_MEMORY_COUNTS 1
%define BOARD_FAST_BOOT_SETTING C_CHIP+12
%define BOARD_IDE_32BIT_POLICY C_CHIP+13
%define BOARD_ATA_DWORD_IO 1
%define BOARD_ATA_DEVICE_COUNT 4
%ifndef BOARD_ATA_PIO_MAX
%define BOARD_ATA_PIO_MAX 4
%endif
%define BOARD_ATA_PIO_ADAPTER
%define BOARD_ATA_PIO_POLICY C_CHIP+20
%define BOARD_ATA_PIO_POLICY_HIGH C_CHIP+23
%define BOARD_POST_RAM_CACHE chipset_post_ram_cache
%define BOARD_DISPLAY_NAME CFG_IDENTITY_VENDOR,' ',CFG_IDENTITY_MODEL
%define BOARD_VENDOR CFG_IDENTITY_VENDOR
%define BOARD_PRODUCT CFG_IDENTITY_MODEL
%define BOARD_CHIPSET_SETUP_POLICY "hardware/chipset-ui.inc"
%define BOARD_CHIPSET_CAS_SETUP "hardware/chipset-options.inc"
%define BOARD_PORTS_ROWS 5,6,7,8,9
%define BOARD_PORTS_SETUP_COUNT 5
%define BOARD_PORTS_SETUP_LABELS u_uart_a,u_uart_b,u_parallel,u_parallel_mode,u_ecp_dma
%define BOARD_PORTS_SETUP_PARAMETERS board_ports_parameters
%define BOARD_PORTS_SETUP_COMMIT board_ports_commit
%define BOARD_PORTS_SETUP_HELP board_ports_help
%define BOARD_BOOT_RETRY_TEST_SOURCE "../tests/core-retry.inc"
%define BOARD_PORTS_VALUES u_uart_values,u_uart_values,u_parallel_values,u_mode_values,u_ecp_dma_values
%define BOARD_PORTS_MODES u_ecp,u_epp,u_printer
%define BOARD_PORTS_MODE_HELP 'SPP printer output, EPP, or ECP mode.'
%define BOARD_PORTS_SETUP_STRINGS "hardware/ports-setup.inc"
%define BOARD_FLOPPY_POST_DETAILS board_floppy_summary_details
%define BOARD_MOUSE_HANDOFF board_keyboard_handoff
%define BOARD_BOOT_HANDOFF board_keyboard_handoff
%define BOARD_AUX_POLICY_ENABLED CFG_PLATFORM_AUX_BIOS_SUPPORTED
%if !BOARD_AUX_POLICY_ENABLED
%define BOARD_MOUSE_INIT board_mouse_no_aux
%define BOARD_PORTS_DEFAULT_FILTER board_ports_no_aux_default
%define BOARD_PORTS_LOAD_FILTER board_ports_no_aux_load
%define BOARD_PORTS_SAVE_FILTER board_ports_no_aux_save
%define BOARD_MOUSE_POLICY_SOURCE "hardware/mouse-policy.inc"
%endif
int1a equ pci_int1a
%define DMA1_MASTER_CLEAR   0x000D
%define DMA2_MASTER_CLEAR   0x00DA
%define FDC_DOR             0x03F2
%define FDC_MSR             0x03F4
%define FDC_FIFO            0x03F5
%define FDC_CCR             0x03F7
%define FLOPPY_DEFAULT_TYPES CFG_PLATFORM_DEFAULT_FLOPPY   ; A: 1.44 MB, B: not installed; not a probe result.
%define SYSTEM_PORT_B       0x0061
%define PIT_CHANNEL1        0x0041
%define PIT_COMMAND         0x0043

%define POST_PORT CFG_PLATFORM_POST_PORT

%define KBC_DATA CFG_PLATFORM_KBC_DATA
%define KBC_STATUS CFG_PLATFORM_KBC_STATUS
%define KBC_COMMAND CFG_PLATFORM_KBC_COMMAND
%define BOARD_MOUSE_DIAGNOSTIC_LABEL ' SIOCR2='

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

%define STATE_SEG CFG_PLATFORM_STATE_SEG
%define KBC_OUTPUT_PORT_VALUE CFG_PLATFORM_KBC_OUTPUT_PORT
%define KBC_INITIAL_COMMAND_BYTE CFG_PLATFORM_KBC_COMMAND_BYTE
%define RTC_CENTURY_REGISTER CFG_PLATFORM_RTC_CENTURY_REGISTER
%define RTC_NMI_SELECT_MASK CFG_PLATFORM_RTC_NMI_MASK
%define RTC_INTERRUPT_LABEL rtc_interrupt

%define VGA_SEGMENT 0xC000
%define SUPERIO_INDEX CFG_PLATFORM_SIO_INDEX
%define SUPERIO_DATA CFG_PLATFORM_SIO_DATA

; Hardware-private scratch is outside the donor records and UI state.
%define HW_HB52 0x1030
%define HW_HB53 0x1031
%define HW_HB61 0x1032
%define HW_RAM_BANKS 0x1033
%define HW_CACHE_CODE 0x1036
%define HW_CACHE_MAP 0x1037
%define HW_CACHE_FLAGS 0x1038 ; Qualified1, failed2, enabled4, geometry mismatch8.
%define HW_IDE_USABLE 0x1039
%define HW_VGA_END 0x103A
%define BOARD_OPTION_ROM_FIRST_SEG [fs:HW_VGA_END]
%define HW_CACHE_BYTES 0x103C
%define HW_CACHE_SAMPLES 0x1200
%define HW_CACHE_FAILURE_ADDRESS (HW_CACHE_SAMPLES+8)
%define HW_CACHE_FAILURE_EXPECTED (HW_CACHE_SAMPLES+16)
%define HW_CACHE_FAILURE_OBSERVED (HW_CACHE_SAMPLES+20)
%define HW_CACHE_STAGE (HW_CACHE_SAMPLES+24)
%define HW_CACHE_TRIAL_FIRST (HW_CACHE_SAMPLES+32)
%define HW_CACHE_BUFFER 0x0800 ; IDENTIFY scratch is unused before device startup.
%define M_VGA_BDF 0x1000
%define M_PCI_ADDRESS 0x1004
%define M_PCI_MMIO 0x1008
%define M_PCI_IO 0x100C
%define M_ROM_PTR 0x1010
%define M_ROM_SS 0x1014
%define M_ROM_SP 0x1016
%define ROM_STATE_SEG STATE_SEG
%define ROM_POINTER M_ROM_PTR
%define ROM_SAVED_SS M_ROM_SS
%define ROM_SAVED_SP M_ROM_SP
%define ROM_SCAN_SEG 0x1018
%define ROM_SCAN_NEXT 0x101A
%define ROM_COUNT 0x101C
%define M_PCI_REJECTED 0x101E
%define M_PCI_ROM_USED 0x101F
%define M_PCI_ROM_RESERVED 0x1020
%define PCI_ROM_FIRST_SEG 0xD000
%define PCI_ROM_LIMIT_SEG 0xE000
%define BOARD_OPTION_ROM_INIT pci_option_roms
%define BOARD_OPTION_ROM_SKIP pci_rom_skip
%define ROM_FIRST_SEG [fs:HW_VGA_END]
%define ROM_LIMIT_SEG 0xE000
%include "setup/layout.inc"
%define HW_PORT_TABLE 0x0190
%define HW_POSITION 0x01A2
%define HW_CD_PORT_TABLE 0x1080
%define HW_CD_POSITION 0x1092
%define HW_FDC_VERSION 0x1100
%define HW_FDC_ENHANCED 0x1101
%define HW_CYRIX_SAVED 0x10A0
%define HW_CYRIX_PCR 0x10A1
%define HW_PCI_LINKS 0x10A4
%define HW_PCI_USED_IRQS 0x10A8
%define HW_PCI_LEVEL_IRQS 0x10AA
%define HW_PCI_ROUTE_MASKS 0x10AC
%define HW_IDE_BDF 0x1034
%macro ata_port 1
%if (%1) == ATA_CONTROL
    mov dx,[fs:HW_PORT_TABLE+16]
%else
    mov dx,[fs:HW_PORT_TABLE+2*((%1)-ATA_DATA)]
%endif
%endmacro
%macro cd_port 1
%if (%1) == ATA_CONTROL
    mov dx,[fs:HW_CD_PORT_TABLE+16]
%else
    mov dx,[fs:HW_CD_PORT_TABLE+2*((%1)-ATA_DATA)]
%endif
%endmacro
