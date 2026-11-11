; A DOS-owned full segment permits a 16-bit stack to wrap at offset zero.
bits 16
org 0x100
    push cs
    pop ds
    mov ax,cs
    add ax,0x2000
    cmp ax,[2]
    ja .failed
    mov ax,0xF000
    mov es,ax
    xor bx,bx
.scan:
    cmp dword [es:bx],0x506E5024
    je .found
    add bx,16
    jnc .scan
    jmp .failed
.found:
    mov eax,[es:bx+13]
    mov [entry],eax
    mov ax,cs
    add ax,0x1000
    cli
    mov ss,ax
%ifndef TEST_STACK_TOP
%define TEST_STACK_TOP 0x80
%endif
    mov sp,TEST_STACK_TOP
    sti
    push word 0x40
    push word 1
    push cs
    push word node
    push cs
    push word handle
    push word 1
    call far [cs:entry]
    add sp,14
    test ax,ax
    jnz .failed
    cmp byte [cs:handle],1
    jne .failed
    cmp word [cs:node],29
    jne .failed
    cmp dword [cs:node+3],0x0000D041
    jne .failed
    mov al,0x66
    jmp terminal
.failed:
    mov al,0x67
    jmp terminal
entry dd 0
handle db 0
node times 128 db 0
%include "test-terminal.inc"
