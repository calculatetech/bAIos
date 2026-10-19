bits 16
org 0x7C00
%include "test-configuration.inc"
%include "pc/state.inc"
jmp short start
times 11-($-$$) db 0
dw 512
db 1
dw 1
times 24-($-$$) db 0
dw 63,16
dd 0
times 62-($-$$) db 0
start:
    xor ax,ax
    mov ds,ax
    mov fs,[0x40E]
    mov al,0x72
    cmp byte [fs:P_RAM_FLAGS],TEST_RAM_FLAGS
    jne terminal
    mov al,0x73
%if TEST_RAM_PROOF_RECOVERY
    cmp byte [fs:C_CHIP+1],0
    jne terminal
    mov al,0x37
    out 0x70,al
    in al,0x71
    cmp al,2
    jne terminal
    mov al,0x69
    out 0x70,al
    in al,0x71
    cmp al,0xD2
    jne terminal
    mov al,0x36
    out 0x70,al
    in al,0x71
    cmp al,0x1A
    jne terminal
%else
    cmp byte [0xB34],1
    jne terminal
%endif
    mov al,0x74
    cmp byte [fs:S_SETUP_REQUEST],0
    jne terminal
    mov al,0x75
    cmp byte [0x400+KB_POST_STATE],0
    jne terminal
%if TEST_RAM_PROOF_RECOVERY
%elif TEST_RAM_FLAGS = 2
    mov al,0x76
    cmp word [0x41E],0x1E61 ; Ordinary IRQ1 input survived Esc.
    jne terminal
%elif TEST_RAM_PROOF_DELETE
    cmp byte [fs:C_CHIP],0x40
    jne terminal
    cmp byte [fs:C_VALID],1
    jne terminal
    cmp dword [fs:C_PORTS],0x03010403
    jne terminal
    cmp word [0x400],0x3E8
    jne terminal
    mov al,0x69
    out 0x70,al
    in al,0x71
    cmp al,0x56
    jne terminal
%else
    cmp byte [0x400+KB_PAUSED],0
    jne terminal
    cmp byte [0x400+KB_PAUSE_OWNER],0
    jne terminal
    cmp byte [0xB35],16
    jne terminal
    mov ax,[0x41A]
    cmp ax,[0x41C]
    jne terminal
%endif
    mov ax,0x0800
    mov dl,0x80
    int 0x13
    jc terminal
    and cl,63
    cmp cl,63
    jne terminal
    mov al,0x68
    jmp terminal
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
