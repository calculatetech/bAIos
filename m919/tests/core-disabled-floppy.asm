bits 16
org 0x7C00
    xor ax,ax
    mov ds,ax
    mov fs,[0x40E]
    mov al,0x71
    cmp byte [fs:0x1E6+5],0 ; Actual persisted ports policy was applied.
    jne terminal
    cmp word [fs:0x80],0
    jne terminal
    test byte [0x410],1
    jnz terminal
    cmp byte [fs:0x175],0
    jne terminal
    mov ax,0x1500
    xor dl,dl
    int 0x13
    jc .fail
    test ah,ah
    jnz .fail
    mov ax,0x0201
    mov bx,0x8000
    mov cx,1
    xor dx,dx
    int 0x13
    jnc .fail
    cmp ah,1
    jne .fail
    mov al,0x69
    jmp terminal
.fail:
    mov al,0x72
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
