bits 16
org 0x100
    push cs
    pop ds
    mov ax, 0x1500
    xor bx, bx
    int 0x2F
    test bx, bx
    jz fail
    mov dx, source
    mov ax, 0x3D00
    int 0x21
    jc fail
    mov [cd_handle], ax
    mov dx, destination
    xor cx, cx
    mov ah, 0x3C
    int 0x21
    jc fail
    mov [hd_handle], ax
    mov bp, 16
.block:
    mov bx, [cd_handle]
    mov dx, buffer
    mov cx, 4096
    mov ah, 0x3F
    int 0x21
    jc fail
    cmp ax, cx
    jne fail
    mov si, buffer
    xor al, al
.verify:
    cmp [si], al
    jne fail
    inc al
    inc si
    loop .verify
    mov bx, [hd_handle]
    mov dx, buffer
    mov cx, 4096
    mov ah, 0x40
    int 0x21
    jc fail
    cmp ax, cx
    jne fail
    dec bp
    jnz .block
    mov bx, [hd_handle]
    mov ah, 0x3E
    int 0x21
    jc fail
    mov bx, [cd_handle]
    mov ah, 0x3E
    int 0x21
    jc fail
    mov bl, 0x67
    jmp exit
fail:
    mov bl, 0x7A
exit:
    mov si, trigger
    mov dx, 0x80
    mov cx, 7
.trigger:
    lodsb
    out dx, al
    loop .trigger
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
    cli
.halt:
    hlt
    jmp .halt
trigger db '86Box',1,5
source db 'D:\PROBE.BIN',0
destination db 'C:\CDCOPY.BIN',0
cd_handle dw 0
hd_handle dw 0
buffer equ $ + 256
