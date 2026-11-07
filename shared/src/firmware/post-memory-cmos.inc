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

