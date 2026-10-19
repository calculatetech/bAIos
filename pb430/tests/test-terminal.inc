terminal:
    and al,0x7F                 ; The provider clamps larger exit codes.
    mov bl,al
    cli
    mov dx,0x80
    mov al,'8'
    out dx,al
    mov al,'6'
    out dx,al
    mov al,'B'
    out dx,al
    mov al,'o'
    out dx,al
    mov al,'x'
    out dx,al
    mov al,1
    out dx,al
    mov al,5
    out dx,al
    mov dx,0x501
    mov al,4
    out dx,al
    inc dx
    mov al,bl
    out dx,al
.halt:
    hlt
    jmp .halt
