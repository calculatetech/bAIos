bits 16
org 0x100
    push cs
    pop ds
    cld
    mov ax,0x3000
    int 0x21
    cmp ax,0x1606
    jne failed
    mov ax,0x4300
    int 0x2F
    cmp al,0x80
    jne failed
    mov al,0x37
    out 0x70,al
    in al,0x71
    cmp al,0x5A
    je passed
    mov al,0x5A
    out 0x71,al
%ifdef TEST_COMMAND_PROMPT
    mov ax,0x4C00
    int 0x21
%endif
    xor ax,ax
    mov es,ax
    mov si,scans
%ifdef TEST_EXTENDED_DELETE
    mov bp,4
%else
    mov bp,3
%endif
.key:
    lodsb
    call inject_scan
    cmp bp,1
    je .wait
    mov ah,4
%ifdef TEST_EXTENDED_DELETE
    cmp bp,4
%else
    cmp bp,3
%endif
    je .expected
    mov ah,0x0C
.expected:
    mov ecx,0x2000000
.modifier:
    mov al,[es:0x417]
    and al,0x0C
    cmp al,ah
    je .next
    dec ecx
    jnz .modifier
    jmp failed
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
%ifdef TEST_EXTENDED_DELETE
scans db 0x1D,0x38,0xE0,0x53
%else
scans db 0x1D,0x38,0x53
%endif
inject_scan:
    push cx
    mov ah,al
    mov cx,0xFFFF
.command:
    in al,0x64
    test al,2
    loopnz .command
    mov al,0xD2
    out 0x64,al
    mov cx,0xFFFF
.data:
    in al,0x64
    test al,2
    loopnz .data
    mov al,ah
    out 0x60,al
    mov cx,0xFFFF
.consumed:
    in al,0x64
    test al,3
    loopnz .consumed
    pop cx
    ret
%include "test-terminal.inc"
