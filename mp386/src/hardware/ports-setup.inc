; MP3220 switch chart. SW1 wiring is not fully decoded, so this is a guide.
mp_ports_draw:
    ui_text 3,23,u_devices_title,0x0B
    ui_text 4,24,mp_sw1_title,0x0B
    ui_text 4,53,mp_sw3_title,0x0B
    xor bp,bp
.row:
    mov bx,bp
    shl bx,1
    mov si,[cs:mp_sw1_lines+bx]
    mov di,bp
    add di,6
    imul di,160
    add di,24*2
    mov bh,7
    call setup_text
    add di,29*2
    mov bx,bp
    shl bx,1
    mov si,[cs:mp_sw3_lines+bx]
    mov bh,7
    call setup_text
    inc bp
    cmp bp,8
    jb .row
    ui_text 15,24,mp_sw_lpt1,7
    ui_text 16,24,mp_sw_lpt2,7
    ui_text 18,24,mp_sw_power,7
    ui_text 19,24,mp_sw_enable,7
    ret
mp_ports_help:
    ui_text 18,25,mp_sw_power,0x1E
    ui_text 19,25,mp_sw_enable,0x1E
    ui_text 20,25,mp_sw_fast,0x1E
    ret
mp_sw1_title db 'SW1: system switches',0
mp_sw3_title db 'SW3: onboard devices',0
mp_sw1_lines dw mp_sw11,mp_sw12,mp_sw13,mp_sw14,mp_sw15,mp_sw16,mp_sw17,mp_sw18
mp_sw3_lines dw mp_sw31,mp_sw32,mp_sw33,mp_sw34,mp_sw35,mp_sw36,mp_sw37,mp_sw38
mp_sw11 db '1 Bus: Off 6 / On 8 MHz',0
mp_sw12 db '2 Ext RAM: Off enables',0
mp_sw13 db '3 Factory: keep Off',0
mp_sw14 db '4 POST: Off full / On min',0
mp_sw15 db '5 Base: Off512 / On256 KB',0
mp_sw16 db '6 Factory: keep Off',0
mp_sw17 db '7 Kbd: Off std / On enhanced',0
mp_sw18 db '8 Video: Off mono / On color',0
mp_sw31 db '1 Cache: Off=no / On=yes',0
mp_sw32 db '2 IDE controller',0
mp_sw33 db '3 Math coprocessor',0
mp_sw34 db '4 Floppy controller',0
mp_sw35 db '5 COM1',0
mp_sw36 db '6 COM2',0
mp_sw37 db '7 Parallel port: see below',0
mp_sw38 db '8 Parallel port: see below',0
mp_sw_lpt1 db 'SW3 7/8: Off/Off LPT1, Off/On LPT2',0
mp_sw_lpt2 db '         On/Off LPT3, On/On Disabled',0
mp_sw_power db 'Turn power off before changing board switches.',0
mp_sw_enable db 'SW1/2 and SW3/2-6: Off enables, On disables.',0
mp_sw_fast db 'Choose Fast Boot on the Boot page.',0
