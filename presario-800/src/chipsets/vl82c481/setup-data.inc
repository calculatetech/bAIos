u_chip_menu db 'Chipset',0
u_chip_title db 'bAIos Setup > Chipset',0
u_chip_open db 'Open',0x1A,0
u_chip_help dw u_chip_menu,u_chip_help1,u_chip_help2
u_chip_help1 db 'Smaller waits are faster. Too fast can corrupt data.',0
u_chip_help2 db 'F9 loads defaults. Save applies after restart.',0
chip_group_0:
    chipset_field chip_profile_clock,23,1,1,2,chip_clock_values,chip_clock_help1,chip_clock_help2
    chipset_field chip_dram_speed,10,4,3,3,chip_speed_values,chip_speed_help1,chip_speed_help2
    chipset_field chip_memory_timing,10,6,3,4,chip_mode_values,chip_mode_help1,chip_mode_help2
    chipset_field uc_0,0,6,3,3,chip_values_0,uc_1,uc_2
    chipset_field uc_3,0,4,3,4,chip_values_1,uc_4,uc_5
    chipset_field uc_6,0,2,3,4,chip_values_1,uc_7,uc_8
    chipset_field uc_9,0,0,3,4,chip_values_2,uc_10,uc_11
    chipset_field uc_12,10,0,3,3,chip_values_3,uc_13,uc_14
    chipset_field uc_15,2,2,3,3,chip_values_4,uc_16,uc_17
    chipset_field uc_18,2,1,1,2,chip_values_5,uc_19,uc_20
    chipset_field uc_21,2,0,1,2,chip_values_6,uc_22,uc_23
    chipset_field uc_24,1,7,1,2,chip_values_5,uc_25,uc_26
    chipset_field uc_27,1,4,1,2,chip_values_7,uc_28,uc_29
    chipset_field uc_30,1,1,3,4,chip_values_8,uc_31,uc_32
    chipset_field uc_33,1,0,1,2,chip_values_9,uc_34,uc_35
    chipset_field uc_36,4,2,1,2,chip_values_7,uc_37,uc_38
    chipset_field uc_39,10,2,1,2,chip_values_5,uc_40,uc_41
chip_group_1:
    chipset_field uc_42,4,3,1,2,chip_values_5,uc_43,uc_44
    chipset_field uc_45,9,0,1,2,chip_values_5,uc_46,uc_47
    chipset_field uc_48,9,6,1,2,chip_values_10,uc_49,uc_50
    chipset_field uc_51,9,3,1,2,chip_values_11,uc_52,uc_53
    chipset_field uc_54,4,7,1,2,chip_values_5,uc_55,uc_56
    chipset_field uc_57,4,5,1,2,chip_values_12,uc_58,uc_59
    chipset_field uc_60,4,4,1,2,chip_values_5,uc_61,uc_62
    chipset_field uc_63,4,1,1,2,chip_values_7,uc_64,uc_65
    chipset_field uc_66,4,0,1,2,chip_values_7,uc_67,uc_68
    chipset_field uc_69,10,3,1,2,chip_values_5,uc_70,uc_71
    chipset_field uc_72,11,0,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_75,11,2,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_76,11,4,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_77,11,6,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_78,12,0,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_79,12,2,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_80,12,4,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_81,12,6,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_82,13,0,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_83,13,2,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_84,13,4,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_85,13,6,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_86,14,0,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_87,14,2,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_88,14,4,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_89,14,6,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_90,15,0,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_91,15,2,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_92,15,4,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_93,15,6,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_94,16,0,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_95,16,2,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_96,16,4,3,3,chip_values_13,uc_73,uc_74
    chipset_field uc_97,16,6,3,3,chip_values_13,uc_73,uc_74
chip_group_2:
    chipset_field uc_98,23,0,1,2,chip_values_14,uc_99,uc_100
    chipset_field uc_101,3,3,3,4,chip_values_15,uc_102,uc_103
    chipset_field uc_104,3,5,3,4,chip_values_16,uc_105,uc_106
    chipset_field uc_107,2,5,7,8,chip_values_17,uc_108,uc_109
    chipset_field uc_110,3,0,3,4,chip_values_18,uc_111,uc_112
chip_group_3:
    chipset_field uc_113,6,6,1,2,chip_values_19,uc_114,uc_115
    chipset_field uc_116,6,5,1,2,chip_values_20,uc_117,uc_118
    chipset_field uc_119,6,4,1,2,chip_values_14,uc_120,uc_121
    chipset_field uc_122,6,3,1,2,chip_values_21,uc_123,uc_124
    chipset_field uc_125,6,2,1,2,chip_values_21,uc_126,uc_127
    chipset_field uc_128,6,1,1,2,chip_values_22,uc_129,uc_130
    chipset_field uc_131,6,0,1,2,chip_values_23,uc_132,uc_133
    chipset_field uc_134,3,7,1,2,chip_values_5,uc_135,uc_136
    chipset_field uc_137,7,0,255,256,CHIP_VALUES_FAST_REGION,uc_138,uc_139
    chipset_field uc_140,17,0,63,64,CHIP_VALUES_CACHE_REGION,uc_141,uc_142
    chipset_field uc_143,17,6,1,2,chip_values_26,uc_144,uc_145
    chipset_field uc_146,18,0,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_149,18,1,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_150,18,2,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_151,18,3,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_152,18,4,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_153,18,5,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_154,18,6,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_155,18,7,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_140,19,0,63,64,CHIP_VALUES_CACHE_REGION,uc_141,uc_142
    chipset_field uc_143,19,6,1,2,chip_values_26,uc_144,uc_145
    chipset_field uc_146,20,0,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_149,20,1,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_150,20,2,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_151,20,3,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_152,20,4,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_153,20,5,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_154,20,6,1,2,chip_values_5,uc_147,uc_148
    chipset_field uc_155,20,7,1,2,chip_values_5,uc_147,uc_148
chip_group_4:
    chipset_field uc_156,5,4,3,4,chip_values_27,uc_157,uc_158
    chipset_field uc_159,5,2,3,4,chip_values_27,uc_160,uc_161
    chipset_field uc_162,5,1,1,2,chip_values_28,uc_163,uc_164
    chipset_field uc_165,5,0,1,2,chip_values_29,uc_166,uc_167
    chipset_field uc_168,5,7,1,2,chip_values_5,uc_169,uc_170
chip_group_5:
    chipset_field uc_171,8,0,3,3,chip_values_30,uc_172,uc_173
    chipset_field uc_174,21,0,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_177,21,1,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_178,21,2,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_179,21,3,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_180,21,4,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_181,21,5,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_182,21,6,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_183,21,7,1,2,chip_values_5,uc_175,uc_176
    chipset_field uc_184,22,0,1,2,chip_values_5,uc_175,uc_185
    chipset_field uc_186,22,1,1,2,chip_values_5,uc_175,uc_185
    chipset_field uc_187,22,2,1,2,chip_values_5,uc_175,uc_185
    chipset_field uc_188,22,3,1,2,chip_values_5,uc_175,uc_185
chip_fields_end:
CHIP_FIELD_COUNT equ (chip_fields_end-chip_group_0)/CHIP_FIELD_SIZE

chipset_groups dw chip_group_0,chip_group_1,chip_group_2,chip_group_3,chip_group_4,chip_group_5
chipset_groups_end:
CHIP_GROUP_COUNT equ (chipset_groups_end-chipset_groups)/2
chipset_group_counts db (chip_group_1-chip_group_0)/CHIP_FIELD_SIZE,(chip_group_2-chip_group_1)/CHIP_FIELD_SIZE,(chip_group_3-chip_group_2)/CHIP_FIELD_SIZE,(chip_group_4-chip_group_3)/CHIP_FIELD_SIZE,(chip_group_5-chip_group_4)/CHIP_FIELD_SIZE,(chip_fields_end-chip_group_5)/CHIP_FIELD_SIZE
chipset_group_titles dw uc_189,uc_190,uc_191,uc_192,uc_193,uc_194
chipset_group_help:
    dw uc_189,uc_195,uc_196
    dw uc_190,uc_197,uc_198
    dw uc_191,uc_199,uc_200
    dw uc_192,uc_201,uc_202
    dw uc_193,uc_203,uc_204
    dw uc_194,uc_205,uc_206
chip_values_0 dw uc_207,uc_208,uc_209
chip_values_1 dw uc_210,uc_211,uc_212,uc_213
chip_values_2 dw uc_214,uc_215,uc_216,uc_217
chip_values_3 dw uc_218,uc_219,uc_220
chip_values_4 dw uc_221,uc_222,uc_223
chip_values_5 dw uc_224,uc_225
chip_values_6 dw uc_226,uc_227
chip_values_7 dw uc_225,uc_224
chip_values_8 dw uc_228,uc_229,uc_230,uc_231
chip_values_9 dw uc_225,uc_232
chip_values_10 dw uc_233,uc_234
chip_values_11 dw uc_235,uc_236
chip_values_12 dw uc_237,uc_238
chip_values_13 dw uc_239,uc_240,uc_241
chip_values_14 dw uc_242,uc_243
chip_values_15 dw uc_244,uc_245,uc_246,uc_247
chip_values_16 dw uc_248,uc_249,uc_250,uc_251
chip_values_17 dw uc_252,uc_253,uc_254,uc_255,uc_256,uc_257,uc_258,uc_259
chip_values_18 dw uc_260,uc_261,uc_262,uc_263
chip_values_19 dw uc_264,uc_265
chip_values_20 dw uc_228,uc_231
chip_values_21 dw uc_266,uc_267
chip_values_22 dw uc_234,uc_233
chip_values_23 dw uc_268,uc_269
chip_values_26 dw uc_239,uc_240
chip_values_27 dw uc_590,uc_268,uc_591,uc_591
chip_values_28 dw uc_592,uc_593
chip_values_29 dw uc_594,uc_595
chip_values_30 dw uc_591,uc_233,uc_590
chipset_first_view db 0,2,5,6,9,10
chipset_view_counts db 2,3,1,3,1,2
chipset_views:
    dw uc_189
    db 0,8
    dw chip_rows_0,chip_headers_0
    dw uc_189
    db 8,9
    dw chip_rows_1,chip_headers_1
    dw uc_190
    db 0,10
    dw chip_rows_2,chip_headers_2
    dw uc_190
    db 10,12
    dw chip_rows_3,chip_headers_3
    dw uc_190
    db 22,12
    dw chip_rows_4,chip_headers_4
    dw uc_191
    db 0,5
    dw chip_rows_6,chip_headers_6
    dw uc_192
    db 0,9
    dw chip_rows_7,chip_headers_7
    dw uc_192
    db 9,10
    dw chip_rows_8,chip_headers_8
    dw uc_192
    db 19,10
    dw chip_rows_9,chip_headers_9
    dw uc_193
    db 0,5
    dw chip_rows_10,chip_headers_10
    dw uc_194
    db 0,9
    dw chip_rows_11,chip_headers_11
    dw uc_194
    db 9,4
    dw chip_rows_12,chip_headers_12
chip_rows_0 db 5,6,7,10,11,12,13,14
chip_headers_0:
    db 4
    dw chip_profiles_title
    db 9
    dw uc_596
    db 0
chip_rows_1 db 5,6,7,10,11,12,13,16,17
chip_headers_1:
    db 4
    dw uc_597
    db 9
    dw uc_598
    db 15
    dw uc_599
    db 0
chip_rows_2 db 5,8,9,10,11,12,13,14,15,16
chip_headers_2:
    db 4
    dw uc_600
    db 7
    dw uc_601
    db 0
chip_rows_3 db 5,6,7,8,11,12,13,14,17,18,19,20
chip_headers_3:
    db 4
    dw uc_602
    db 10
    dw uc_603
    db 16
    dw uc_604
    db 0
chip_rows_4 db 5,6,7,8,11,12,13,14,17,18,19,20
chip_headers_4:
    db 4
    dw uc_605
    db 10
    dw uc_606
    db 16
    dw uc_607
    db 0
chip_rows_6 db 5,8,11,12,13
chip_headers_6:
    db 7
    dw uc_243
    db 10
    dw uc_242
    db 0
chip_rows_7 db 5,6,7,8,9,10,11,14,15
chip_headers_7:
    db 4
    dw uc_608
    db 13
    dw uc_134
    db 0
chip_rows_8 db 5,6,7,8,9,10,11,12,13,14
chip_headers_8:
    db 4
    dw uc_609
    db 0
chip_rows_9 db 5,6,7,8,9,10,11,12,13,14
chip_headers_9:
    db 4
    dw uc_610
    db 0
chip_rows_10 db 5,6,7,8,9
chip_headers_10:
    db 0
chip_rows_11 db 5,8,9,10,11,14,15,16,17
chip_headers_11:
    db 7
    dw uc_604
    db 13
    dw uc_605
    db 0
chip_rows_12 db 5,6,7,8
chip_headers_12:
    db 4
    dw uc_606
    db 0
chip_cas_disabled dw uc_611,uc_612,uc_613,uc_614
chip_cas_enabled dw uc_615,uc_615,uc_616,uc_617
uc_0 db 'Cycle Start',0
uc_1 db 'First T2 is faster. End T2 gives RAM more time.',0
uc_2 db 'An early start can cause RAM errors or a failed boot.',0
uc_3 db 'RAS Precharge',0
uc_4 db 'Smaller is faster. Larger gives RAM more time.',0
uc_5 db 'Too small can corrupt data or prevent a boot.',0
uc_6 db 'RAS to CAS Delay',0
uc_7 db 'Smaller is faster. RAM needs time from RAS to CAS.',0
uc_8 db 'Too small can cause RAM errors with or without L2.',0
uc_9 db 'CAS Width',0
uc_10 db 'Smaller is faster. Values show read/write CAS widths.',0
uc_11 db 'L2/HSPD uses right widths. Too small corrupts data.',0
uc_12 db 'High Speed Timing',0
uc_13 db 'High Speed changes timing for high CPU clock rates.',0
uc_14 db 'Auto keeps the board strap. An override can fail.',0
uc_15 db 'Refresh Mode',0
uc_16 db 'Asynchronous/Decoupled can reduce refresh delays.',0
uc_17 db 'RAM resumes earlier. ISA cards still need refresh.',0
uc_18 db 'CAS Before RAS',0
uc_19 db 'Enabled selects the RAM internal refresh counter.',0
uc_20 db 'No clear speed gain. The RAM must support this mode.',0
uc_21 db 'Refresh Period',0
uc_22 db '125 us refreshes less often and leaves more RAM time.',0
uc_23 db 'RAM without 125 us support can lose data.',0
uc_24 db 'Memory Interleave',0
uc_25 db 'Enabled can speed RAM access across matching banks.',0
uc_26 db 'BIOS picks the bank pair. Mixed RAM can be unstable.',0
uc_27 db 'RAS Timeout',0
uc_28 db 'Leave Disabled unless RAM requires a RAS time limit.',0
uc_29 db 'Enabled ends long RAS pulses and can close RAM pages.',0
uc_30 db 'DRAM Drive Strength',0
uc_31 db 'More mA drives a heavier RAM load. It is not faster.',0
uc_32 db 'Too little or too much drive can cause RAM errors.',0
uc_33 db 'DRAM Page Mode',0
uc_34 db 'Enabled speeds repeated access to the same RAM page.',0
uc_35 db 'Burst Only limits fast page access to burst cycles.',0
uc_36 db 'RAM Parity Check',0
uc_37 db 'Enabled detects RAM parity errors but cannot repair.',0
uc_38 db 'Needs parity RAM and CPU generation. Errors halt.',0
uc_39 db 'CPU Parity Generation',0
uc_40 db 'Enabled stores parity bits with CPU writes to RAM.',0
uc_41 db 'No speed gain. Needs parity RAM for useful checking.',0
uc_42 db 'Internal Cache',0
uc_43 db 'Enabled speeds repeated CPU reads from RAM.',0
uc_44 db 'Disabled is slower but helps diagnose RAM faults.',0
uc_45 db 'External Cache',0
uc_46 db 'Enabled speeds repeated RAM reads if L2 is present.',0
uc_47 db 'L2 starts after summary. Bad timing can corrupt data.',0
uc_48 db 'L2 Write Wait States',0
uc_49 db '0 WS is faster. Needs two low-skew clock buffers.',0
uc_50 db 'Wrong clock wiring or slow SRAM can corrupt writes.',0
uc_51 db 'L2 Write Policy',0
uc_52 db 'Write Back is faster because it delays RAM writes.',0
uc_53 db 'Write Through writes RAM too. It is usually slower.',0
uc_54 db 'L2 Segment Controls',0
uc_55 db 'Enabled honors each memory window cache policy.',0
uc_56 db 'Disabled can cache devices and return old data.',0
uc_57 db 'Cache Write Turnoff',0
uc_58 db 'Early ends the SRAM write pulse sooner. Not faster.',0
uc_59 db 'A short pulse can cause bad writes. Late gives time.',0
uc_60 db 'Fast Internal RC',0
uc_61 db 'Enabled selects the fast internal RC# signal timing.',0
uc_62 db 'Speed gain is not proven. Wrong timing can fail.',0
uc_63 db 'Conditional Waits',0
uc_64 db 'Disabled can reduce waits and speed memory access.',0
uc_65 db 'Less wait time can cause RAM or cache errors.',0
uc_66 db 'Cache Clock Adjustment',0
uc_67 db 'Changes cache signal timing. It does not change MHz.',0
uc_68 db 'Neither mode is always faster. Wrong timing can fail.',0
uc_69 db 'Extra Cache Read Wait',0
uc_70 db 'Disabled removes a cache read wait and is faster.',0
uc_71 db 'Slow SRAM can fail at fast reads. Enabled adds time.',0
uc_72 db 'A0000-A3FFF',0
uc_73 db 'Cacheable speeds reads. Uncached avoids stale data.',0
uc_74 db 'Write Protected caches ROM and blocks CPU writes.',0
uc_75 db 'A4000-A7FFF',0
uc_76 db 'A8000-ABFFF',0
uc_77 db 'AC000-AFFFF',0
uc_78 db 'B0000-B3FFF',0
uc_79 db 'B4000-B7FFF',0
uc_80 db 'B8000-BBFFF',0
uc_81 db 'BC000-BFFFF',0
uc_82 db 'C0000-C3FFF',0
uc_83 db 'C4000-C7FFF',0
uc_84 db 'C8000-CBFFF',0
uc_85 db 'CC000-CFFFF',0
uc_86 db 'D0000-D3FFF',0
uc_87 db 'D4000-D7FFF',0
uc_88 db 'D8000-DBFFF',0
uc_89 db 'DC000-DFFFF',0
uc_90 db 'E0000-E3FFF',0
uc_91 db 'E4000-E7FFF',0
uc_92 db 'E8000-EBFFF',0
uc_93 db 'EC000-EFFFF',0
uc_94 db 'F0000-F3FFF',0
uc_95 db 'F4000-F7FFF',0
uc_96 db 'F8000-FBFFF',0
uc_97 db 'FC000-FFFFF',0
uc_98 db 'CPU Clock',0
uc_99 db 'Fast runs the CPU faster. Slow helps old programs.',0
uc_100 db 'Fast can upset software that needs a slow CPU.',0
uc_101 db 'Fast ISA Divider',0
uc_102 db 'Smaller is faster. Values show TCLK2 then BUSOSC.',0
uc_103 db 'The source is wired. Too fast can cause ISA errors.',0
uc_104 db 'Slow CPU Divider',0
uc_105 db 'Smaller is faster in Slow CPU mode only.',0
uc_106 db 'A faster slow mode can upset old games or devices.',0
uc_107 db 'Slow CPU Waits',0
uc_108 db 'Smaller is faster in Slow CPU mode only.',0
uc_109 db 'Larger adds delay for software that needs a slow CPU.',0
uc_110 db 'Slow ISA Divider',0
uc_111 db 'Smaller is faster. Values show TCLK2 then BUSOSC.',0
uc_112 db 'The source is wired. Too fast can cause ISA errors.',0
uc_113 db 'I/O Address Decode',0
uc_114 db '16 Bit avoids port aliases. Neither mode is faster.',0
uc_115 db '10 Bit can make devices respond at unwanted ports.',0
uc_116 db 'Slot Drive Strength',0
uc_117 db '24 mA drives a heavier ISA load. It is not faster.',0
uc_118 db 'Wrong drive strength can cause ISA device errors.',0
uc_119 db 'Disk I/O Timing',0
uc_120 db 'Fast shortens disk I/O timing. Slow adds time.',0
uc_121 db 'Too fast can cause disk errors. ATA modes stay fixed.',0
uc_122 db 'I/O Command Delay',0
uc_123 db '0 SYSCLK is faster. 1 SYSCLK gives devices more time.',0
uc_124 db 'Too short can cause ISA I/O or 8-bit memory errors.',0
uc_125 db '16-Bit Memory Delay',0
uc_126 db '0 SYSCLK is faster. 1 SYSCLK gives devices more time.',0
uc_127 db 'Too short can cause 16-bit ISA memory errors.',0
uc_128 db '16-Bit Wait States',0
uc_129 db 'Smaller is faster. Larger gives ISA memory more time.',0
uc_130 db 'Too small can corrupt data. READY can add more waits.',0
uc_131 db '8-Bit Wait States',0
uc_132 db 'Smaller is faster. Larger gives ISA memory more time.',0
uc_133 db 'Too small can corrupt data. READY can add more waits.',0
uc_134 db 'Fast ISA Region',0
uc_135 db 'Enabled uses the Fast ISA divider in the chosen area.',0
uc_136 db 'Faster access can help devices or cause bad data.',0
uc_137 db 'Fast ISA Address',0
uc_138 db 'Selects the area that uses the Fast ISA divider.',0
uc_139 db 'No speed gain unless enabled. A wrong area can fail.',0
uc_140 db 'Region Address / Size',0
uc_141 db 'Selects ISA card memory. A larger area is not faster.',0
uc_142 db 'Disable all parts first. RAM holes reduce usable RAM.',0
uc_143 db 'Region Cacheability',0
uc_144 db 'Cacheable speeds reads. Uncached suits ISA devices.',0
uc_145 db 'Caching device memory can return old data.',0
uc_146 db 'Subregion 0',0
uc_147 db 'Enabled maps this part to ISA memory. Not faster.',0
uc_148 db 'RAM holes reduce usable RAM. Shadow conflicts fail.',0
uc_149 db 'Subregion 1',0
uc_150 db 'Subregion 2',0
uc_151 db 'Subregion 3',0
uc_152 db 'Subregion 4',0
uc_153 db 'Subregion 5',0
uc_154 db 'Subregion 6',0
uc_155 db 'Subregion 7',0
uc_156 db '8-Bit DMA Wait States',0
uc_157 db 'Smaller is faster. Larger gives DMA cards more time.',0
uc_158 db 'Too small can cause bad data. Both 3 WS codes match.',0
uc_159 db '16-Bit DMA Wait States',0
uc_160 db 'Smaller is faster. Larger gives DMA cards more time.',0
uc_161 db 'Too small can cause bad data. Both 3 WS codes match.',0
uc_162 db 'DMA Clock',0
uc_163 db 'SYSCLK is faster. SYSCLK / 2 gives DMA more time.',0
uc_164 db 'Too fast can corrupt data or cause sound problems.',0
uc_165 db 'DMA Memory Read',0
uc_166 db 'Early asserts the DMA read signal one clock sooner.',0
uc_167 db 'It adds setup time, not speed. Some devices can fail.',0
uc_168 db 'Extended DMA Address',0
uc_169 db 'Enabled supports extended DMA address registers.',0
uc_170 db 'No speed gain. DMA software must set the right pages.',0
uc_171 db 'ROM Wait States',0
uc_172 db 'Smaller is faster for reads from physical ROM.',0
uc_173 db 'Too small can read bad ROM data and prevent a boot.',0
uc_174 db 'C0000-C3FFF Shadow',0
uc_175 db 'Enabled copies ROM to RAM for faster ROM reads.',0
uc_176 db 'Uses a RAM window. Can conflict with ISA card memory.',0
uc_177 db 'C4000-C7FFF Shadow',0
uc_178 db 'C8000-CBFFF Shadow',0
uc_179 db 'CC000-CFFFF Shadow',0
uc_180 db 'D0000-D3FFF Shadow',0
uc_181 db 'D4000-D7FFF Shadow',0
uc_182 db 'D8000-DBFFF Shadow',0
uc_183 db 'DC000-DFFFF Shadow',0
uc_184 db 'E0000-E3FFF Shadow',0
uc_185 db 'Uses a RAM window. Can conflict with cards or UMBs.',0
uc_186 db 'E4000-E7FFF Shadow',0
uc_187 db 'E8000-EBFFF Shadow',0
uc_188 db 'EC000-EFFFF Shadow',0
uc_189 db 'RAM',0
uc_190 db 'Cache',0
uc_191 db 'Clock',0
uc_192 db 'ISA Bus',0
uc_193 db 'DMA',0
uc_194 db 'Shadow',0
uc_195 db 'Smaller RAM timings are faster but can corrupt data.',0
uc_196 db 'Only RAM test failures load chipset defaults.',0
uc_197 db 'Enabled caches speed repeated RAM and ROM reads.',0
uc_198 db 'Caching device memory can return old data.',0
uc_199 db 'Smaller dividers are faster. ISA cards can fail.',0
uc_200 db 'Slow CPU settings affect only Slow CPU mode.',0
uc_201 db 'Smaller waits are faster. Slow ISA cards can fail.',0
uc_202 db 'ISA regions reserve memory for expansion devices.',0
uc_203 db 'Smaller waits and faster clocks speed DMA.',0
uc_204 db 'Too fast can cause bad data or sound problems.',0
uc_205 db 'Enabled copies ROM to RAM for faster ROM reads.',0
uc_206 db 'Uses RAM windows. ISA card memory can conflict.',0
uc_207 db 'First T2',0
uc_208 db 'Middle T2',0
uc_209 db 'End T2',0
uc_210 db '1T',0
uc_211 db '2T',0
uc_212 db '3T',0
uc_213 db '4T',0
uc_214 db '1T/1T | 2T/1T',0
uc_215 db '1.5T/1T | 2T/1T',0
uc_216 db '2T/1T | 3T/1T',0
uc_217 db '2T/2T | 3T/2T',0
uc_218 db 'Auto',0
uc_219 db 'Normal',0
uc_220 db 'High Speed',0
uc_221 db 'Synchronous',0
uc_222 db 'Asynchronous',0
uc_223 db 'Decoupled',0
uc_224 db 'Disabled',0
uc_225 db 'Enabled',0
uc_226 db '15.625 us',0
uc_227 db '125 us',0
uc_228 db '12 mA',0
uc_229 db '24 mA MA / RAMW',0
uc_230 db '24 mA except RAS',0
uc_231 db '24 mA',0
uc_232 db 'Burst Only',0
uc_233 db '1 WS',0
uc_234 db '0 WS',0
uc_235 db 'Write Back',0
uc_236 db 'Write Through',0
uc_237 db 'Late',0
uc_238 db 'Early',0
uc_239 db 'Cacheable',0
uc_240 db 'Uncached',0
uc_241 db 'Write Protected',0
uc_242 db 'Slow',0
uc_243 db 'Fast',0
uc_244 db 'TCLK2 /  2 | BUS / 2',0
uc_245 db 'TCLK2 /  4 | BUS / 4',0
uc_246 db 'TCLK2 /  6 | BUS / 6',0
uc_247 db 'TCLK2 /  8 | BUS / 8',0
uc_248 db 'TCLK2 /  2',0
uc_249 db 'TCLK2 /  4',0
uc_250 db 'TCLK2 /  6',0
uc_251 db 'TCLK2 /  8',0
uc_252 db '0',0
uc_253 db '2',0
uc_254 db '3',0
uc_255 db '4',0
uc_256 db '5',0
uc_257 db '6',0
uc_258 db '7',0
uc_259 db '8',0
uc_260 db 'TCLK2 /  4 | BUS / 2',0
uc_261 db 'TCLK2 /  6 | BUS / 4',0
uc_262 db 'TCLK2 /  8 | BUS / 6',0
uc_263 db 'TCLK2 / 12 | BUS / 8',0
uc_264 db '16 Bit',0
uc_265 db '10 Bit',0
uc_266 db '0 SYSCLK',0
uc_267 db '1 SYSCLK',0
uc_268 db '4 WS',0
uc_269 db '5 WS',0
uc_590 db '2 WS',0
uc_591 db '3 WS',0
uc_592 db 'SYSCLK / 2',0
uc_593 db 'SYSCLK',0
uc_594 db 'AT Compatible',0
uc_595 db '1 DMA Clock Early',0
uc_596 db 'Timing',0
uc_597 db 'Refresh',0
uc_598 db 'Configuration',0
uc_599 db 'Parity',0
uc_600 db 'Internal',0
uc_601 db 'External',0
uc_602 db 'A0000-AFFFF',0
uc_603 db 'B0000-BFFFF',0
uc_604 db 'C0000-CFFFF',0
uc_605 db 'D0000-DFFFF',0
uc_606 db 'E0000-EFFFF',0
uc_607 db 'F0000-FFFFF',0
uc_608 db 'Bus Timing',0
uc_609 db 'Region 1',0
uc_610 db 'Region 2',0
uc_611 db '  1T/1T',0
uc_612 db '1.5T/1T',0
uc_613 db '  2T/1T',0
uc_614 db '  2T/2T',0
uc_615 db '2T/1T',0
uc_616 db '3T/1T',0
uc_617 db '3T/2T',0
chip_profiles_title db 'Profiles',0
chip_profile_clock db 'Timing Profile Clock',0
chip_dram_speed db 'DRAM Speed',0
chip_memory_timing db 'Memory Timing',0
chip_clock_values dw chip_clock25,chip_clock33
chip_speed_values dw chip_unknown,chip_speed60,chip_speed70
chip_mode_values dw chip_normal,chip_compatibility,chip_manual,chip_fast
chip_mode_choices dw chip_fast,chip_normal,chip_compatibility,chip_manual
chip_clock25 db '25 MHz',0
chip_clock33 db '33 MHz',0
chip_unknown db 'Unknown',0
chip_speed60 db '60 ns',0
chip_speed70 db '70 ns',0
chip_normal db 'Normal',0
chip_compatibility db 'Compatibility',0
chip_manual db 'Manual',0
chip_fast db 'Fast',0
chip_clock_help1 db 'Configured input. This does not change the clock.',0
chip_clock_help2 db 'Above 25 through 33 MHz: use 33. Above 33: Manual.',0
chip_speed_help1 db 'Onboard RAM is 70 ns. Unknown also uses 70 ns.',0
chip_speed_help2 db '60 ns is experimental with onboard 70 ns RAM.',0
chip_mode_help1 db 'Normal balances speed. Compatibility adds margin.',0
chip_mode_help2 db 'Fast uses 2T CAS with L2. Manual unlocks timing.',0
chip_page_prefix db 'Page ',0
chip_page_slash db ' / ',0
chip_cas_title db 'CAS Width',0
chip_cas_left db 'L2 Disabled',0
chip_cas_right db 'L2 Enabled',0
chip_cas_separator db '|',0
chip_page_keys db 'PgUp/PgDn Page   F1 Help   F4/F5 Theme   F9 Defaults   F10 Save',0

; Calculated numeric choices retain the approved strings exactly.
chip_range_dash db '-',0
chip_range_512k db ' / 512 KB',0
chip_range_8m db ' / 8 MB',0
chip_range_16k db ' / 16 KB',0
