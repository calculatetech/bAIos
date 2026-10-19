; Independent OEM bus baseline, checked after every cold/warm guest boot.
    pushf
    cli
    out 0xFB, al
    mov al, 6
    out 0xEC, al
    in al, 0xED
    and al, 0xFB               ; BOSCSNS is a read-only input pin.
    cmp al, 0
    mov al, 0x57
    jne fail
    mov al, 8
    out 0xEC, al
    in al, 0xED
    cmp al, 0x38
    mov al, 0x58
    jne fail
    mov al, 9
    out 0xEC, al
    in al, 0xED
    cmp al, 0x30
    mov al, 0x59
    jne fail
    out 0xF9, al
    popf
