; DOS VGA check: video-memory writes only; does not write disk sectors.
; Codes: 71 planar pixels, 72 VBE info, 73 VBE mode, 74 VBE banks,
; 75 IRQ0 not pending, 76 IRQ0 blocked inside INT10, 77 caller IF changed,
; 78 native Cirrus banks/pitch, 79 native retrace, 7A direct planar writes.
bits 16
org 0x100
start:
    mov dx, message
    mov ah, 9
    int 0x21
    call check_vga
    mov al, 0x67
fail:
    mov [cs:result], al
    call restore_vga_test_irq
    sti
    mov ax, 3
    int 0x10
    push cs
    pop ds
    mov al, [result]
    mov ah, al
    shr al, 4
    call hex
    mov [digits], al
    mov al, ah
    and al, 15
    call hex
    mov [digits + 1], al
    mov dx, result_message
    mov ah, 9
    int 0x21
%ifdef EMULATOR_TEST
    mov dx, 0x80
    mov al, '8'
    out dx, al
    mov al, '6'
    out dx, al
    mov al, 'B'
    out dx, al
    mov al, 'o'
    out dx, al
    mov al, 'x'
    out dx, al
    mov al, 1
    out dx, al
    mov al, 5
    out dx, al
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, [result]
    out dx, al
%endif
    mov al, [result]
    cmp al, 0x67
    jne .exit
    xor al, al
.exit:
    mov ah, 0x4C
    int 0x21
hex:
    add al, '0'
    cmp al, '9'
    jbe .done
    add al, 7
.done:
    ret
message: db 'VGA check: planar, native Cirrus, VESA, IRQ delivery.',13,10,'$'
result_message: db 'VGA check result: '
digits: db '00', ' (67 = PASS)',13,10,'$'
result: db 0

%include "vga-check.inc"
