BITS 16
ORG 0x7C00
    xor ax, ax
    mov ds, ax
    cmp dl, EXPECTED_DRIVE
    jne fail
    mov ax, [0x040E]
    mov fs, ax
    cmp byte [fs:0x172], EXPECTED_BOOT
    jne fail
    cmp byte [fs:0x173], EXPECTED_SEEK
    jne fail
    cmp word [0x44A], 80
    jne fail
    cmp byte [0x484], 24
    jne fail
    cmp word [0x485], 16
    jne fail
    cmp byte [0x49E], 0
    jne fail
%ifdef EXPECT_NO_INPUT
    mov ax, [0x41A]
    cmp ax, [0x41C]
    jne fail
%endif
    mov bl, RESULT
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
times 510-($-$$) db 0
dw 0xAA55
