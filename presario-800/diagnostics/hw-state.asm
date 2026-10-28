; Read-only DOS snapshot. No CMOS/data/command writes; restore IDE selection.
bits 16
org 0x100
    push cs
    pop ds
    mov dx, rtc_label
    call text
    mov si, rtc_registers
    mov cx, rtc_registers_end - rtc_registers
.rtc:
    lodsb
    pushf
    cli
    out 0x70, al
    in al, 0x84
    in al, 0x71
    popf
    call hex
    loop .rtc
    mov dx, cmos_label
    call text
    mov si, cmos_registers
    mov cx, cmos_registers_end - cmos_registers
.cmos:
    lodsb
    pushf
    cli
    out 0x70, al
    in al, 0x84
    in al, 0x71
    popf
    call hex
    loop .cmos
    mov dx, ide_label
    call text
    mov dx, 0x1F6
    in al, dx
    mov [selected], al
    mov bx, 0
.device:
    mov dx, master_label
    test bl, bl
    jz .label
    mov dx, slave_label
.label:
    call text
    mov dx, 0x1F6
    mov al, 0xA0
    or al, bl
    out dx, al
    mov dx, 0x3F6
    mov cx, 4
.settle:
    in al, dx
    loop .settle
    mov dx, 0x1F1
    mov cx, 7
.register:
    in al, dx
    call hex
    inc dx
    loop .register
    mov dx, 0x3F6
    in al, dx
    call hex
    add bl, 0x10
    cmp bl, 0x20
    jb .device
    mov dx, 0x1F6
    mov al, [selected]
    out dx, al
    mov dx, newline
    call text
    mov ax, 0x4C00
    int 0x21

text:
    pushad
    mov ah, 9
    int 0x21
    popad
    ret
hex:
    pushad
    mov bl, al
    shr al, 4
    call .digit
    mov al, bl
    and al, 15
    call .digit
    mov dl, ' '
    mov ah, 2
    int 0x21
    popad
    ret
.digit:
    movzx di, al
    mov dl, [digits + di]
    mov ah, 2
    int 0x21
    ret

digits db '0123456789ABCDEF'
selected db 0
rtc_registers db 0xA,0xB,0xE,0,2,4,7,8,9,0x32
rtc_registers_end:
cmos_registers db 0x10,0x38,0x39,0x3A,0x3B,0x3C,0x3D,0x3E,0x3F
cmos_registers_end:
rtc_label db 'RTC A/B/E/sec/min/hour/day/month/year/century:',13,10,'$'
cmos_label db 13,10,'CMOS 10,38..3F:',13,10,'$'
ide_label db 13,10,'IDE ERR CNT SEC CYL_LO CYL_HI DEV STATUS ALT:',13,10,'$'
master_label db 'Master: $'
slave_label db 13,10,'Slave:  $'
newline db 13,10,'$'
