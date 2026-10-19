bits 16
org 0x9000
cli
xor ax,ax
mov ds,ax
mov word [IRQ_VECTOR*4],handler
mov word [IRQ_VECTOR*4+2],0
mov byte [0xB91],0
in al,0xA1
and al,~(1 << (IRQ_NUMBER-8))
out 0xA1,al
in al,0x21
and al,0xFB
out 0x21,al
mov dx,0x300
mov al,1
out dx,al
sti
.first: cmp byte [0xB91],1
jne .first
mov al,1
out dx,al
.second: cmp byte [0xB91],2
jne .second
cli
nop
terminal: hlt
handler:
push ax
push dx
mov dx,0x300
xor al,al
out dx,al
inc byte [0xB91]
mov al,0x20
out 0xA0,al
out 0x20,al
pop dx
pop ax
iret
