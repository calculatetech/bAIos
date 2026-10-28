bits 16
org 0x100

    push cs
    pop ds
    smsw ax
    test al,1
    jnz .protected
    mov dx,intro
    mov ah,9
    int 0x21
    mov bl,0x5A
.show:
    mov dx,value_5a
    cmp bl,0x5A
    je .print
    mov dx,value_a5
.print:
    mov ah,9
    int 0x21
.poll:
    mov al,bl
    out 0x80,al
    mov ah,1
    int 0x16
    jz .poll
    xor ah,ah
    int 0x16
    cmp al,27
    je .exit
    cmp al,' '
    jne .poll
    xor bl,0xFF
    jmp .show
.protected:
    mov dx,real_mode
    mov ah,9
    int 0x21
    mov ax,0x4C01
    int 0x21
.exit:
    mov ax,0x4C00
    int 0x21

intro db 'POST80: Run in plain DOS. Space switches values; Esc exits.',13,10,'$'
value_5a db 'Writing 5A to port 80h.',13,10,'$'
value_a5 db 'Writing A5 to port 80h.',13,10,'$'
real_mode db 'Run in real-mode DOS without a memory manager.',13,10,'$'
