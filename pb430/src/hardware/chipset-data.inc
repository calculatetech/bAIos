u_chip_menu db 'Chipset',0
u_chip_title db 'bAIos Setup > Chipset',0
u_chip_open db 'Open',0x1A,0
u_chip_help dw u_chip_menu,u_chip_help1,u_chip_help2
u_chip_help1 db 'Tune memory, cache, refresh and ROM settings.',0
u_chip_help2 db 'F9 loads defaults. Save applies after restart.',0
chip_group_0:
    chipset_field acc_field_0,0,0,1,2,acc_values_0,acc_field_0_help1,acc_field_0_help2
    chipset_field acc_field_1,1,0,1,2,acc_values_1,acc_field_1_help1,acc_field_1_help2
    chipset_field acc_field_2,2,0,1,2,acc_values_1,acc_field_2_help1,acc_field_2_help2
    chipset_field acc_field_3,3,0,1,2,acc_values_1,acc_field_3_help1,acc_field_3_help2
    chipset_field acc_field_4,4,0,1,2,acc_values_1,acc_field_4_help1,acc_field_4_help2
    chipset_field acc_field_5,5,0,1,2,acc_values_1,acc_field_5_help1,acc_field_5_help2
chip_group_1:
    chipset_field acc_field_8,14,0,3,3,acc_values_3,acc_field_8_help1,acc_field_8_help2
    chipset_field acc_field_9,9,0,1,2,acc_values_4,acc_field_9_help1,acc_field_9_help2
    chipset_field acc_field_10,15,6,3,4,acc_values_5,acc_field_10_help1,acc_field_10_help2
    chipset_field acc_field_11,16,7,1,2,acc_values_6,acc_field_11_help1,acc_field_11_help2
    chipset_field acc_field_12,15,5,1,2,acc_values_6,acc_field_12_help1,acc_field_12_help2
    chipset_field acc_field_13,15,2,3,4,acc_values_7,acc_field_13_help1,acc_field_13_help2
    chipset_field acc_field_14,15,0,3,4,acc_values_7,acc_field_14_help1,acc_field_14_help2
    chipset_field acc_field_15,16,6,1,2,acc_values_8,acc_field_15_help1,acc_field_15_help2
    chipset_field acc_field_16,15,4,1,2,acc_values_9,acc_field_16_help1,acc_field_16_help2
    chipset_field acc_field_17,18,0,1,2,acc_values_10,acc_field_17_help1,acc_field_17_help2
    chipset_field acc_field_18,18,1,1,2,acc_values_10,acc_field_18_help1,acc_field_18_help2
chip_group_2:
    chipset_field acc_field_20,21,3,1,2,acc_values_1,acc_field_20_help1,acc_field_20_help2
    chipset_field acc_field_25,19,7,1,2,acc_values_1,acc_field_25_help1,acc_field_25_help2
    chipset_field acc_field_46,22,1,1,2,acc_values_1,acc_field_46_help1,acc_field_46_help2
    chipset_field acc_field_47,22,2,1,2,acc_values_1,acc_field_47_help1,acc_field_47_help2
    chipset_field acc_field_21,21,5,1,2,acc_values_11,acc_field_21_help1,acc_field_21_help2
    chipset_field acc_field_22,21,6,1,2,acc_values_12,acc_field_22_help1,acc_field_22_help2
    chipset_field acc_field_24,17,6,1,2,acc_values_1,acc_field_24_help1,acc_field_24_help2
    chipset_field acc_field_26,19,5,1,2,acc_values_1,acc_field_26_help1,acc_field_26_help2
    chipset_field acc_field_27,19,4,1,2,acc_values_1,acc_field_27_help1,acc_field_27_help2
    chipset_field acc_field_19,21,4,1,2,acc_values_1,acc_field_19_help1,acc_field_19_help2
chip_group_3:
    chipset_field acc_field_28,7,0,3,4,acc_values_2,acc_field_28_help1,acc_field_28_help2
    chipset_field acc_field_32,19,1,1,2,acc_values_1,acc_field_32_help1,acc_field_32_help2
    chipset_field acc_field_29,20,6,3,4,acc_values_13,acc_field_29_help1,acc_field_29_help2
    chipset_field acc_field_30,20,4,3,4,acc_values_14,acc_field_30_help1,acc_field_30_help2
    chipset_field acc_field_31,20,0,7,8,acc_values_15,acc_field_31_help1,acc_field_31_help2
    chipset_field acc_field_48,22,3,1,2,acc_values_1,acc_field_48_help1,acc_field_48_help2
chip_group_4:
    chipset_field acc_isa_clock,22,4,7,8,acc_isa_values,acc_isa_help1,acc_isa_help2
    chipset_field acc_field_35,17,4,1,2,acc_values_1,acc_field_35_help1,acc_field_35_help2
    chipset_field acc_field_36,17,3,1,2,acc_values_1,acc_field_36_help1,acc_field_36_help2
    chipset_field acc_field_37,19,6,1,2,acc_values_1,acc_field_37_help1,acc_field_37_help2
    chipset_field acc_field_38,18,4,1,2,acc_values_1,acc_field_38_help1,acc_field_38_help2
chip_group_5:
    chipset_field acc_field_39,3,0,1,2,acc_values_1,acc_field_39_help1,acc_field_39_help2
    chipset_field acc_field_40,4,0,1,2,acc_values_1,acc_field_40_help1,acc_field_40_help2
    chipset_field acc_field_41,10,0,1,2,acc_values_1,acc_field_41_help1,acc_field_41_help2
    chipset_field acc_field_42,11,0,1,2,acc_values_1,acc_field_42_help1,acc_field_42_help2
    chipset_field acc_field_43,12,0,1,2,acc_values_1,acc_field_43_help1,acc_field_43_help2
    chipset_field acc_field_44,13,0,1,2,acc_values_4,acc_field_44_help1,acc_field_44_help2
    chipset_field acc_field_45,22,0,1,2,acc_values_4,acc_field_45_help1,acc_field_45_help2
chip_fields_end:
CHIP_FIELD_COUNT equ 45
CHIP_GROUP_COUNT equ 6
chipset_groups:
    dw chip_group_0,chip_group_1,chip_group_2,chip_group_3,chip_group_4,chip_group_5
chipset_group_counts:
    db 6,11,10,6,5,7
chipset_group_titles dw acc_group_0,acc_group_1,acc_group_2,acc_group_3,acc_group_4,acc_group_5
chipset_group_help:
    dw acc_group_0,u_chip_help1,u_chip_help2
    dw acc_group_1,u_chip_help1,u_chip_help2
    dw acc_group_2,u_chip_help1,u_chip_help2
    dw acc_group_3,u_chip_help1,u_chip_help2
    dw acc_group_4,u_chip_help1,u_chip_help2
    dw acc_group_5,u_chip_help1,u_chip_help2
chipset_first_view db 0,1,2,3,4,5
chipset_view_counts db 1,1,1,1,1,1
chipset_views:
    dw acc_group_0
    db 0,6
    dw acc_rows,acc_headers
    dw acc_group_1
    db 0,11
    dw acc_rows,acc_headers
    dw acc_group_2
    db 0,10
    dw acc_rows,acc_headers
    dw acc_group_3
    db 0,6
    dw acc_rows,acc_headers
    dw acc_group_4
    db 0,5
    dw acc_rows,acc_headers
    dw acc_group_5
    db 0,7
    dw acc_rows,acc_headers
acc_rows db 5,6,7,8,9,10,11,12,13,14,15
acc_headers db 0
acc_group_0 db 'General',0
acc_group_1 db 'RAM Timing',0
acc_group_2 db 'Cache and Memory',0
acc_group_3 db 'Refresh',0
acc_group_4 db 'Bus and ROM Timing',0
acc_group_5 db 'Shadow',0
acc_values_0 dw acc_values_0_0,acc_values_0_1
acc_values_0_0 db 'Auto',0
acc_values_0_1 db 'Manual',0
acc_values_1 dw acc_values_1_0,acc_values_1_1
acc_values_1_0 db 'Disabled',0
acc_values_1_1 db 'Enabled',0
acc_values_2 dw acc_values_2_0,acc_values_2_1,acc_values_2_2,acc_values_2_3
acc_values_2_0 db '15 us (Normal)',0
acc_values_2_1 db '120 us (Slow)',0
acc_values_2_2 db '30 us',0
acc_values_2_3 db '60 us',0
acc_values_3 dw acc_values_3_0,acc_values_3_1,acc_values_3_2
acc_values_3_0 db 'Normal',0
acc_values_3_1 db 'Fast',0
acc_values_3_2 db 'Manual',0
acc_values_4 dw acc_values_4_0,acc_values_4_1
acc_values_4_0 db 'Enabled',0
acc_values_4_1 db 'Disabled',0
acc_values_5 dw acc_values_5_0,acc_values_5_1,acc_values_5_2,acc_values_5_3
acc_values_5_0 db '2T',0
acc_values_5_1 db '3T',0
acc_values_5_2 db '4T',0
acc_values_5_3 db '5T',0
acc_values_6 dw acc_values_6_0,acc_values_6_1
acc_values_6_0 db '2T',0
acc_values_6_1 db '3T',0
acc_values_7 dw acc_values_7_0,acc_values_7_1,acc_values_7_2,acc_values_7_3
acc_values_7_0 db '1T',0
acc_values_7_1 db '2T',0
acc_values_7_2 db '3T',0
acc_values_7_3 db '4T',0
acc_values_8 dw acc_values_8_0,acc_values_8_1
acc_values_8_0 db '1T',0
acc_values_8_1 db '2T',0
acc_values_9 dw acc_values_9_0,acc_values_9_1
acc_values_9_0 db '1T',0
acc_values_9_1 db '2T',0
acc_values_10 dw acc_values_10_0,acc_values_10_1
acc_values_10_0 db 'Normal',0
acc_values_10_1 db 'Earlier',0
acc_values_11 dw acc_values_11_0,acc_values_11_1
acc_values_11_0 db '0 WS',0
acc_values_11_1 db '1 WS',0
acc_values_12 dw acc_values_12_0,acc_values_12_1
acc_values_12_0 db '1 WS',0
acc_values_12_1 db '0 WS',0
acc_values_13 dw acc_values_13_0,acc_values_13_1,acc_values_13_2,acc_values_13_3
acc_values_13_0 db 'Longest',0
acc_values_13_1 db 'Long',0
acc_values_13_2 db 'Short',0
acc_values_13_3 db 'Shortest',0
acc_values_14 dw acc_values_14_0,acc_values_14_1,acc_values_14_2,acc_values_14_3
acc_values_14_0 db '4T',0
acc_values_14_1 db '3T',0
acc_values_14_2 db '2T',0
acc_values_14_3 db '1T',0
acc_values_15 dw acc_values_15_0,acc_values_15_1,acc_values_15_2,acc_values_15_3,acc_values_15_4,acc_values_15_5,acc_values_15_6,acc_values_15_7
acc_values_15_0 db '1',0
acc_values_15_1 db '2',0
acc_values_15_2 db '3',0
acc_values_15_3 db '4',0
acc_values_15_4 db '5',0
acc_values_15_5 db '6',0
acc_values_15_6 db '7',0
acc_values_15_7 db '8',0
acc_field_0 db 'ADS Delay Control',0
acc_field_0_help1 db 'Auto uses the recommended disabled ADS delay.',0
acc_field_0_help2 db 'Choose Manual to change ADS Delay yourself.',0
acc_field_1 db 'Internal Cache',0
acc_field_1_help1 db 'Enable or disable the processor cache.',0
acc_field_1_help2 db 'Enabled usually makes programs run faster.',0
acc_field_2 db 'External Cache',0
acc_field_2_help1 db 'Use the cache fitted to the motherboard.',0
acc_field_2_help2 db 'Requires processor cache and detected cache RAM.',0
acc_field_3 db 'System ROM Shadow',0
acc_field_3_help1 db 'Copy the system BIOS into RAM for faster access.',0
acc_field_3_help2 db 'Disabled runs it from the BIOS chip instead.',0
acc_field_4 db 'Video ROM Shadow',0
acc_field_4_help1 db 'Copy the video BIOS into RAM for faster access.',0
acc_field_4_help2 db 'Required for onboard video. Optional for cards.',0
acc_field_5 db 'ADS Delay',0
acc_field_5_help1 db 'Disabled is recommended by the AMI manual.',0
acc_field_5_help2 db 'Enabled adds a delay. Auto always disables it.',0
acc_field_8 db 'Memory Timing',0
acc_field_8_help1 db 'Fast uses tested 33 MHz RAM and refresh timings.',0
acc_field_8_help2 db 'Choose Manual after Fast to adjust them further.',0
acc_field_9 db 'RAS Timeout',0
acc_field_9_help1 db 'Closes an idle RAM row after a short wait.',0
acc_field_9_help2 db 'Enabled is the default. Disable to compare.',0
acc_field_10 db 'RAS Precharge',0
acc_field_10_help1 db 'Time to prepare a RAM row for another access.',0
acc_field_10_help2 db 'Smaller is faster. Too short can corrupt data.',0
acc_field_11 db 'Read RAS to CAS',0
acc_field_11_help1 db 'Wait between choosing a RAM row and reading it.',0
acc_field_11_help2 db 'Smaller is faster. Increase if memory errors occur.',0
acc_field_12 db 'Write RAS to CAS',0
acc_field_12_help1 db 'Wait between choosing a RAM row and writing it.',0
acc_field_12_help2 db 'Smaller is faster. Increase if memory errors occur.',0
acc_field_13 db 'Read CAS Width',0
acc_field_13_help1 db 'Sets the length of each RAM read pulse.',0
acc_field_13_help2 db 'For 1T, choose Earlier for Read Pulse Timing.',0
acc_field_14 db 'Write CAS Width',0
acc_field_14_help1 db 'Sets the length of each RAM write pulse.',0
acc_field_14_help2 db 'Shorter can be faster. Too short can corrupt data.',0
acc_field_15 db 'Read CAS Precharge',0
acc_field_15_help1 db 'Wait between RAM read pulses.',0
acc_field_15_help2 db '1T is the starting choice. Compare with 2T.',0
acc_field_16 db 'Write CAS Precharge',0
acc_field_16_help1 db 'Wait between RAM write pulses.',0
acc_field_16_help2 db '1T is faster. Increase if memory errors occur.',0
acc_field_17 db 'Read Pulse Timing',0
acc_field_17_help1 db 'Earlier starts the read pulse half a clock sooner.',0
acc_field_17_help2 db 'Use Earlier with a Read CAS Width of 1T.',0
acc_field_18 db 'Write Pulse Timing',0
acc_field_18_help1 db 'Earlier starts the write pulse half a clock sooner.',0
acc_field_18_help2 db 'Use Earlier with Uncached Write Wait at 0 WS.',0
acc_field_20 db 'Cache Burst Reads',0
acc_field_20_help1 db 'Transfer cache data to the processor in bursts.',0
acc_field_20_help2 db 'Disabled was faster in the tests on this board.',0
acc_field_21 db 'Cache Read Wait',0
acc_field_21_help1 db 'Extra wait for a read from motherboard cache.',0
acc_field_21_help2 db '0 WS is faster. Add a wait if cache errors occur.',0
acc_field_22 db 'Uncached Write Wait',0
acc_field_22_help1 db 'Wait for a write that does not use cache.',0
acc_field_22_help2 db 'For 0 WS, choose Earlier for Write Pulse Timing.',0
acc_field_24 db 'Cache Write Hit 0 WS',0
acc_field_24_help1 db 'Remove a wait when writing data already in cache.',0
acc_field_24_help2 db 'May be faster. Disable if errors or crashes occur.',0
acc_field_25 db 'Cache Read X-2-2-2',0
acc_field_25_help1 db 'Use two clocks for each later cache burst transfer.',0
acc_field_25_help2 db 'Available only while Cache Burst Reads is enabled.',0
acc_field_26 db 'Memory Wait Control',0
acc_field_26_help1 db 'Change the wait used for memory and bus transfers.',0
acc_field_26_help2 db 'Neither choice is known to be faster on this board.',0
acc_field_27 db 'Cache Wait Control',0
acc_field_27_help1 db 'Change the wait used for cache access.',0
acc_field_27_help2 db 'Enabled improved writes in tests on this board.',0
acc_field_28 db 'Refresh Period',0
acc_field_28_help1 db 'Longer periods leave more time for RAM access.',0
acc_field_28_help2 db '120 us is Slow Refresh. Shorten if errors occur.',0
acc_field_29 db 'Refresh Active Time',0
acc_field_29_help1 db 'Time that RAM stays active during each refresh.',0
acc_field_29_help2 db 'Requires Hidden Burst Refresh. Test stability.',0
acc_field_30 db 'Refresh Precharge',0
acc_field_30_help1 db 'Time to prepare RAM for a refresh cycle.',0
acc_field_30_help2 db 'Requires Hidden Burst Refresh. Fast selects 2T.',0
acc_field_31 db 'Refresh Burst Count',0
acc_field_31_help1 db 'Number of refresh cycles performed in a group.',0
acc_field_31_help2 db 'Available only with Hidden Burst Refresh enabled.',0
acc_field_32 db 'Hidden Burst Refresh',0
acc_field_32_help1 db 'Group memory refresh cycles in hidden bursts.',0
acc_field_32_help2 db 'Try with the refresh count. Check memory stability.',0
acc_field_35 db '8-Bit ISA 0 WS',0
acc_field_35_help1 db 'Remove a wait from access to 8-bit expansion cards.',0
acc_field_35_help2 db 'Enable only if your cards work reliably with it.',0
acc_field_36 db '16-Bit ISA 0 WS',0
acc_field_36_help1 db 'Remove a wait when using 16-bit expansion cards.',0
acc_field_36_help2 db 'Enable only if your cards work reliably with it.',0
acc_field_37 db 'Extra ISA Wait',0
acc_field_37_help1 db 'Add time for slower expansion cards.',0
acc_field_37_help2 db 'Disabled is faster. Enable for slower cards.',0
acc_field_38 db 'ROM 0 WS',0
acc_field_38_help1 db 'Remove a wait when reading the physical ROM chip.',0
acc_field_38_help2 db 'Slow ROM chips can fail. Shadow reads are separate.',0
acc_field_39 db 'System ROM Shadow',0
acc_field_39_help1 db 'Copy the system BIOS into RAM for faster access.',0
acc_field_39_help2 db 'Disabled runs it from the BIOS chip instead.',0
acc_field_40 db 'Video ROM Shadow',0
acc_field_40_help1 db 'Copy the video BIOS into RAM for faster access.',0
acc_field_40_help2 db 'Required for onboard video. Optional for cards.',0
acc_field_41 db 'C800-CFFF ROM Shadow',0
acc_field_41_help1 db 'Copy this ROM area into RAM for faster access.',0
acc_field_41_help2 db 'Leave disabled for cards that use this area as RAM.',0
acc_field_42 db 'D000-DFFF ROM Shadow',0
acc_field_42_help1 db 'Copy this ROM area into RAM for faster access.',0
acc_field_42_help2 db 'Leave disabled for cards that use this area as RAM.',0
acc_field_43 db 'E000-EFFF ROM Shadow',0
acc_field_43_help1 db 'Copy this ROM area into RAM for faster access.',0
acc_field_43_help2 db 'Required for onboard video. Optional for cards.',0
acc_field_44 db 'Shadow RAM Cacheable',0
acc_field_44_help1 db 'Allow cached reads from shadowed ROMs.',0
acc_field_44_help2 db 'AMI recommends Disabled for compatibility.',0
acc_field_45 db 'Shadow Write Protection',0
acc_field_45_help1 db 'Protect BIOS and card ROM copies from changes.',0
acc_field_45_help2 db 'Keep enabled unless software must change the copy.',0
acc_field_46 db 'Cache Burst Writes',0
acc_field_46_help1 db 'Try grouped cache writes with write-back operation.',0
acc_field_46_help2 db 'Experimental. Leave disabled if unsure.',0
acc_field_47 db 'Cache Write X-2-2-2',0
acc_field_47_help1 db 'Use two clocks for later cache burst writes.',0
acc_field_47_help2 db 'Available only while Cache Burst Writes is enabled.',0
acc_field_48 db 'CAS Before RAS Refresh',0
acc_field_48_help1 db 'Let the memory chips choose which row to refresh.',0
acc_field_48_help2 db 'Try enabled for compatible memory. Test stability.',0
acc_field_19 db 'DRAM Read Burst',0
acc_field_19_help1 db 'Read memory in groups instead of single transfers.',0
acc_field_19_help2 db 'Enabled is normal. Compare disabled for speed.',0
chip_page_prefix db 'Page ',0
chip_page_slash db ' / ',0
chip_page_keys db 'PgUp/PgDn Page   F1 Help   F4/F5 Theme   F9 Defaults   F10 Save',0

acc_isa_clock db 'ISA Clock Divider',0
acc_isa_help1 db 'Smaller is faster for ISA cards.',0
acc_isa_help2 db 'Clear CMOS if startup fails.',0
acc_isa_values dw acc_isa_stock,acc_isa_5,acc_isa_4,acc_isa_3,acc_isa_25,acc_isa_2,acc_isa_15,acc_isa_1
acc_isa_stock db 'Stock',0
acc_isa_5 db '/5',0
acc_isa_4 db '/4',0
acc_isa_3 db '/3',0
acc_isa_25 db '/2.5',0
acc_isa_2 db '/2',0
acc_isa_15 db '/1.5',0
acc_isa_1 db '/1',0
