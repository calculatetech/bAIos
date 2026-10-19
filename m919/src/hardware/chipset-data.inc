CHIP_GROUP_COUNT equ 3
CHIP_FIELD_COUNT equ 17
CHIP_OPTION_BYTES equ 10
CHIP_CERT_OFFSET equ 10
CHIP_RECORD_TAG equ 0x56
CHIP_CERT_TAG equ 0xA5
chip_group_0:
    chipset_field chip_clock,7,0,3,4,chip_clock_values,chip_clock_help1,chip_clock_help2
    chipset_field chip_speed,8,4,3,3,chip_speed_values,chip_speed_help1,chip_speed_help2
    chipset_field chip_mode,8,6,3,4,chip_mode_values,chip_mode_help1,chip_mode_help2
    chipset_field chip_read,0,6,3,4,chip_wait_values,chip_read_help1,chip_read_help2
    chipset_field chip_write,0,4,3,4,chip_wait_values,chip_write_help1,chip_write_help2
    chipset_field chip_type,5,0,1,2,chip_type_values,chip_type_help1,chip_type_help2
    chipset_field chip_edo_burst,5,1,1,2,chip_edo_burst_values,chip_edo_burst_help1,chip_edo_burst_help2
    chipset_field chip_refresh,4,4,1,2,chip_refresh_values,chip_refresh_help1,chip_refresh_help2
    chipset_field chip_parity,6,0,1,2,chip_enable_values,chip_parity_help1,chip_parity_help2
chip_group_1:
    chipset_field chip_l1,1,0,1,2,chip_enable_values,chip_l1_help1,chip_l1_help2
    chipset_field chip_l2,2,0,1,2,chip_l2_values,chip_l2_help1,chip_l2_help2
    chipset_field chip_policy,3,6,1,2,chip_policy_values,chip_policy_help1,chip_policy_help2
    chipset_field chip_burst,3,4,3,4,chip_burst_values,chip_burst_help1,chip_burst_help2
    chipset_field chip_early,4,7,1,2,chip_enable_values,chip_early_help1,chip_early_help2
chip_group_2:
    chipset_field chip_posted,9,0,1,2,chip_enable_values,chip_posted_help1,chip_posted_help2
    chipset_field chip_pci_burst,9,1,1,2,chip_enable_values,chip_pci_burst_help1,chip_pci_burst_help2
    chipset_field chip_copyback,9,2,1,2,chip_enable_values,chip_copyback_help1,chip_copyback_help2
chipset_groups dw chip_group_0,chip_group_1,chip_group_2
chipset_group_counts db 9,5,3
chipset_group_labels dw chip_memory,chip_cache,chip_bus
chipset_group_help dw chip_memory,chip_read_help1,chip_read_help2
    dw chip_cache,chip_l2_help1,chip_l2_help2
    dw chip_bus,chip_posted_help1,chip_posted_help2
chipset_first_view db 0,1,2
chipset_view_counts db 1,1,1
chipset_views:
    dw chip_memory
    db 0,9
    dw chip_memory_rows,chip_memory_headers
    dw chip_cache
    db 0,5
    dw chip_cache_rows,chip_cache_headers
    dw chip_bus
    db 0,3
    dw chip_bus_rows,chip_bus_headers
chip_memory_rows db 5,6,7,10,11,12,13,14,15
chip_memory_headers db 4
    dw chip_profiles_title
    db 9
    dw chip_access_title
    db 0
chip_cache_rows db 5,6,9,10,11
chip_cache_headers db 4
    dw chip_control_title
    db 8
    dw chip_timing_title
    db 0
chip_bus_rows db 5,6,7
chip_bus_headers db 4
    dw chip_access_title
    db 0
chipset_default db 0xF0,1,0,0x20,0,0,0,1,0,0
    times CHIP_SIZE-CHIP_OPTION_BYTES db 0
chipset_masks db 0xF0,1,1,0x70,0x90,3,1,3,0xF0,7
    times CHIP_SIZE-CHIP_OPTION_BYTES db 0xFF
; Entry: DRAM waits, SRAM burst, EDO burst. Unknown uses70ns.
; Normal: AMI BADA rows1/2 and3/4. No inferred60/70ns split.
chipset_profiles:
    db 0xF0,0x20,0, 0xF0,0x20,0, 0xF0,0x20,0, 0xF0,0x20,0
    db 0x50,0x00,0, 0x50,0x00,0, 0x50,0x00,0, 0x50,0x00,0
    times 8 db 0x00,0x00,0
    times 8 db 0xF0,0x30,2
u_chip_menu db 'Chipset',0
u_chip_title db 'bAIos Setup > Chipset',0
u_chip_open db 'Open',0x1A,0
u_chip_help dw u_chip_menu,chip_read_help1,chip_read_help2
chip_memory db 'Memory',0
chip_cache db 'Cache',0
chip_bus db 'Bus Timing',0
chip_profiles_title db 'Profiles',0
chip_access_title db 'Memory Access',0
chip_control_title db 'Cache Control',0
chip_timing_title db 'Cache Timing',0
chip_clock db 'Timing Profile Clock',0
chip_clock_help1 db 'Select the bus speed set by the board jumpers.',0
chip_clock_help2 db 'This chooses timings. It does not change speed.',0
chip_speed db 'DRAM Speed',0
chip_speed_help1 db 'Select the speed printed on the memory chips.',0
chip_speed_help2 db 'Unknown uses the 70 ns timing profile.',0
chip_mode db 'Memory Timing',0
chip_mode_help1 db 'Normal follows AMI. Compatibility adds wait cycles.',0
chip_mode_help2 db 'Manual unlocks timings. Fast reduces wait cycles.',0
chip_read db 'DRAM Read Wait States',0
chip_read_help1 db 'Extra clock cycles before RAM data is read.',0
chip_read_help2 db 'Lower values are faster but need faster memory.',0
chip_write db 'DRAM Write Wait States',0
chip_write_help1 db 'Extra clock cycles before RAM data is written.',0
chip_write_help2 db 'Lower values are faster but need faster memory.',0
chip_edo_burst db 'EDO Burst Timing',0
chip_edo_burst_help1 db 'Clock cycles used for an EDO memory burst.',0
chip_edo_burst_help2 db 'Available with EDO memory and Manual timing.',0
chip_type db 'DRAM Type',0
chip_type_help1 db 'Select the installed memory type: FPM or EDO.',0
chip_type_help2 db 'Use the type printed on the SIMMs or their chips.',0
chip_refresh db 'DRAM Refresh Rate',0
chip_refresh_help1 db 'How often the board refreshes RAM contents.',0
chip_refresh_help2 db 'Slow refresh reduces overhead but can lose data.',0
chip_parity db 'Memory Parity',0
chip_parity_help1 db 'Detects memory errors using an extra parity bit.',0
chip_parity_help2 db 'Enable only if the SIMMs have parity chips.',0
chip_l1 db 'CPU L1 Cache',0
chip_l1_help1 db 'Fast memory inside the CPU.',0
chip_l1_help2 db 'Enabled usually improves CPU performance.',0
chip_l2 db 'External L2 Cache',0
chip_l2_help1 db "Fast memory in the board's external SRAM chips.",0
chip_l2_help2 db 'The BIOS enables it after its cache test passes.',0
chip_policy db 'L2 Write Policy',0
chip_policy_help1 db 'Write-Back delays RAM writes for more speed.',0
chip_policy_help2 db 'Write-Through updates RAM on every cache write.',0
chip_burst db 'L2 Read Burst',0
chip_burst_help1 db 'Clock cycles for the first word, then three more.',0
chip_burst_help2 db "2-1-1-1 matches AMI's 2-1-2 setting.",0
chip_early db 'Early Cache Write',0
chip_early_help1 db 'Cache write timing control.',0
chip_early_help2 db 'Exact behavior is not yet confirmed.',0
chip_posted db 'CPU Posted Writes',0
chip_posted_help1 db 'Buffers writes so the CPU can continue sooner.',0
chip_posted_help2 db 'Applies to writes from the CPU to PCI devices.',0
chip_pci_burst db 'CPU Burst Writes',0
chip_pci_burst_help1 db 'Sends consecutive writes to PCI as a burst.',0
chip_pci_burst_help2 db 'Can improve transfers to PCI devices.',0
chip_copyback db 'Burst Copyback',0
chip_copyback_help1 db 'The exact purpose of this switch is unknown.',0
chip_copyback_help2 db '',0
chip_clock_values dw chip_clock_0,chip_clock_1,chip_clock_2,chip_clock_3
chip_clock_0 db '25 MHz',0
chip_clock_1 db '33 MHz',0
chip_clock_2 db '40 MHz',0
chip_clock_3 db '50 MHz',0
chip_speed_values dw chip_speed_0,chip_speed_1,chip_speed_2
chip_speed_0 db 'Unknown',0
chip_speed_1 db '60 ns',0
chip_speed_2 db '70 ns',0
chip_mode_values dw chip_mode_0,chip_mode_1,chip_mode_2,chip_mode_3
chip_mode_0 db 'Normal',0
chip_mode_1 db 'Compatibility',0
chip_mode_2 db 'Manual',0
chip_mode_3 db 'Fast',0
chip_wait_values dw chip_wait_3,chip_wait_2,chip_wait_1,chip_wait_0
chip_wait_choices dw chip_wait_0,chip_wait_1,chip_wait_2,chip_wait_3
chip_wait_0 db '0',0
chip_wait_1 db '1',0
chip_wait_2 db '2',0
chip_wait_3 db '3',0
chip_edo_burst_values dw chip_edo_burst_0,chip_edo_burst_1
chip_edo_burst_0 db '4-2-2-2',0
chip_edo_burst_1 db '3-1-1-1',0
chip_type_values dw chip_type_0,chip_type_1
chip_type_0 db 'FPM',0
chip_type_1 db 'EDO',0
chip_refresh_values dw chip_refresh_0,chip_refresh_1
chip_refresh_0 db 'Normal',0
chip_refresh_1 db 'Slow',0
chip_policy_values dw chip_policy_0,chip_policy_1
chip_policy_0 db 'Write-Through',0
chip_policy_1 db 'Write-Back',0
chip_burst_values dw chip_burst_0,chip_burst_1,chip_burst_2,chip_burst_3
chip_burst_0 db '3-2-2-2',0
chip_burst_1 db '3-1-1-1',0
chip_burst_2 db '2-2-2-2',0
chip_burst_3 db '2-1-1-1',0
chip_mode_choices dw chip_mode_3,chip_mode_0,chip_mode_1,chip_mode_2
chip_enable_values dw u_disabled,u_on
chip_enable_choices dw u_on,u_disabled
chip_l2_values dw u_on,u_disabled
chip_page_prefix db 'Page ',0
chip_page_slash db ' / ',0
chip_page_keys db 'PgUp/PgDn Page   F1 Help   F4/F5 Theme   F9 Defaults   F10 Save',0
chipset_group_titles dw chip_memory,chip_cache,chip_bus
