memory_decimal:
    xor dx, dx
    mov bx, 10
    div bx
    test ax, ax
    jz .digit
    push dx
    call memory_decimal
    pop dx
.digit:
    mov al, dl
    add al, '0'
    jmp memory_character
memory_hex_byte:
    push ax
    shr al, 4
    call .digit
    pop ax
    and al, 15
.digit:
    add al, '0'
    cmp al, '9'
    jbe memory_character
    add al, 7
memory_character:
    push ax
    push bx
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    pop bx
    pop ax
    ret
