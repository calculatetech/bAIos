bits 16
org 0x7C00
    xor ax,ax
    mov ds,ax
    mov ax,[0x40E]
    mov fs,ax
    mov al,0x71
    cmp byte [fs:0x175],0
    jne terminal
    cmp byte [fs:0x85],1
    jne terminal
%ifndef TEST_A20_BASELINE
    cmp byte [fs:0x1100],0x90
    jne terminal
%endif
    cli
    mov byte [failure],0x72
    mov al,0xAD
    call command
    mov al,0xA7
    call command
.drain:
    in al,0x64
    test al,1
    jz .output
    in al,0x60
    jmp .drain
.output:
    mov al,0xD0
    call command
    mov cx,0xFFFF
.response:
    in al,0x64
    test al,1
    loopz .response
    jz fail
    in al,0x60
    mov [saved_output],al
    and al,0xFD
    call output
    mov byte [failure],0x73
    call alias
    jne fail                    ; Disabled8042 source must physically wrap1MiB.
    mov al,[saved_output]
    or al,2
    call output
    mov byte [failure],0x74
    call alias
    je fail                     ; Enabled source must expose independent RAM.
    mov al,0xAE
    call command
    mov al,0x6A
    jmp terminal
output:
    push ax
    mov al,0xD1
    call command
    pop ax
    push ax
    call ready
    pop ax
    out 0x60,al
    jmp ready
command:
    push ax
    call ready
    pop ax
    out 0x64,al
    jmp ready
ready:
    push cx
    mov cx,0xFFFF
.poll:
    in al,0x64
    test al,2
    loopnz .poll
    pop cx
    jnz fail
    ret
alias:
    push es
    mov ax,0xFFFF
    mov es,ax
    mov dl,[0x500]
    mov dh,[es:0x510]
    mov byte [0x500],0
    mov byte [es:0x510],0xFF
    cmp byte [0x500],0xFF
    mov [es:0x510],dh
    mov [0x500],dl
    pop es
    ret
fail:
    mov al,[failure]
    jmp terminal
saved_output db 0
failure db 0x71
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
