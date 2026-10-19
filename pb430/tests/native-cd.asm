bits 16
org 0x7C00
%include "test-configuration.inc"
xor ax,ax
mov ds,ax
cmp dl,0xE0*(TEST_CD_MEDIA=0)
jne bad
mov ax,[0x40E]
mov fs,ax
mov bx,TEST_CD_SLOT*0x200
cmp byte [fs:bx+0x169],1
jne bad
cmp byte [fs:bx+0x13F],1
jne bad
mov si,status
mov ax,0x4B01
mov dl,0xE0*(TEST_CD_MEDIA=0)
int 0x13
jc bad
cmp byte [status+3],0
jne bad
cmp word [status+8],TEST_CD_SLOT
jne bad
cmp word [status+12],0x7C0
jne bad
%if TEST_CD_MEDIA
xor ax,ax
mov es,ax
mov bx,0x8000
mov cx,2
xor dx,dx
mov ax,0x0201
int 0x13
jc bad
cmp dword [0x8000],0x03020100
jne bad
%endif
mov ax,0x4B00
mov dl,0xE0*(TEST_CD_MEDIA=0)
int 0x13
jc bad
mov ax,[fs:0x27E]
cmp ax,[0x410]
jne bad
cmp byte [fs:0x298],0
jne bad
cmp dword [0x4C],0xF0000000|TEST_INT13_OFFSET
jne bad
mov al,0x68
jmp terminal
bad:
mov al,0x69
jmp terminal
status times 19 db 0
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
