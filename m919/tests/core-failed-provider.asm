; A real loaded/signed provider declines boot through the installed INT18.
bits 16
org 0x7C00
    xor ax,ax
    mov ds,ax
    mov fs,[0x40E]
    cmp byte [fs:0x49],0xA5  ; Real boot_candidate owns an active chain.
    jne .fail
    cmp byte [fs:0x48],1     ; It advanced before entering this first provider.
    jne .fail
    cmp word [0x18*4+2],0xF000
    jne .fail
    mov eax,[0x18*4]
    mov [0xB08],eax
    mov byte [0xB0C],0
    mov byte [0xB0D],1
    mov word [0x18*4],observe_int18
    mov word [0x18*4+2],0
    int 0x18
.fail:
    mov al,0x75
%include "test-terminal.inc"
observe_int18:
    inc byte [0xB0C]
    jmp far [0xB08]          ; The real installed BIOS continuation is unchanged.
times 510-($-$$) db 0
dw 0xAA55
