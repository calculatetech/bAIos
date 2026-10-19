; Guest expectation comes from the machine fixture, never from the BIOS.
%ifndef EXPECTED_MEMORY_KIB
%define EXPECTED_MEMORY_KIB 4096
%endif
    pushf
    cli
    mov ah, 0x88
    int 0x15
    mov bl, al
    mov al, 0x68
    jc fail
    mov al, bl
    cmp ax, EXPECTED_MEMORY_KIB - 1024
    mov al, 0x68
    jne fail
    mov al, 0x30
    out 0x70, al
    in al, 0x71
    mov bl, al
    mov al, 0x31
    out 0x70, al
    in al, 0x71
    mov bh, al
    cmp bx, EXPECTED_MEMORY_KIB - 1024
    mov al, 0x69
    jne fail
    mov al, 0x17
    out 0x70, al
    in al, 0x71
    mov bl, al
    mov al, 0x18
    out 0x70, al
    in al, 0x71
    mov bh, al
    cmp bx, EXPECTED_MEMORY_KIB - 1024
    mov al, 0x69
    jne fail
    mov al, 0x15
    out 0x70, al
    in al, 0x71
    mov bl, al
    mov al, 0x16
    out 0x70, al
    in al, 0x71
    mov bh, al
    cmp bx, 640
    mov al, 0x69
    jne fail
    xor bx, bx
    mov dl, 0x10
.memory_checksum:
    mov al, dl
    out 0x70, al
    in al, 0x71
    xor ah, ah
    add bx, ax
    inc dl
    cmp dl, 0x2E
    jb .memory_checksum
    mov al, 0x2E
    out 0x70, al
    in al, 0x71
    mov ch, al
    mov al, 0x2F
    out 0x70, al
    in al, 0x71
    mov cl, al
    cmp bx, cx
    mov al, 0x69
    jne fail
    out 0xFB, al
    mov al, 1
    out 0xEC, al
    in al, 0xED
    cmp al, 0x96              ; Normal 33 MHz / 70 ns default, independent of firmware constant.
    mov al, 0x68
    jne fail
    mov al, 4
    out 0xEC, al
    in al, 0xED
    and al, 0xF7             ; Bit 3 reports CPU type, not a writable setting.
    cmp al, 0x16             ; OEM drive and RAS timeout, interleave disabled.
    mov al, 0x68
    jne fail
    mov al, 2
    out 0xEC, al
    in al, 0xED
%if EXPECTED_MEMORY_KIB == 8192
    cmp al, 0x8D
%else
    cmp al, 0x8C
%endif
    mov al, 0x68
    jne fail
    mov al, 3
    out 0xEC, al
    in al, 0xED
    cmp al, 0x88
    mov al, 0x68
    jne fail
    out 0xF9, al
    int 0x12
    cmp ax, 639
    mov al, 0x69
    jne fail
    popf
