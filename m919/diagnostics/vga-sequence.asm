; Plain DOS: reports the active step on the POST card. No chipset/CMOS writes.
bits 16
org 0x100
start:
    cld
    mov byte [cs:step],0
.next:
    xor ax,ax
    mov ds,ax
    mov es,ax
    movzx bx,byte [cs:step]
    shl bx,1
    call [cs:stages+bx]
    mov al,[cs:step]
    add al,0x31
    out 0x80,al
    mov si,message
.print:
    cs lodsb
    test al,al
    jz .wait
    mov ah,0x0E
    mov bx,7
    int 0x10
    jmp .print
.wait:
    xor ah,ah
    int 0x16
    cmp al,27
    je .exit
    cmp al,' '
    jne .wait
    inc byte [cs:step]
    cmp byte [cs:step],6
    jb .next
.exit:
    mov ax,0x4C00
    int 0x21
mode3:
    mov ax,3
    int 0x10
    ret
font16:
    mov ax,0x1114
    xor bx,bx
    int 0x10
    ret
blink:
    mov ax,0x1003
    mov bx,1
    int 0x10
    ret
page0:
    mov ax,0x0500
    int 0x10
    ret
full:
    mov bx,0x0030
    jmp restore
full_bh7:
    mov bx,0x0730
restore:
    mov ax,0x1202
    int 0x10
    call mode3
    call font16
    call blink
    call page0
    ret
stages dw mode3,font16,blink,page0,full,full_bh7
step db 0
message db 13,10,'VGASEQ  ABCDEFGHIJKLMNOPQRSTUVWXYZ  abcdefghijklmnopqrstuvwxyz  0123456789',13,10,'Space=next  Esc=exit; report first bad POST code31-36.',13,10,0
