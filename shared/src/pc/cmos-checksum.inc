; AT checksum covers10h..2Dh;2Eh stores the high byte,2Fh the low byte.
update_cmos_checksum:
    pushf
    cli
    pushad
    call cmos_checksum_sum
    xchg bl,bh
    mov cx,2
.write:
    mov al,dl
    out 0x70,al
    in al,0x84
    mov al,bl
    out 0x71,al
    shr bx,8
    inc dl
    loop .write
    call cmos_checksum_acknowledge
    popad
    popf
    ret

; CF=1 on mismatch or failed acknowledgment. Preserve registers and caller IF.
; Clear only the checksum diagnostic after verifying the actual stored bytes.
cmos_checksum_acknowledge:
    pushf
    cli
    pushad
    call cmos_checksum_sum
    mov al,0xAE
    out 0x70,al
    in al,0x84
    in al,0x71
    cmp al,bh
    jne .invalid
    mov al,0xAF
    out 0x70,al
    in al,0x84
    in al,0x71
    cmp al,bl
    jne .invalid
    mov al,0x8E
    out 0x70,al
    in al,0x84
    in al,0x71
    test al,0x40
    jz .valid
    and al,0xBF
    out 0x71,al
    in al,0x84
    in al,0x71
    test al,0x40
    jnz .invalid
.valid:
    popad
    popf
    clc
    ret
.invalid:
    popad
    popf
    stc
    ret

cmos_checksum_sum:
    xor bx,bx
    mov dl,0x90
.byte:
    mov al,dl
    out 0x70,al
    in al,0x84
    in al,0x71
    xor ah,ah
    add bx,ax
    inc dl
    cmp dl,0xAE
    jb .byte
    ret
cmos_checksum_end:
