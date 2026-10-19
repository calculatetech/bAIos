bits 16
org 0x7C00
    xor ax,ax
    mov ds,ax
    cmp byte [0x475],1
    jne failed
    mov ax,[0x40E]
    mov fs,ax
    cmp byte [fs:0x20],1
    jne failed
    push es
    mov ax,0xB800
    mov es,ax
    cmp byte [es:160],0xC9
    jne failed
    cmp byte [es:11*160],0xC8
    jne failed
    pop es
    cmp word [0x4FE],0 ; Normal POST clears the previous boot's BDA witness.
    jne failed
    mov word [0x4FE],0xA55A
    mov al,0x37
    out 0x70,al
    in al,0x71
    cmp al,0xA6
    je passed
    cmp al,0xA5
    je second
    mov al,0xA5
    mov si,extended
    mov bp,4
    jmp restart
second:
    mov al,0xA6
    mov si,keypad
    mov bp,3
restart:
    out 0x71,al
    sti
.key:
    pushf
    cli ; Keep the test's D2 parameter separate from timer-driven LED writes.
    lodsb
    mov ah,al
    mov cx,0xFFFF
.command:
    in al,0x64
    test al,2
    loopnz .command
    jnz failed
    mov al,0xD2
    out 0x64,al
    mov cx,0xFFFF
.data:
    in al,0x64
    test al,2
    loopnz .data
    jnz failed
    mov al,ah
    out 0x60,al
    popf
    cmp bp,1
    je .wait
    mov ecx,0x2000000
.consumed:
    in al,0x64
    test al,3
    jnz .pending
    cmp ah,0xE0
    je .next
    mov al,[0x417]
    and al,0x0C
    cmp al,4
    je .control
    cmp al,0x0C
    je .next
.pending:
    dec ecx
    jnz .consumed
    jmp failed
.control:
    cmp ah,0x1D
    jne .pending
.next:
    dec bp
    jmp .key
.wait:
    hlt
    jmp .wait
passed:
    mov al,0x67
    jmp terminal
failed:
    mov al,0x71
    jmp terminal
extended db 0x1D,0x38,0xE0,0x53
keypad db 0x1D,0x38,0x53
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
