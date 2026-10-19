; Exercise the retained video BIOS, not a replacement renderer.
check_vga:
    pusha
    push es
    push fs
    xor ax, ax
    mov fs, ax
    mov ax, 0x0012             ; 640x480, four VGA planes.
    int 0x10
    call check_direct_planar
    mov ax, 0x0012             ; Clear the direct-write pattern before pixels.
    int 0x10
    mov si, .pixels
.write_pixel:
    cs lodsw
    mov cx, ax
    cs lodsw
    mov dx, ax
    cs lodsw
    xor bx, bx
    mov ah, 0x0C
    int 0x10
    cmp si, .pixels_end
    jb .write_pixel
    mov si, .pixels
.read_pixel:
    cs lodsw
    mov cx, ax
    cs lodsw
    mov dx, ax
    cs lodsw
    mov di, ax
    xor bx, bx
    mov ah, 0x0D
    int 0x10
    xor ah, ah
    cmp ax, di
    mov al, 0x71
    jne fail
    cmp si, .pixels_end
    jb .read_pixel

    ; Chris's Allegro 2 driver can choose native Cirrus instead of VBE.
    ; Mirror its 640x480 mode with a 1024-pixel virtual pitch.
    mov ax, 0x005F
    int 0x10
    mov dx, 0x03D4
    mov al, 0x13
    out dx, al
    inc dx
    in al, dx
    xor ah, ah
    mov bx, 1024
    mul bx
    mov bx, 640
    div bx
    test ah, ah
    mov bl, al
    mov al, 0x78
    jnz fail
    mov al, bl
    mov dx, 0x03D5
    out dx, al
    mov dx, 0x03CE
    mov al, 0x0B
    out dx, al
    inc dx
    in al, dx
    and al, 0xDE
    out dx, al
    dec dx
    mov ax, 0x0009             ; Native bank 0, in 4 KiB units.
    out dx, ax
    mov ax, 0xA000
    mov es, ax
    mov word [es:16], 0x3579
    mov ax, 0x1009             ; Native bank 16 = 64 KiB.
    out dx, ax
    mov word [es:16], 0x468A
    mov ax, 0x0009
    out dx, ax
    cmp word [es:16], 0x3579
    mov al, 0x78
    jne fail
    mov ax, 0x1009
    out dx, ax
    cmp word [es:16], 0x468A
    mov al, 0x78
    jne fail
    ; The native scroll/teardown path waits for both retrace transitions.
    mov dx, 0x03DA
    xor bl, bl
.retrace_phase:
    mov ecx, 0x100000
.retrace:
    in al, dx
    and al, 8
    cmp al, bl
    je .transition
    dec ecx
    jnz .retrace
    mov al, 0x79
    jmp fail
.transition:
    xor bl, 8
    jnz .retrace_phase

    push cs
    pop es
    mov di, .mode_info
    mov ax, 0x4F01
    mov cx, 0x0101             ; 640x480x8, already working in PC Player.
    int 0x10
    cmp ax, 0x004F
    mov al, 0x72
    jne fail
    cmp word [es:.mode_info + 18], 640
    jne fail
    cmp word [es:.mode_info + 20], 480
    jne fail
    cmp byte [es:.mode_info + 25], 8
    jne fail
    mov ax, 64
    xor dx, dx
    mov bx, [es:.mode_info + 4] ; Bank granularity in KiB.
    test bx, bx
    jz fail
    div bx
    test dx, dx
    mov dx, ax
    mov al, 0x72
    jnz fail
    mov [cs:.bank64k], dx
    mov ax, 0x4F02
    mov bx, 0x0101
    int 0x10
    cmp ax, 0x004F
    mov al, 0x73
    jne fail
    xor dx, dx
    call .bank
    mov ax, 0xA000
    mov es, ax
    mov word [es:16], 0x1357
    mov dx, [cs:.bank64k]
    call .bank
    mov word [es:16], 0x2468
    xor dx, dx
    call .bank
    cmp word [es:16], 0x1357
    mov al, 0x74
    jne fail
    mov dx, [cs:.bank64k]
    call .bank
    cmp word [es:16], 0x2468
    mov al, 0x74
    jne fail
    mov ax, 3
    int 0x10

    ; IRQ0 pending with IF=0 must run inside the public INT10 entry.
    ; Caller IF must still be restored clear by IRET.
    cli
    mov eax, [fs:0x1C * 4]
    mov [cs:.old1c], eax
    mov byte [cs:.irq_active], 1
    mov word [fs:0x1C * 4], .tick
    mov [fs:0x1C * 4 + 2], cs
    mov word [cs:.ticks], 0
    mov ecx, 0x100000
.pending:
    mov al, 0x0A
    out 0x20, al
    in al, 0x20
    test al, 1
    jnz .query
    dec ecx
    jnz .pending
    mov al, 0x75
    jmp fail
.query:
    mov ah, 0x0F
    int 0x10
    cmp word [cs:.ticks], 0
    mov al, 0x76
    je fail
    pushf
    pop ax
    test ax, 0x0200
    mov al, 0x77
    jnz fail
    call restore_vga_test_irq
    sti
    pop fs
    pop es
    popa
    ret

.bank:
    mov ax, 0x4F05
    xor bx, bx
    int 0x10
    cmp ax, 0x004F
    mov al, 0x74
    jne fail
    ret
.tick:
    inc word [cs:.ticks]
    iret
.ticks: dw 0
.bank64k: dw 0
.old1c: dd 0
.irq_active: db 0
.pixels:
    dw 0,0,1, 639,0,2, 0,479,4, 639,479,8, 321,241,15
.pixels_end:
.mode_info: times 256 db 0

; Also used by the DOS wrapper's failure path before it releases its memory.
restore_vga_test_irq:
    pushf
    cli
    push eax
    push es
    cmp byte [cs:check_vga.irq_active], 0
    je .done
    xor ax, ax
    mov es, ax
    mov eax, [cs:check_vga.old1c]
    mov [es:0x1C * 4], eax
    mov byte [cs:check_vga.irq_active], 0
.done:
    pop es
    pop eax
    popf
    ret

%include "planar-check.inc"
