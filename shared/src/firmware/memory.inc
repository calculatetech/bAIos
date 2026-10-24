publish_memory_cmos:
    pushf
    cli
    pushad
    push fs
    mov ax, STATE_SEG
    mov fs, ax
    mov bx, 640                 ; Installed base RAM; INT12 excludes our EBDA.
    mov dl, 0x95
    call .word
    mov bx, [fs:S_EXTENDED_KIB]
    mov dl, 0x97
    call .word
    mov bx, [fs:S_EXTENDED_KIB]
    mov dl, 0xB0
    call .word
    call update_cmos_checksum
    pop fs
    popad
    popf
    ret
.word:
    mov cx, 2
.byte:
    mov al, dl
    out 0x70, al
    in al, 0x84
    mov al, bl
    out 0x71, al
    shr bx, 8
    inc dl
    loop .byte
    ret

; Shared AT checksum only. Setup must not republish fixed-segment RAM state.
%ifdef BOARD_RTC_EXTENDED_READ
%include "pc/cmos-checksum.inc"
%else
update_cmos_checksum:
    pushf
    cli
    pushad
    xor bx,bx
    mov dl,0x90
.sum:
    mov al,dl
    out 0x70,al
    in al,0x84
    in al,0x71
    xor ah,ah
    add bx,ax
    inc dl
    cmp dl,0xAE
    jb .sum
    xchg bl,bh
    call .word
    popad
    popf
    ret
.word:
    mov cx,2
.byte:
    mov al,dl
    out 0x70,al
    in al,0x84
    mov al,bl
    out 0x71,al
    shr bx,8
    inc dl
    loop .byte
    ret
%endif

