bits 16
org 0x7C00
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov di, 1
    cmp dl, 0x80
    jne fail
    mov ax, [0x40E]
    mov fs, ax
    cmp byte [fs:0x20], MASTER_ATA
    jne fail
    inc di
    cmp byte [fs:0x169], MASTER_PACKET
    jne fail
    inc di
    cmp byte [fs:0x220], SLAVE_ATA
    jne fail
    inc di
    cmp byte [fs:0x369], SLAVE_PACKET
    jne fail
    inc di
    cmp byte [0x475], MASTER_ATA + SLAVE_ATA
    jne fail
    mov dl, 0x80
    mov bp, 0xA001
%if MASTER_ATA == 0
    inc bp
%endif
.drive:
    mov di, 6
    push dx
    mov ah, 8
    int 0x13
    jc fail
    cmp dl, MASTER_ATA + SLAVE_ATA
    jne fail
    pop dx
    inc di
    mov ax, 0x0201
    mov cx, 2
    xor dh, dh
    mov bx, 0x1000
    int 0x13
    jc fail
    cmp [0x1000], bp
    jne fail
    inc di
    ; Read/write a disposable sector and prove routing on both legacy paths.
    mov cx, 3
    mov ax, 0x0301
    int 0x13
    jc fail
    inc di
    mov word [0x1000], 0
    mov ax, 0x0201
    int 0x13
    jc fail
    cmp [0x1000], bp
    jne fail
    inc di
    ; EDD42 reads the distinct marker from the same physical device.
    mov word [dap + 2], 1
    mov si, dap
    mov ah, 0x42
    int 0x13
    jc fail
    cmp [0x1000], bp
    jne fail
    inc di
    mov si, parameters
    mov word [si], 30
    mov ah, 0x48
    int 0x13
    jc fail
    inc di
    mov eax, 131072
    cmp bp, 0xA001
    je .capacity
    mov eax, 196608
.capacity:
    cmp [si + 16], eax
    jne fail
    inc di
    mov ah, 0
    int 0x13
    jc fail
    ; A full block plus a final partial block, after shared-channel reset.
    push di
    mov di, 0x1000
    mov ax, bp
    mov cx, 19 * 256
    rep stosw
    pop di
    inc di
    mov ax, 0x0313
    mov cx, 9
    int 0x13
    jc fail
    mov word [0x1000], 0
    mov word [0x35FE], 0
    mov ax, 0x0213
    int 0x13
    jc fail
    inc di
    cmp [0x1000], bp
    jne fail
    cmp [0x35FE], bp
    jne fail
    mov word [dap + 2], 19
    mov word [dap + 8], 40
    mov si, dap
    mov ax, 0x4300
    int 0x13
    jc fail
    mov word [0x35FE], 0
    mov word [dap + 2], 19
    mov ah, 0x42
    int 0x13
    jc fail
    inc di
    cmp [0x35FE], bp
    jne fail
    mov word [dap + 8], 1
%if MASTER_ATA + SLAVE_ATA == 2
    cmp dl, 0x80
    jne .done
    inc dl
    inc bp
    jmp .drive
%endif
.done:
%ifdef INTERACTIVE_GUEST
    mov si, message
.message:
    lodsb
    test al, al
    jz .preview_wait
    mov ah, 0x0E
    xor bx, bx
    int 0x10
    jmp .message
.preview_wait:
    sti
    hlt
    jmp .preview_wait
message db 'Virtual ATA/ATAPI checks passed. Ctrl+Alt+Del to repeat.',13,10,0
%endif
    mov bl, 0x67
    jmp exit
fail:
    mov bx, di
    add bl, 0x70
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
dap db 16,0
    dw 1,0x1000,0
    dq 1
parameters times 30 db 0
times 510-($-$$) db 0
dw 0xAA55
