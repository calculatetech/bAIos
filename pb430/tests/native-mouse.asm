bits 16
org 0x7C00
xor ax,ax
mov ds,ax
mov es,ax
mov ax,[0x40E]
mov fs,ax
mov ax,0xC201
int 0x15
jc bad
cmp bx,0x00AA
jne bad
mov bx,callback
xor ax,ax
mov es,ax
mov ax,0xC207
int 0x15
jc bad
mov ax,0xC200
mov bh,1
int 0x15
jc bad
mov byte [0x650],0
mov si,packet
mov cx,3
.next:
.wait:
in al,0x64
test al,2
jnz .wait
mov al,0xD3
out 0x64,al
.wait_data:
in al,0x64
test al,2
jnz .wait_data
lodsb
out 0x60,al
.consumed:
in al,0x64
test al,1
jnz .consumed
loop .next
mov cx,0xFFFF
.callback:
cmp byte [0x650],1
je .received
sti
nop
loop .callback
jmp bad
.received:
mov ax,0xC200
xor bx,bx
int 0x15
jc bad
cmp byte [fs:0xB4],0
jne bad
mov al,0x65
jmp terminal
bad:
mov al,0x66
jmp terminal
callback:
push bp
mov bp,sp
cmp word [ss:bp+6],0
jne .wrong
cmp word [ss:bp+8],0x22
jne .wrong
cmp word [ss:bp+10],0x11
jne .wrong
cmp word [ss:bp+12],8
jne .wrong
mov byte [0x650],1
pop bp
retf
.wrong:
mov byte [0x650],2
pop bp
retf
packet db 8,0x11,0x22
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
