; Boot the real selected VGA ROM and record final hardware state per mode.
bits 16
org 0x7C00
%include "boards/presario800.inc"
%define BUFFER 0x1000

start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti
    cld
    mov si, stage_dap
    mov ax, 0x4200
    mov dl, 0x80
    int 0x13
    mov al, 1
    jc fail
    jmp 0:stage2
stage_dap:
    db 16,0
    dw 15,stage2,0
    dq 1
fail:
    mov bl, al
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
    mov al, bl
    out dx, al
.halt:
    cli
    hlt
    jmp .halt
times 510-($-$$) db 0
dw 0xAA55

stage2:
    cmp word [0x40], VGA_INT10_ENTRY
    mov al, 2
    jne fail
    cmp word [0x42], VGA_SEGMENT
    jne fail
    cmp word [0x108], 0xF065
    jne fail
    cmp word [0x10A], 0xF000
    jne fail
    mov ah, 0x0F
    int 0x10
    mov [query], ax
    mov [query+2], bx
    mov ah, 0x0F
    int 0x42
    cmp ax, [query]
    mov al, 3
    jne fail
    cmp bx, [query+2]
    jne fail
    mov di, BUFFER
    mov cx, 256
    xor ax, ax
    rep stosw
    mov di, BUFFER
    mov ax, 0x4F00
    int 0x10
    push ax
    pusha
    mov dword [dump_dap+8], 31
    mov si, dump_dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov word [dump_dap+2], 1
    mov dword [dump_dap+8], 32
    popa
    pop ax
    cmp ax, 0x004F
    mov al, 4
    jne fail
    cmp dword [BUFFER], 'VESA'
    mov al, 0x14
    jne fail
    cmp word [BUFFER+18], 16 ; Fixed soldered 1 MiB, in 64 KiB units.
    mov al, 0x15
    jne fail
    mov ax, [BUFFER+4]
    mov [vbe_version], ax
    xor bp, bp
    call snapshot
    mov ax, 3
    int 0x10
    mov bp, 3
    call snapshot
    ; Same scan-line/mode/font sequence as setup_video_mode.
    mov ax, 0x1202
    mov bl, 0x30
    int 0x10
    mov ax, 3
    int 0x10
    mov ax, 0x1112
    xor bx, bx
    int 0x10
    cmp byte [0x484], 49
    mov al, 5
    jne fail
    cmp word [0x485], 8
    jne fail
    mov bp, 0x0503
    call snapshot
    mov ax, 0x1202
    mov bl, 0x30
    int 0x10
    mov ax, 3
    int 0x10
    mov ax, 0x1114
    xor bx, bx
    int 0x10
    cmp byte [0x484], 24
    mov al, 6
    jne fail
    cmp word [0x485], 16
    jne fail
    mov bp, 0x0603
    call snapshot
    mov ax, 0x12
    int 0x10
    mov bp, 0x12
    call snapshot
    mov ax, 0x13
    int 0x10
    mov bp, 0x13
    call snapshot
    mov si, modes
.mode:
    lodsw
    test ax, ax
    jz .memory
    push si
    mov bp, ax
    mov bx, ax
    mov ax, 0x4F02
    int 0x10
    cmp ax, 0x004F
    mov al, 7
    jne fail
    call snapshot
    pop si
    jmp .mode
.memory:
    mov ax, 0x4F02
    mov bx, 0x101
    int 0x10
    cmp ax, 0x004F
    mov al, 8
    jne fail
    ; Native Cirrus 4 KiB banks: distinguish zero, 512 KiB, and 1 MiB alias.
    mov dx, 0x3CE
    mov ax, 0x000B
    out dx, ax
    mov ax, 0x0009
    out dx, ax
    mov ax, 0xA000
    mov es, ax
    mov word [es:16], 0x1357
    mov ax, 0x8009
    out dx, ax
    mov word [es:16], 0x2468
    mov ax, 0x0009
    out dx, ax
    cmp word [es:16], 0x1357
    mov al, 9
    jne fail
    mov ax, 0x8009
    out dx, ax
    cmp word [es:16], 0x2468
    mov al, 9
    jne fail
    mov ax, 0xFF09
    out dx, ax
    mov word [es:16], 0x3579 ; Last 4 KiB bank of the installed 1 MiB.
    cmp word [es:16], 0x3579
    mov al, 9
    jne fail
    xor ax, ax
    mov es, ax
    call check_vga
    mov al, 0x67
    jmp fail

snapshot:
    pusha
    push es
    xor ax, ax
    mov es, ax
    mov di, BUFFER
    mov cx, 256
    rep stosw
    mov dword [BUFFER], 'VGAR'
    mov [BUFFER+4], bp
    mov ax, [vbe_version]
    mov [BUFFER+6], ax
    mov dx, 0x3CC
    in al, dx
    mov [BUFFER+8], al
    mov dx, 0x3C8
    in al, dx               ; Reset hidden DAC access counter.
    mov dx, 0x3C6
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    mov [BUFFER+9], al
    mov dx, 0x3C8
    in al, dx
    mov al, [0x449]
    mov [BUFFER+10], al
    mov al, [0x484]
    mov [BUFFER+11], al
    mov ax, [0x44A]
    mov [BUFFER+12], ax
    mov ax, [0x485]
    mov [BUFFER+14], ax
    mov dx, 0x3C4
    in al, dx
    push ax
    mov ax, 0x1206          ; Unlock only to observe extended registers.
    out dx, ax
    mov di, BUFFER+16
    mov cx, 32
    call indexed
    pop ax
    out dx, al
    mov dx, 0x3D4
    in al, dx
    push ax
    mov di, BUFFER+48
    mov cx, 40
    call indexed
    pop ax
    out dx, al
    mov dx, 0x3CE
    in al, dx
    push ax
    mov di, BUFFER+88
    mov cx, 64
    call indexed
    pop ax
    out dx, al
    ; Reading AC uses its address phase; restore its index and display enable.
    mov dx, 0x3C0
    in al, dx
    push ax
    mov di, BUFFER+152
    xor bx, bx
.attribute:
    mov dx, 0x3DA
    in al, dx
    mov dx, 0x3C0
    mov al, bl
    or al, 0x20
    out dx, al
    inc dx
    in al, dx
    stosb
    inc bl
    cmp bl, 21
    jb .attribute
    mov dx, 0x3DA
    in al, dx
    mov dx, 0x3C0
    pop ax
    out dx, al
    mov eax, [0x40]
    mov [BUFFER+174], eax
    mov eax, [0x108]
    mov [BUFFER+178], eax
    mov ax, VGA_SEGMENT
    mov es, ax
    mov eax, [es:0]
    mov [BUFFER+182], eax
    mov ax, [es:4]
    mov [BUFFER+186], ax
    xor ax, ax
    mov es, ax
    mov si, dump_dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 10
    jc fail
    inc dword [dump_dap+8]
    mov word [dump_dap+2], 1
    pop es
    popa
    ret
indexed:
    xor bx, bx
.read:
    mov al, bl
    out dx, al
    inc dx
    in al, dx
    stosb
    dec dx
    inc bl
    loop .read
    ret
dump_dap:
    db 16,0
    dw 1,BUFFER,0
    dq 32
query: dd 0
vbe_version: dw 0
modes: dw 0x101,0x102,0x103,0x104,0x105,0x106,0x111,0x112,0
%include "vga-check.inc"
times 16*512-($-$$) db 0
