CHIP_GROUP_COUNT equ 7
CHIP_FIELD_COUNT equ 45
CHIP_OPTION_BYTES equ 24
CHIP_RECORD_TAG equ 0x57
chip_group_0:
    chipset_field chip_l1,1,0,1,2,chip_enable_values,chip_l1_help1,chip_l1_help2
    chipset_field chip_l2,2,0,1,2,chip_l2_values,chip_l2_help1,chip_l2_help2
    chipset_field chip_policy,3,6,1,2,chip_policy_values,chip_policy_help1,chip_policy_help2
    chipset_field chip_burst,3,4,3,4,chip_burst_values,chip_burst_help1,chip_wait_help
    chipset_field chip_early,4,7,1,2,chip_enable_values,chip_early_help1,chip_early_help2
    chipset_field chip_boot_speed,7,7,1,2,chip_boot_speed_values,chip_speed_help1,chip_speed_help2
    chipset_field chip_turbo,7,5,1,2,chip_l2_values,chip_turbo_help1,chip_turbo_help2
    chipset_field chip_deturbo,7,6,1,2,chip_deturbo_values,chip_deturbo_help1,chip_deturbo_help2
    chipset_field chip_cyrix_linear,18,1,1,2,chip_enable_values,chip_linear_help1,chip_cyrix_help
    chipset_field chip_cyrix_lsser,18,2,1,2,chip_enable_values,chip_lsser_help1,chip_cyrix_help
chip_group_1:
    chipset_field chip_pci_clock,10,2,3,4,chip_pci_clock_values,chip_pci_clock_help1,chip_clock_help
    chipset_field chip_posted,9,0,1,2,chip_posted_values,chip_posted_help1,chip_posted_help2
    chipset_field chip_pci_burst,9,1,1,2,chip_enable_values,chip_pci_burst_help1,chip_pci_burst_help2
    chipset_field chip_pci_posted,9,2,1,2,chip_enable_values,chip_pci_posted_help1,chip_keep_help
    chipset_field chip_devsel,10,0,3,4,chip_devsel_values,chip_devsel_help1,chip_keep_help
    chipset_field chip_bus_lock,8,0,3,3,chip_lock_values,chip_bus_lock_help1,chip_keep_help
    chipset_field chip_park,8,2,3,3,chip_keep_switch_values,chip_park_help1,chip_keep_help
    chipset_field chip_preempt,8,4,3,3,chip_keep_switch_values,chip_preempt_help1,chip_keep_help
    chipset_field chip_pci_parity,8,6,3,3,chip_keep_switch_values,chip_pci_parity_help1,chip_pci_parity_help2
    chipset_field chip_palette,18,3,1,2,chip_enable_values,chip_palette_help1,chip_palette_help2
    chipset_field chip_ide_trigger,19,0,1,2,chip_trigger_values,chip_trigger_help1,chip_trigger_help2
chip_group_2:
    chipset_field chip_irq_1,16,0,15,12,chip_irq_values,chip_irq_help1,chip_irq_help2
    chipset_field chip_irq_2,16,4,15,12,chip_irq_values,chip_irq_help1,chip_irq_help2
    chipset_field chip_irq_3,17,0,15,12,chip_irq_values,chip_irq_help1,chip_irq_help2
    chipset_field chip_irq_4,17,4,15,12,chip_irq_values,chip_irq_help1,chip_irq_help2
chip_group_3:
    chipset_field chip_mapping,18,0,1,2,chip_enable_values,chip_mapping_help1,chip_mapping_help2
    chipset_field chip_ldev,7,3,3,3,chip_ldev_values,chip_ldev_help1,chip_keep_help
    chipset_field chip_mem_lock,7,1,3,3,chip_keep_switch_values,chip_mem_lock_help1,chip_keep_help
chip_group_4:
    chipset_field chip_isa_clock,11,0,3,3,chip_isa_values,chip_isa_help1,chip_clock_help
    chipset_field chip_io_recovery,11,5,3,4,chip_recovery_values,chip_io_help1,chip_io_help2
    chipset_field chip_kbc_clock,11,2,7,5,chip_kbc_values,chip_kbc_help1,chip_keep_help
chip_group_5:
    chipset_field chip_read,0,6,3,4,chip_wait_values,chip_read_help1,chip_wait_help
    chipset_field chip_write,0,4,3,4,chip_wait_values,chip_write_help1,chip_wait_help
    chipset_field chip_type,5,0,1,2,chip_type_values,chip_type_help1,chip_type_help2
    chipset_field chip_edo_burst,5,1,1,2,chip_edo_burst_values,chip_edo_burst_help1,chip_wait_help
    chipset_field chip_copyback,7,0,1,2,chip_enable_values,chip_copyback_help1,chip_wait_help
    chipset_field chip_refresh,4,4,1,2,chip_refresh_values,chip_refresh_help1,chip_refresh_help2
    chipset_field chip_parity,6,0,1,2,chip_enable_values,chip_parity_help1,chip_parity_help2
chip_group_6:
    chipset_field chip_video_cache,14,0,1,2,chip_enable_values,chip_video_cache_help1,chip_video_cache_help2
    chipset_field chip_shadow_c800,15,2,1,2,chip_shadow_values,chip_shadow_help1,chip_shadow_help2
    chipset_field chip_shadow_cc00,15,3,1,2,chip_shadow_values,chip_shadow_help1,chip_shadow_help2
    chipset_field chip_shadow_d000,15,4,1,2,chip_shadow_values,chip_shadow_help1,chip_shadow_help2
    chipset_field chip_shadow_d400,15,5,1,2,chip_shadow_values,chip_shadow_help1,chip_shadow_help2
    chipset_field chip_shadow_d800,15,6,1,2,chip_shadow_values,chip_shadow_help1,chip_shadow_help2
    chipset_field chip_shadow_dc00,15,7,1,2,chip_shadow_values,chip_shadow_help1,chip_shadow_help2
chipset_groups:
    dw chip_group_0,chip_group_1,chip_group_2,chip_group_3,chip_group_4,chip_group_5,chip_group_6
chipset_group_counts:
    db 10,11,4,3,3,7,7
chipset_group_labels dw chip_cache,chip_bus,chip_irqs,chip_local_bus,chip_isa_bus,chip_memory,chip_rom
chipset_group_help:
    dw chip_cache,chip_l1_help1,chip_l1_help2
    dw chip_bus,chip_pci_clock_help1,chip_clock_help
    dw chip_irqs,chip_irq_help1,chip_irq_help2
    dw chip_local_bus,chip_ldev_help1,chip_keep_help
    dw chip_isa_bus,chip_isa_help1,chip_clock_help
    dw chip_memory,chip_read_help1,chip_wait_help
    dw chip_rom,chip_video_cache_help1,chip_video_cache_help2
chipset_first_view db 0,1,2,3,4,5,6
chipset_view_counts db 1,1,1,1,1,1,1
chipset_views:
    dw chip_cache
    db 0,10
    dw chip_rows_0,chip_headers
    dw chip_bus
    db 0,11
    dw chip_rows_1,chip_headers
    dw chip_irqs
    db 0,4
    dw chip_rows_2,chip_headers
    dw chip_local_bus
    db 0,3
    dw chip_rows_3,chip_headers
    dw chip_isa_bus
    db 0,3
    dw chip_rows_4,chip_headers
    dw chip_memory
    db 0,7
    dw chip_rows_5,chip_headers
    dw chip_rom
    db 0,7
    dw chip_rows_6,chip_headers
chip_rows_0 db 5,6,7,8,9,10,11,12,13,14
chip_rows_1 db 5,6,7,8,9,10,11,12,13,14,15
chip_rows_2 db 5,6,7,8
chip_rows_3 db 5,6,7
chip_rows_4 db 5,6,7
chip_rows_5 db 5,6,7,8,9,10,11
chip_rows_6 db 5,6,7,8,9,10,11
chip_headers db 0
; Three DRAM waits, 3-2-2-2 cache burst, FPM, WB, no posting.
chipset_default db 0,DEFAULT_CACHE_ENABLED,1-DEFAULT_CACHE_ENABLED,(DEFAULT_CACHE_WRITE_BACK << 6),0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    times CHIP_SIZE-CHIP_OPTION_BYTES db 0
; Byte21 retains its old packed bit as opaque compatibility data.
chipset_masks db 0xF0,1,1,0x70,0x90,3,1,0xFF,0xFF,7,0x0F,0x7F,1,0x0F,1,0xFC,0xFF,0xFF,0x0F,1,0xFF,1,3,0x0F
    times CHIP_SIZE-CHIP_OPTION_BYTES db 0xFF
u_chip_menu db 'Chipset',0
u_chip_title db 'bAIos Setup > Chipset',0
u_chip_open db 'Open',0x1A,0
u_chip_help dw u_chip_menu,chip_read_help1,chip_wait_help
chip_memory db 'Memory',0
chip_cache db 'CPU and Cache',0
chip_bus db 'PCI Bus',0
chip_isa_bus db 'ISA Bus',0
chip_read db 'DRAM Read Waits',0
chip_read_help1 db 'Adds time for memory to return data.',0
chip_write db 'DRAM Write Waits',0
chip_write_help1 db 'Adds time for memory to store data.',0
chip_wait_help db 'Use the slowest timing until stability is proven.',0
chip_type db 'Memory Type',0
chip_type_help1 db 'Select FPM or EDO to match the installed memory.',0
chip_type_help2 db 'FPM is the conservative starting choice.',0
chip_edo_burst db 'EDO Read Burst',0
chip_edo_burst_help1 db 'Read timing used when EDO mode is active.',0
chip_refresh db 'DRAM Refresh',0
chip_refresh_help1 db 'Select how often memory is refreshed.',0
chip_refresh_help2 db 'Normal is recommended.',0
chip_parity db 'Memory Parity',0
chip_parity_help1 db 'Reports errors when parity memory is installed.',0
chip_parity_help2 db 'Leave disabled for non-parity SIMMs.',0
chip_l1 db 'Internal CPU Cache',0
chip_l1_help1 db 'Enables the cache inside the processor.',0
chip_l1_help2 db 'Enabled is recommended.',0
chip_l2 db 'External Cache',0
chip_l2_help1 db 'Enables the detected external cache.',0
chip_l2_help2 db 'Enabled is recommended after its check passes.',0
chip_policy db 'External Cache Policy',0
chip_policy_help1 db 'Select write-through or write-back operation.',0
chip_policy_help2 db 'Write-back is the normal default.',0
chip_burst db 'L2 Read Burst',0
chip_burst_help1 db 'Clock cycles for each word in a cache burst.',0
chip_early db 'Early Cache Write',0
chip_early_help1 db 'Selects the early cache write timing control.',0
chip_early_help2 db 'Leave disabled during initial testing.',0
chip_posted db 'CPU Posted Write Waits',0
chip_posted_help1 db 'Wait states for CPU writes sent to PCI devices.',0
chip_posted_help2 db '0 is faster; 1 is the conservative starting choice.',0
chip_pci_burst db 'CPU Burst Writes',0
chip_pci_burst_help1 db 'Groups consecutive writes to PCI devices.',0
chip_pci_burst_help2 db 'Disabled is the conservative starting choice.',0
chip_wait_values dw chip_wait_3,chip_wait_2,chip_wait_1,chip_wait_0
chip_wait_choices dw chip_wait_0,chip_wait_1,chip_wait_2,chip_wait_3
chip_wait_0 db '0',0
chip_wait_1 db '1',0
chip_wait_2 db '2',0
chip_wait_3 db '3',0
chip_enable_values dw u_disabled,u_on
chip_l2_values dw u_on,u_disabled
chip_type_values dw chip_type_fpm,chip_type_edo
chip_type_choices dw chip_type_edo,chip_type_fpm
chip_type_fpm db 'FPM',0
chip_type_edo db 'EDO',0
chip_refresh_values dw chip_refresh_normal,chip_refresh_slow
chip_refresh_normal db 'Normal',0
chip_refresh_slow db 'Slow',0
chip_policy_values dw chip_policy_wt,chip_policy_wb
chip_policy_choices dw chip_policy_wb,chip_policy_wt
chip_policy_wt db 'Write-Through',0
chip_policy_wb db 'Write-Back',0
chip_burst_values dw chip_burst_0,chip_burst_1,chip_burst_2,chip_burst_3
chip_burst_choices dw chip_burst_3,chip_burst_2,chip_burst_1,chip_burst_0
chip_burst_0 db '3-2-2-2',0
chip_burst_1 db '3-1-1-1',0
chip_burst_2 db '2-2-2-2',0
chip_burst_3 db '2-1-1-1',0
chip_edo_burst_values dw chip_edo_burst_0,chip_edo_burst_1
chip_edo_burst_choices dw chip_edo_burst_1,chip_edo_burst_0
chip_edo_burst_0 db '4-2-2-2',0
chip_edo_burst_1 db '3-1-1-1',0
chip_page_prefix db 'Page ',0
chip_page_slash db ' / ',0
chip_page_keys db 'PgUp/PgDn Page   F1 Help   F4/F5 Theme   F9 Defaults   F10 Save',0
chipset_group_titles dw chip_cache,chip_bus,chip_irqs,chip_local_bus,chip_isa_bus,chip_memory,chip_rom
chip_copyback db 'DRAM Burst Writes',0
chip_copyback_help1 db 'Allows consecutive cache writes back to memory.',0
chip_mem_lock db 'DRAM Resource Lock',0
chip_mem_lock_help1 db 'Selects the memory resource locking option.',0
chip_ldev db 'Local Device Sampling',0
chip_ldev_help1 db 'Selects when a local device response is sampled.',0
chip_turbo db 'Turbo Switch',0
chip_turbo_help1 db 'Allows the board turbo switch to select speed.',0
chip_turbo_help2 db 'Leave enabled for the normal board behavior.',0
chip_deturbo db 'Deturbo Speed',0
chip_deturbo_help1 db 'Speed ratio used when the board is in slow mode.',0
chip_deturbo_help2 db 'This does not change the normal CPU bus speed.',0
chip_pci_posted db 'PCI Posted Writes',0
chip_pci_posted_help1 db 'Buffers PCI memory writes through the bridge.',0
chip_devsel db 'PCI Device Response',0
chip_devsel_help1 db 'Selects how quickly the bridge claims a transfer.',0
chip_bus_lock db 'PCI Lock Method',0
chip_bus_lock_help1 db 'Locks the bus or the resource during access.',0
chip_park db 'PCI Bus Parking',0
chip_park_help1 db 'Lets a PCI master retain the bus while idle.',0
chip_preempt db 'PCI Master Preemption',0
chip_preempt_help1 db 'Allows a waiting master to request the PCI bus.',0
chip_pci_parity db 'PCI Parity Check',0
chip_pci_parity_help1 db 'Selects parity checking for PCI transfers.',0
chip_pci_parity_help2 db 'Keep the hardware choice unless testing parity.',0
chip_pci_clock db 'PCI Clock Ratio',0
chip_pci_clock_help1 db 'Selects the PCI clock relative to the CPU bus.',0
chip_isa_clock db 'ISA Clock Divider',0
chip_isa_help1 db 'Divides the PCI clock to produce the ISA clock.',0
chip_clock_help db 'Ratios use bus clocks, not the CPU multiplier.',0
chip_io_recovery db 'ISA I/O Recovery',0
chip_io_help1 db 'Adds ISA bus clocks between I/O transfers.',0
chip_io_help2 db '12 BCLK is the conservative starting choice.',0
chip_kbc_clock db 'Keyboard Clock',0
chip_kbc_help1 db 'Selects the keyboard controller clock source.',0
chip_keep_help db 'Keep Current preserves the hardware choice.',0
chip_keep db 'Keep Current',0
chip_keep_switch_values dw chip_keep,u_on,u_disabled
chip_keep_switch_choices dw u_disabled,u_on,chip_keep
chip_lock_values dw chip_keep,chip_lock_bus,chip_lock_resource
chip_lock_choices dw chip_lock_bus,chip_keep,chip_lock_resource
chip_lock_bus db 'Bus',0
chip_lock_resource db 'Resource',0
chip_ldev_values dw chip_keep,chip_ldev_2,chip_ldev_1
chip_ldev_choices dw chip_ldev_1,chip_ldev_2,chip_keep
chip_ldev_1 db '1 T2',0
chip_ldev_2 db '2 T2',0
chip_deturbo_values dw chip_div_3,chip_div_6
chip_div_3 db 'CPU / 3',0
chip_div_6 db 'CPU / 6',0
chip_devsel_values dw chip_keep,chip_fast,chip_medium,chip_slow
chip_devsel_choices dw chip_fast,chip_keep,chip_medium,chip_slow
chip_fast db 'Fast',0
chip_medium db 'Medium',0
chip_slow db 'Slow',0
chip_pci_clock_values dw chip_keep,chip_cpu_two_thirds,chip_cpu_half,chip_cpu_same
chip_pci_clock_choices dw chip_cpu_same,chip_cpu_half,chip_cpu_two_thirds,chip_keep
chip_cpu_same db 'CPU / 1',0
chip_cpu_half db 'CPU / 2',0
chip_cpu_two_thirds db 'CPU x 2/3',0
chip_isa_values dw chip_pci_4,chip_pci_3,chip_pci_2
chip_isa_choices dw chip_pci_2,chip_pci_3,chip_pci_4
chip_pci_2 db 'PCI / 2',0
chip_pci_3 db 'PCI / 3',0
chip_pci_4 db 'PCI / 4',0
chip_kbc_values dw chip_keep,chip_kbc_fixed,chip_pci_2,chip_pci_3,chip_pci_4
chip_kbc_choices dw chip_kbc_fixed,chip_keep,chip_pci_2,chip_pci_3,chip_pci_4
chip_kbc_fixed db '7.16 MHz',0
chip_recovery_values dw chip_io_12,chip_io_8,chip_io_4,chip_io_2
chip_recovery_choices dw chip_io_2,chip_io_4,chip_io_8,chip_io_12
chip_io_2 db '2 BCLK',0
chip_io_4 db '4 BCLK',0
chip_io_8 db '8 BCLK',0
chip_io_12 db '12 BCLK',0

chip_irqs db 'PCI Interrupts',0
chip_local_bus db 'Local Bus',0
chip_rom db 'ROM Shadow and Cache',0
chip_boot_speed db 'Boot CPU Speed',0
chip_speed_help1 db 'Starts the board in normal or slow speed mode.',0
chip_speed_help2 db 'High is recommended for normal use.',0
chip_boot_speed_values dw chip_high,chip_low
chip_high db 'High',0
chip_low db 'Low',0
chip_cyrix_linear db 'Cyrix Linear Burst',0
chip_linear_help1 db 'Enables linear cache bursts on a Cyrix 5x86.',0
chip_cyrix_lsser db 'Cyrix Load/Store Tuning',0
chip_lsser_help1 db 'Uses the AMI load/store setting on a Cyrix 5x86.',0
chip_cyrix_help db 'Other processors keep their own cache protocol.',0
chip_mapping db 'Device Number Mapping',0
chip_mapping_help1 db 'Selects the alternate device-number mapping.',0
chip_mapping_help2 db 'Leave disabled unless an expansion device needs it.',0
chip_palette db 'VGA Palette Snoop',0
chip_palette_help1 db 'Lets a second graphics device follow palette writes.',0
chip_palette_help2 db 'Leave disabled for a single graphics card.',0
chip_video_cache db 'Video BIOS Cacheable',0
chip_video_cache_help1 db 'Allows the copied video BIOS to use external cache.',0
chip_video_cache_help2 db 'Requires a working, enabled external cache.',0
chip_shadow_help1 db 'Copies this option ROM area into faster memory.',0
chip_shadow_help2 db 'Auto keeps copies required by discovered ROMs.',0
chip_shadow_values dw chip_auto,u_on
chip_auto db 'Auto',0
chip_shadow_c800 db 'C8000-CBFFF Shadow',0
chip_shadow_cc00 db 'CC000-CFFFF Shadow',0
chip_shadow_d000 db 'D0000-D3FFF Shadow',0
chip_shadow_d400 db 'D4000-D7FFF Shadow',0
chip_shadow_d800 db 'D8000-DBFFF Shadow',0
chip_shadow_dc00 db 'DC000-DFFFF Shadow',0
chip_irq_help1 db 'Assigns an interrupt to this PCI routing link.',0
chip_irq_help2 db 'Auto avoids the active onboard ISA devices.',0
chip_trigger_help1 db 'Trigger mode for PCI IDE cards using IRQ 14 or 15.',0
chip_trigger_help2 db 'Edge is recommended for legacy IDE operation.',0
chip_irq_1 db 'INTA Interrupt',0
chip_irq_2 db 'INTB Interrupt',0
chip_irq_3 db 'INTC Interrupt',0
chip_irq_4 db 'INTD Interrupt',0
chip_ide_trigger db 'PCI IDE IRQ Trigger',0
chip_trigger_values dw chip_edge,chip_level
chip_level db 'Level',0
chip_edge db 'Edge',0
chip_irq_values dw chip_auto,chip_irq4,chip_irq5,chip_irq7,chip_irq9,chip_irq10,chip_irq11,chip_irq12,chip_irq14,chip_irq15,chip_irq3,u_disabled
chip_irq_choices dw chip_irq3,chip_irq4,chip_irq5,chip_irq7,chip_irq9,chip_irq10,chip_irq11,chip_irq12,chip_irq14,chip_irq15,chip_auto,u_disabled
chip_irq3 db '3',0
chip_irq4 db '4',0
chip_irq5 db '5',0
chip_irq7 db '7',0
chip_irq9 db '9',0
chip_irq10 db '10',0
chip_irq11 db '11',0
chip_irq12 db '12',0
chip_irq14 db '14',0
chip_irq15 db '15',0

chip_posted_values dw chip_wait_1,chip_wait_0
chip_posted_choices dw chip_wait_0,chip_wait_1
