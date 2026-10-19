bits 16
org 0x7C00
%include "test-configuration.inc"
xor ax,ax
mov ds,ax
mov es,ax
mov ax,[0x40E]
mov fs,ax
cmp byte [fs:0x175],TEST_EXPECT_ERROR
jne bad
mov ax,[0x410]
and ax,0xC1
cmp byte [fs:0x1EB],0
je .disabled
cmp ax,1
jne bad
cmp word [fs:0x80],4
jne bad
jmp .read
.disabled:
test ax,ax
jnz bad
cmp word [fs:0x80],0
jne bad
.read:
mov bx,0x8000
mov ax,0x0201
mov cx,1
xor dx,dx
int 0x13
jnc bad
test ah,ah
jz bad
test al,al
jnz bad
cmp ah,[0x441]
jne bad
mov [0x650],ax
pushf
pop ax
mov [0x652],ax
mov si,dap
mov ax,0x4300
mov dl,0x80
int 0x13
jc bad
mov al,0x65
jmp terminal
bad:
mov al,0x66
jmp terminal
dap db 0x10,0
dw 1,0x600,0
dq 17
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
