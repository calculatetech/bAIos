print_string:
    push ax
    push bx
    mov bx, 0x0007
.next:
    cs lodsb
    test al, al
    jz .done
    mov ah, 0x0E
    int 0x10
    jmp .next
.done:
    pop bx
    pop ax
    ret
