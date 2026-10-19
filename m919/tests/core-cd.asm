bits 16
org 0x7C00
xor ax,ax
mov ds,ax
mov al,0x71
cmp dl,0xE0
jne terminal
mov ax,[0x40E]
mov fs,ax
mov al,0x72
cmp byte [fs:0x169],1
jne terminal
cmp word [fs:0x1080],0x170
jne terminal
mov si,status
mov ax,0x4B01
mov dl,0xE0
int 0x13
jc .fail
cmp byte [status+3],1        ; Public CD status identifies the actual channel.
jne .fail
mov al,0x68
jmp terminal
.fail:
mov al,0x73
jmp terminal
status times 19 db 0
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
