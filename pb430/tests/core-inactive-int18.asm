bits 16
org 0
db 0x55,0xAA,4
jmp initialize
initialize:
xor ax,ax
mov ds,ax
mov ax,[0x40E]
mov fs,ax
cmp byte [fs:0x49],0xA5
je bad
inc word [0x620]
int 0x18
bad:
mov word [0x624],0xBAD
hlt
times 2047-($-$$) db 0
db 0
