; Named fields decoded from V010B302 native Setup; hardware masks stay in chipset-core.
u_chip_menu db 'Chipset',0
mp_page_mode db 'Page Mode',0
mp_interleave db 'RAM Interleave',0
mp_board_controlled db 'Automatic',0
u_chip_title db 'bAIos Setup > Chipset',0
u_chip_open db 'Open',0x1A,0
u_chip_help dw u_chip_menu,mp_chip_help1,mp_chip_help2
mp_chip_help1 db 'Adjust bus, memory and ROM settings.',0
mp_chip_help2 db 'F9 restores defaults. Save applies after restart.',0
%macro mp_reverse_field 8
    dw %1
    db %2,%3,%4
    dw %5,%6,%7,%8
    db 1
%endmacro
mp_chip_group_0:
    chipset_field mp_bus_source,3,2,1,2,mp_values_bus_source,mp_bus_source_help1,mp_bus_source_help2
    chipset_field mp_bus_divisor,3,0,3,4,mp_values_bus_divisor,mp_bus_divisor_help1,mp_bus_divisor_help2
mp_trigger_descriptor:
    mp_reverse_field mp_trigger,2,7,1,2,mp_mid_end,mp_trigger_help1,mp_trigger_help2
    chipset_field mp_posted,2,6,1,2,mp_values_posted,mp_posted_help1,mp_posted_help2
mp_bale_descriptor:
    mp_reverse_field mp_bale,2,5,1,2,mp_values_bale,mp_bale_help1,mp_bale_help2
    chipset_field mp_wait8,2,0,3,4,mp_values_wait8,mp_wait8_help1,mp_wait8_help2
    chipset_field mp_wait16,2,2,3,4,mp_values_wait16,mp_wait16_help1,mp_wait16_help2
    chipset_field mp_dma_delay,4,4,3,4,mp_values_dma_delay,mp_dma_delay_help1,mp_dma_delay_help2
    chipset_field mp_dma_width,4,2,3,4,mp_values_dma_width,mp_dma_width_help1,mp_dma_width_help2
    chipset_field mp_dma_off,4,0,3,4,mp_values_dma_off,mp_dma_off_help1,mp_dma_off_help2
mp_chip_group_1:
    chipset_field mp_bank2_casras,12,3,3,4,mp_clk2_4,mp_bank2_casras_help1,mp_bank2_casras_help2
    chipset_field mp_bank2_colsetup,12,2,1,2,mp_clk2_2,mp_bank2_colsetup_help1,mp_bank2_colsetup_help2
    chipset_field mp_bank2_rowhold,12,1,1,2,mp_clk2_2,mp_bank2_rowhold_help1,mp_bank2_rowhold_help2
    chipset_field mp_bank2_caspre,12,0,1,2,mp_clk2_2,mp_bank2_caspre_help1,mp_bank2_caspre_help2
    chipset_field mp_bank2_caswidth,11,6,3,4,mp_clk2_4,mp_bank2_caswidth_help1,mp_bank2_caswidth_help2
    chipset_field mp_bank2_raspre,11,3,7,8,mp_clk2_8,mp_bank2_raspre_help1,mp_bank2_raspre_help2
    chipset_field mp_bank2_raswidth,11,0,7,8,mp_clk2_8,mp_bank2_raswidth_help1,mp_bank2_raswidth_help2
mp_chip_group_2:
    chipset_field mp_bank3_casras,14,3,3,4,mp_clk2_4,mp_bank3_casras_help1,mp_bank3_casras_help2
    chipset_field mp_bank3_colsetup,14,2,1,2,mp_clk2_2,mp_bank3_colsetup_help1,mp_bank3_colsetup_help2
    chipset_field mp_bank3_rowhold,14,1,1,2,mp_clk2_2,mp_bank3_rowhold_help1,mp_bank3_rowhold_help2
    chipset_field mp_bank3_caspre,14,0,1,2,mp_clk2_2,mp_bank3_caspre_help1,mp_bank3_caspre_help2
    chipset_field mp_bank3_caswidth,13,6,3,4,mp_clk2_4,mp_bank3_caswidth_help1,mp_bank3_caswidth_help2
    chipset_field mp_bank3_raspre,13,3,7,8,mp_clk2_8,mp_bank3_raspre_help1,mp_bank3_raspre_help2
    chipset_field mp_bank3_raswidth,13,0,7,8,mp_clk2_8,mp_bank3_raswidth_help1,mp_bank3_raswidth_help2
mp_chip_group_3:
    chipset_field mp_bank4_casras,16,3,3,4,mp_clk2_4,mp_bank4_casras_help1,mp_bank4_casras_help2
    chipset_field mp_bank4_colsetup,16,2,1,2,mp_clk2_2,mp_bank4_colsetup_help1,mp_bank4_colsetup_help2
    chipset_field mp_bank4_rowhold,16,1,1,2,mp_clk2_2,mp_bank4_rowhold_help1,mp_bank4_rowhold_help2
    chipset_field mp_bank4_caspre,16,0,1,2,mp_clk2_2,mp_bank4_caspre_help1,mp_bank4_caspre_help2
    chipset_field mp_bank4_caswidth,15,6,3,4,mp_clk2_4,mp_bank4_caswidth_help1,mp_bank4_caswidth_help2
    chipset_field mp_bank4_raspre,15,3,7,8,mp_clk2_8,mp_bank4_raspre_help1,mp_bank4_raspre_help2
    chipset_field mp_bank4_raswidth,15,0,7,8,mp_clk2_8,mp_bank4_raswidth_help1,mp_bank4_raswidth_help2
mp_chip_group_4:
    chipset_field mp_bank5_casras,18,3,3,4,mp_clk2_4,mp_bank5_casras_help1,mp_bank5_casras_help2
    chipset_field mp_bank5_colsetup,18,2,1,2,mp_clk2_2,mp_bank5_colsetup_help1,mp_bank5_colsetup_help2
    chipset_field mp_bank5_rowhold,18,1,1,2,mp_clk2_2,mp_bank5_rowhold_help1,mp_bank5_rowhold_help2
    chipset_field mp_bank5_caspre,18,0,1,2,mp_clk2_2,mp_bank5_caspre_help1,mp_bank5_caspre_help2
    chipset_field mp_bank5_caswidth,17,6,3,4,mp_clk2_4,mp_bank5_caswidth_help1,mp_bank5_caswidth_help2
    chipset_field mp_bank5_raspre,17,3,7,8,mp_clk2_8,mp_bank5_raspre_help1,mp_bank5_raspre_help2
    chipset_field mp_bank5_raswidth,17,0,7,8,mp_clk2_8,mp_bank5_raswidth_help1,mp_bank5_raswidth_help2
mp_chip_group_5:
    chipset_field mp_refresh,5,0,3,4,mp_values_refresh,mp_refresh_help1,mp_refresh_help2
mp_rcap_descriptor:
    mp_reverse_field mp_rcap,6,6,1,2,mp_mid_end,mp_rcap_help1,mp_rcap_help2
mp_write_timing_descriptor:
    mp_reverse_field mp_write_timing,6,5,1,2,mp_mid_end,mp_write_timing_help1,mp_write_timing_help2
mp_address_edge_descriptor:
    mp_reverse_field mp_address_edge,6,4,1,2,mp_values_address_edge,mp_address_edge_help1,mp_address_edge_help2
    chipset_field mp_shadow,1,0,1,2,mp_values_shadow,mp_shadow_help1,mp_shadow_help2
mp_chip_group_6:
    chipset_field mp_bank0_casras,8,3,3,4,mp_clk2_4,mp_bank0_casras_help1,mp_bank0_casras_help2
    chipset_field mp_bank0_colsetup,8,2,1,2,mp_clk2_2,mp_bank0_colsetup_help1,mp_bank0_colsetup_help2
    chipset_field mp_bank0_rowhold,8,1,1,2,mp_clk2_2,mp_bank0_rowhold_help1,mp_bank0_rowhold_help2
    chipset_field mp_bank0_caspre,8,0,1,2,mp_clk2_2,mp_bank0_caspre_help1,mp_bank0_caspre_help2
    chipset_field mp_bank0_caswidth,7,6,3,4,mp_clk2_4,mp_bank0_caswidth_help1,mp_bank0_caswidth_help2
    chipset_field mp_bank0_raspre,7,3,7,8,mp_clk2_8,mp_bank0_raspre_help1,mp_bank0_raspre_help2
    chipset_field mp_bank0_raswidth,7,0,7,8,mp_clk2_8,mp_bank0_raswidth_help1,mp_bank0_raswidth_help2
mp_chip_group_7:
    chipset_field mp_bank1_casras,10,3,3,4,mp_clk2_4,mp_bank1_casras_help1,mp_bank1_casras_help2
    chipset_field mp_bank1_colsetup,10,2,1,2,mp_clk2_2,mp_bank1_colsetup_help1,mp_bank1_colsetup_help2
    chipset_field mp_bank1_rowhold,10,1,1,2,mp_clk2_2,mp_bank1_rowhold_help1,mp_bank1_rowhold_help2
    chipset_field mp_bank1_caspre,10,0,1,2,mp_clk2_2,mp_bank1_caspre_help1,mp_bank1_caspre_help2
    chipset_field mp_bank1_caswidth,9,6,3,4,mp_clk2_4,mp_bank1_caswidth_help1,mp_bank1_caswidth_help2
    chipset_field mp_bank1_raspre,9,3,7,8,mp_clk2_8,mp_bank1_raspre_help1,mp_bank1_raspre_help2
    chipset_field mp_bank1_raswidth,9,0,7,8,mp_clk2_8,mp_bank1_raswidth_help1,mp_bank1_raswidth_help2
%unmacro mp_reverse_field 8
CHIP_GROUP_COUNT equ 8
; Navigation follows hardware grouping; option values retain their sorted order.
chipset_groups dw mp_chip_group_0,mp_chip_group_5,mp_chip_group_6,mp_chip_group_7,mp_chip_group_1,mp_chip_group_2,mp_chip_group_3,mp_chip_group_4
chipset_group_counts db 10,5,7,7,7,7,7,7
chipset_group_titles dw mp_chip_title_0,mp_chip_title_5,mp_chip_title_6,mp_chip_title_7,mp_chip_title_1,mp_chip_title_2,mp_chip_title_3,mp_chip_title_4
chipset_group_help:
    dw mp_chip_title_0,mp_chip_help1,mp_chip_help2
    dw mp_chip_title_5,mp_chip_help1,mp_chip_help2
    dw mp_chip_title_6,mp_chip_help1,mp_chip_help2
    dw mp_chip_title_7,mp_chip_help1,mp_chip_help2
    dw mp_chip_title_1,mp_chip_help1,mp_chip_help2
    dw mp_chip_title_2,mp_chip_help1,mp_chip_help2
    dw mp_chip_title_3,mp_chip_help1,mp_chip_help2
    dw mp_chip_title_4,mp_chip_help1,mp_chip_help2
chipset_first_view db 0,5,6,7,1,2,3,4
chipset_view_counts db 1,1,1,1,1,1,1,1
chipset_views:
    dw mp_chip_title_0
    db 0,10
    dw mp_chip_rows,mp_chip_headers
    dw mp_chip_title_1
    db 0,7
    dw mp_chip_rows,mp_chip_headers
    dw mp_chip_title_2
    db 0,7
    dw mp_chip_rows,mp_chip_headers
    dw mp_chip_title_3
    db 0,7
    dw mp_chip_rows,mp_chip_headers
    dw mp_chip_title_4
    db 0,7
    dw mp_chip_rows,mp_chip_headers
    dw mp_chip_title_5
    db 0,5
    dw mp_chip_rows,mp_chip_headers
    dw mp_chip_title_6
    db 0,7
    dw mp_chip_rows,mp_chip_headers
    dw mp_chip_title_7
    db 0,7
    dw mp_chip_rows,mp_chip_headers
mp_chip_rows db 5,6,7,8,9,10,11,12,13,14
mp_chip_headers db 0
mp_values_bus_source dw mp_values_bus_source_0,mp_values_bus_source_1
mp_values_bus_divisor dw mp_values_bus_divisor_0,mp_values_bus_divisor_1,mp_values_bus_divisor_2,mp_values_bus_divisor_3
mp_mid_end dw mp_mid_end_0,mp_mid_end_1
    dw mp_mid_end_1,mp_mid_end_0
mp_values_posted dw mp_values_posted_0,mp_values_posted_1
mp_values_bale dw mp_values_bale_0,mp_values_bale_1
    dw mp_values_bale_1,mp_values_bale_0
mp_values_wait8 dw mp_values_wait8_0,mp_values_wait8_1,mp_values_wait8_2,mp_values_wait8_3
mp_values_wait16 dw mp_values_wait16_0,mp_values_wait16_1,mp_values_wait16_2,mp_values_wait16_3
mp_values_dma_delay dw mp_values_dma_delay_0,mp_values_dma_delay_1,mp_values_dma_delay_2,mp_values_dma_delay_3
mp_values_dma_width dw mp_values_dma_width_0,mp_values_dma_width_1,mp_values_dma_width_2,mp_values_dma_width_3
mp_values_dma_off dw mp_values_dma_off_0,mp_values_dma_off_1,mp_values_dma_off_2,mp_values_dma_off_3
mp_values_refresh dw mp_values_refresh_0,mp_values_refresh_1,mp_values_refresh_2,mp_values_refresh_3
mp_values_address_edge dw mp_values_address_edge_0,mp_values_address_edge_1
    dw mp_values_address_edge_1,mp_values_address_edge_0
mp_values_shadow dw mp_values_shadow_0,mp_values_shadow_1
mp_clk2_4 dw mp_clk2_4_0,mp_clk2_4_1,mp_clk2_4_2,mp_clk2_4_3
mp_clk2_2 dw mp_clk2_2_0,mp_clk2_2_1
mp_clk2_8 dw mp_clk2_8_0,mp_clk2_8_1,mp_clk2_8_2,mp_clk2_8_3,mp_clk2_8_4,mp_clk2_8_5,mp_clk2_8_6,mp_clk2_8_7
mp_bus_source db 'Bus Clock Source',0
mp_bus_source_help1 db 'Select the source for the bus clock.',0
mp_bus_source_help2 db 'Use CLK1 with the normal board configuration.',0
mp_bus_divisor db 'Bus Clock Divider',0
mp_bus_divisor_help1 db 'Divide the selected bus clock by this value.',0
mp_bus_divisor_help2 db 'Default follows the board clock switch.',0
mp_trigger db 'Bus Trigger',0
mp_trigger_help1 db 'Choose when a bus transfer starts.',0
mp_trigger_help2 db 'Default End. Keep it unless testing bus timing.',0
mp_posted db 'Posted Writes',0
mp_posted_help1 db 'Let the processor continue during a bus write.',0
mp_posted_help2 db 'Default Disabled. Some cards need this delay.',0
mp_bale db 'BALE Width',0
mp_bale_help1 db 'Set how long the bus address latch stays active.',0
mp_bale_help2 db 'Default 0.5 clock. Longer can help older cards.',0
mp_wait8 db '8-bit Bus Wait',0
mp_wait8_help1 db 'Set the wait for an 8-bit bus transfer.',0
mp_wait8_help2 db 'Default 4 clocks. More waits give cards more time.',0
mp_wait16 db '16-bit Bus Wait',0
mp_wait16_help1 db 'Set the wait for a 16-bit bus transfer.',0
mp_wait16_help2 db 'Default 2 clocks. More waits give cards more time.',0
mp_dma_delay db 'DMA Delay',0
mp_dma_delay_help1 db 'Wait before a direct memory transfer starts.',0
mp_dma_delay_help2 db 'SCLK is one bus clock. Default 2 SCLK.',0
mp_dma_width db 'DMA Width',0
mp_dma_width_help1 db 'Set the active time for a direct memory transfer.',0
mp_dma_width_help2 db 'SCLK is one bus clock. Default 4 SCLK.',0
mp_dma_off db 'DMA Recovery',0
mp_dma_off_help1 db 'Wait between direct memory transfers.',0
mp_dma_off_help2 equ mp_dma_delay_help2
mp_refresh db 'Refresh Period',0
mp_refresh_help1 db 'Choose the time between memory refreshes.',0
mp_refresh_help2 db 'Default 15 us. Longer needs compatible RAM.',0
mp_rcap db 'Read Address Timing',0
mp_rcap_help1 db 'Choose when the RAM read address is latched.',0
mp_rcap_help2 db 'Default End. Changing it can cause RAM errors.',0
mp_write_timing db 'Write Timing',0
mp_write_timing_help1 db 'Choose when the RAM write cycle starts.',0
mp_write_timing_help2 db 'Default Mid. Changing it can cause RAM errors.',0
mp_address_edge db 'RAM Address Edge',0
mp_address_edge_help1 db 'Choose the clock edge used for the RAM address.',0
mp_address_edge_help2 db 'Default Rise. Changing it can cause RAM errors.',0
mp_shadow db 'System ROM Shadow',0
mp_shadow_help1 db 'Copy the system BIOS to RAM for faster access.',0
mp_shadow_help2 db 'Default Enabled. Disable to run from the ROM.',0
mp_bank0_casras db 'CAS to RAS',0
mp_bank0_casras_help1 db 'Wait between the column and row strobes.',0
mp_bank0_casras_help2 db 'Default 3 CLK2. CLK2 is one memory clock step.',0
mp_bank0_colsetup db 'Column Address Setup',0
mp_bank0_colsetup_help1 db 'Time to hold the column address before use.',0
mp_bank0_colsetup_help2 db 'Default 1 CLK2. CLK2 is one memory clock step.',0
mp_bank0_rowhold db 'Row Address Hold',0
mp_bank0_rowhold_help1 db 'Time to keep the RAM row address stable.',0
mp_bank0_rowhold_help2 equ mp_bank0_colsetup_help2
mp_bank0_caspre db 'CAS Precharge',0
mp_bank0_caspre_help1 db 'Wait between column access pulses.',0
mp_bank0_caspre_help2 equ mp_bank0_colsetup_help2
mp_bank0_caswidth db 'CAS Width',0
mp_bank0_caswidth_help1 db 'Set the length of a column access pulse.',0
mp_bank0_caswidth_help2 db 'Default 4 CLK2. CLK2 is one memory clock step.',0
mp_bank0_raspre db 'RAS Precharge',0
mp_bank0_raspre_help1 db 'Wait before opening another RAM row.',0
mp_bank0_raspre_help2 db 'Default 5 CLK2. CLK2 is one memory clock step.',0
mp_bank0_raswidth db 'RAS Width',0
mp_bank0_raswidth_help1 db 'Set how long a RAM row stays active.',0
mp_bank0_raswidth_help2 equ mp_bank0_raspre_help2
mp_bank1_casras equ mp_bank0_casras
mp_bank1_casras_help1 equ mp_bank0_casras_help1
mp_bank1_casras_help2 equ mp_bank0_casras_help2
mp_bank1_colsetup equ mp_bank0_colsetup
mp_bank1_colsetup_help1 equ mp_bank0_colsetup_help1
mp_bank1_colsetup_help2 equ mp_bank0_colsetup_help2
mp_bank1_rowhold equ mp_bank0_rowhold
mp_bank1_rowhold_help1 equ mp_bank0_rowhold_help1
mp_bank1_rowhold_help2 equ mp_bank0_colsetup_help2
mp_bank1_caspre equ mp_bank0_caspre
mp_bank1_caspre_help1 equ mp_bank0_caspre_help1
mp_bank1_caspre_help2 equ mp_bank0_colsetup_help2
mp_bank1_caswidth equ mp_bank0_caswidth
mp_bank1_caswidth_help1 equ mp_bank0_caswidth_help1
mp_bank1_caswidth_help2 equ mp_bank0_caswidth_help2
mp_bank1_raspre equ mp_bank0_raspre
mp_bank1_raspre_help1 equ mp_bank0_raspre_help1
mp_bank1_raspre_help2 equ mp_bank0_raspre_help2
mp_bank1_raswidth equ mp_bank0_raswidth
mp_bank1_raswidth_help1 equ mp_bank0_raswidth_help1
mp_bank1_raswidth_help2 equ mp_bank0_raspre_help2
mp_bank2_casras equ mp_bank0_casras
mp_bank2_casras_help1 equ mp_bank0_casras_help1
mp_bank2_casras_help2 equ mp_bank0_casras_help2
mp_bank2_colsetup equ mp_bank0_colsetup
mp_bank2_colsetup_help1 equ mp_bank0_colsetup_help1
mp_bank2_colsetup_help2 db 'Default 2 CLK2. CLK2 is one memory clock step.',0
mp_bank2_rowhold equ mp_bank0_rowhold
mp_bank2_rowhold_help1 equ mp_bank0_rowhold_help1
mp_bank2_rowhold_help2 equ mp_bank2_colsetup_help2
mp_bank2_caspre equ mp_bank0_caspre
mp_bank2_caspre_help1 equ mp_bank0_caspre_help1
mp_bank2_caspre_help2 equ mp_bank0_colsetup_help2
mp_bank2_caswidth equ mp_bank0_caswidth
mp_bank2_caswidth_help1 equ mp_bank0_caswidth_help1
mp_bank2_caswidth_help2 equ mp_bank0_caswidth_help2
mp_bank2_raspre equ mp_bank0_raspre
mp_bank2_raspre_help1 equ mp_bank0_raspre_help1
mp_bank2_raspre_help2 equ mp_bank0_raspre_help2
mp_bank2_raswidth equ mp_bank0_raswidth
mp_bank2_raswidth_help1 equ mp_bank0_raswidth_help1
mp_bank2_raswidth_help2 equ mp_bank0_raspre_help2
mp_bank3_casras equ mp_bank0_casras
mp_bank3_casras_help1 equ mp_bank0_casras_help1
mp_bank3_casras_help2 equ mp_bank0_casras_help2
mp_bank3_colsetup equ mp_bank0_colsetup
mp_bank3_colsetup_help1 equ mp_bank0_colsetup_help1
mp_bank3_colsetup_help2 equ mp_bank2_colsetup_help2
mp_bank3_rowhold equ mp_bank0_rowhold
mp_bank3_rowhold_help1 equ mp_bank0_rowhold_help1
mp_bank3_rowhold_help2 equ mp_bank2_colsetup_help2
mp_bank3_caspre equ mp_bank0_caspre
mp_bank3_caspre_help1 equ mp_bank0_caspre_help1
mp_bank3_caspre_help2 equ mp_bank0_colsetup_help2
mp_bank3_caswidth equ mp_bank0_caswidth
mp_bank3_caswidth_help1 equ mp_bank0_caswidth_help1
mp_bank3_caswidth_help2 equ mp_bank0_caswidth_help2
mp_bank3_raspre equ mp_bank0_raspre
mp_bank3_raspre_help1 equ mp_bank0_raspre_help1
mp_bank3_raspre_help2 equ mp_bank0_raspre_help2
mp_bank3_raswidth equ mp_bank0_raswidth
mp_bank3_raswidth_help1 equ mp_bank0_raswidth_help1
mp_bank3_raswidth_help2 equ mp_bank0_raspre_help2
mp_bank4_casras equ mp_bank0_casras
mp_bank4_casras_help1 equ mp_bank0_casras_help1
mp_bank4_casras_help2 equ mp_bank0_casras_help2
mp_bank4_colsetup equ mp_bank0_colsetup
mp_bank4_colsetup_help1 equ mp_bank0_colsetup_help1
mp_bank4_colsetup_help2 equ mp_bank2_colsetup_help2
mp_bank4_rowhold equ mp_bank0_rowhold
mp_bank4_rowhold_help1 equ mp_bank0_rowhold_help1
mp_bank4_rowhold_help2 equ mp_bank2_colsetup_help2
mp_bank4_caspre equ mp_bank0_caspre
mp_bank4_caspre_help1 equ mp_bank0_caspre_help1
mp_bank4_caspre_help2 equ mp_bank0_colsetup_help2
mp_bank4_caswidth equ mp_bank0_caswidth
mp_bank4_caswidth_help1 equ mp_bank0_caswidth_help1
mp_bank4_caswidth_help2 equ mp_bank0_caswidth_help2
mp_bank4_raspre equ mp_bank0_raspre
mp_bank4_raspre_help1 equ mp_bank0_raspre_help1
mp_bank4_raspre_help2 equ mp_bank0_raspre_help2
mp_bank4_raswidth equ mp_bank0_raswidth
mp_bank4_raswidth_help1 equ mp_bank0_raswidth_help1
mp_bank4_raswidth_help2 equ mp_bank0_raspre_help2
mp_bank5_casras equ mp_bank0_casras
mp_bank5_casras_help1 equ mp_bank0_casras_help1
mp_bank5_casras_help2 equ mp_bank0_casras_help2
mp_bank5_colsetup equ mp_bank0_colsetup
mp_bank5_colsetup_help1 equ mp_bank0_colsetup_help1
mp_bank5_colsetup_help2 equ mp_bank2_colsetup_help2
mp_bank5_rowhold equ mp_bank0_rowhold
mp_bank5_rowhold_help1 equ mp_bank0_rowhold_help1
mp_bank5_rowhold_help2 equ mp_bank2_colsetup_help2
mp_bank5_caspre equ mp_bank0_caspre
mp_bank5_caspre_help1 equ mp_bank0_caspre_help1
mp_bank5_caspre_help2 equ mp_bank0_colsetup_help2
mp_bank5_caswidth equ mp_bank0_caswidth
mp_bank5_caswidth_help1 equ mp_bank0_caswidth_help1
mp_bank5_caswidth_help2 equ mp_bank0_caswidth_help2
mp_bank5_raspre equ mp_bank0_raspre
mp_bank5_raspre_help1 equ mp_bank0_raspre_help1
mp_bank5_raspre_help2 equ mp_bank0_raspre_help2
mp_bank5_raswidth equ mp_bank0_raswidth
mp_bank5_raswidth_help1 equ mp_bank0_raswidth_help1
mp_bank5_raswidth_help2 equ mp_bank0_raspre_help2
mp_chip_title_0 db 'Bus and DMA',0
mp_chip_title_1 db 'Expansion Bank 1',0
mp_chip_title_2 db 'Expansion Bank 2',0
mp_chip_title_3 db 'Expansion Bank 3',0
mp_chip_title_4 db 'Expansion Bank 4',0
mp_chip_title_5 db 'Memory and ROM',0
mp_chip_title_6 db 'Onboard Bank 1',0
mp_chip_title_7 db 'Onboard Bank 2',0
mp_values_bus_source_0 db 'CLK0',0
mp_values_bus_source_1 db 'CLK1',0
mp_values_bus_divisor_0 db '/1',0
mp_values_bus_divisor_1 db '/2',0
mp_values_bus_divisor_2 db '/3',0
mp_values_bus_divisor_3 db '/4',0
mp_mid_end_0 db 'Mid',0
mp_mid_end_1 db 'End',0
mp_values_posted_0 db 'Disabled',0
mp_values_posted_1 db 'Enabled',0
mp_values_bale_0 db '1 clock',0
mp_values_bale_1 db '0.5 clock',0
mp_values_wait8_0 db '4 clocks',0
mp_values_wait8_1 db '5 clocks',0
mp_values_wait8_2 db '6 clocks',0
mp_values_wait8_3 db '7 clocks',0
mp_values_wait16_0 db '1 clocks',0
mp_values_wait16_1 db '2 clocks',0
mp_values_wait16_2 db '3 clocks',0
mp_values_wait16_3 equ mp_values_wait8_0
mp_values_dma_delay_0 db '1 SCLK',0
mp_values_dma_delay_1 db '2 SCLK',0
mp_values_dma_delay_2 db '3 SCLK',0
mp_values_dma_delay_3 db '4 SCLK',0
mp_values_dma_width_0 equ mp_values_dma_delay_1
mp_values_dma_width_1 equ mp_values_dma_delay_3
mp_values_dma_width_2 db '6 SCLK',0
mp_values_dma_width_3 db '8 SCLK',0
mp_values_dma_off_0 equ mp_values_dma_delay_0
mp_values_dma_off_1 equ mp_values_dma_delay_1
mp_values_dma_off_2 equ mp_values_dma_delay_2
mp_values_dma_off_3 equ mp_values_dma_delay_3
mp_values_refresh_0 db '7.5 us',0
mp_values_refresh_1 db '15 us',0
mp_values_refresh_2 db '30 us',0
mp_values_refresh_3 db '60 us',0
mp_values_address_edge_0 db 'Rise',0
mp_values_address_edge_1 db 'Fall',0
mp_values_shadow_0 equ mp_values_posted_0
mp_values_shadow_1 equ mp_values_posted_1
mp_clk2_4_0 db '1 CLK2',0
mp_clk2_4_1 db '2 CLK2',0
mp_clk2_4_2 db '3 CLK2',0
mp_clk2_4_3 db '4 CLK2',0
mp_clk2_2_0 equ mp_clk2_4_0
mp_clk2_2_1 equ mp_clk2_4_1
mp_clk2_8_0 equ mp_clk2_4_0
mp_clk2_8_1 equ mp_clk2_4_1
mp_clk2_8_2 equ mp_clk2_4_2
mp_clk2_8_3 equ mp_clk2_4_3
mp_clk2_8_4 db '5 CLK2',0
mp_clk2_8_5 db '6 CLK2',0
mp_clk2_8_6 db '7 CLK2',0
mp_clk2_8_7 db '8 CLK2',0
chip_page_prefix db 'Page ',0
chip_page_slash db ' / ',0
chip_page_keys db 'Esc Back   F1 Help   F9 Defaults   F10 Save',0
