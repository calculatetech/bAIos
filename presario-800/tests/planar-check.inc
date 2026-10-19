; Speedsys 4.78 A6D0/A770 use GC word writes and GS byte RMW, not INT10
; pixel services. Draw a cyan frame then verify every byte of every plane.
check_direct_planar:
    pusha
    push gs
    mov ax, 0xA000
    mov gs, ax
    mov dx, 0x3CE
    mov ax, 0x0B00             ; Set/reset color 11.
    out dx, ax
    mov ax, 0x0F01             ; Enable set/reset on all planes.
    out dx, ax
    mov ax, 0xFF08             ; Full-byte horizontal edges.
    out dx, ax
    mov di, 8 * 80 + 1
    mov cx, 78
.horizontal:
    or byte [gs:di], al
    or byte [gs:di + (471 - 8) * 80], al
    inc di
    loop .horizontal
    mov di, 9 * 80 + 1
    mov cx, 462
.vertical:
    mov ax, 0x8008             ; x=8, high bit of byte 1.
    out dx, ax
    or byte [gs:di], al
    mov ax, 0x0108             ; x=631, low bit of byte 78.
    out dx, ax
    or byte [gs:di + 77], al
    add di, 80
    loop .vertical
.verify:
    ; Also used after the original Speedsys drawing code in SPEEDRAW.
    ; Entry has the same saved PUSHA/GS frame and GS=A000.
    mov dx, 0x3CE
    ; Select read mode 0 independently of the drawing setup.
    mov al, 5
    out dx, al
    inc dx
    in al, dx
    and al, 0xF7
    out dx, al
    dec dx
    xor bp, bp
.plane:
    mov ax, bp
    mov ah, al
    mov al, 4
    out dx, ax
    xor di, di
    xor bx, bx                ; Row.
.row:
    xor si, si                ; Byte column.
.byte:
    xor al, al
    cmp bp, 2                 ; Color 11 has no plane 2 bit.
    je .compare
    cmp bx, 8
    jb .compare
    cmp bx, 471
    ja .compare
    cmp si, 1
    jb .compare
    cmp si, 78
    ja .compare
    cmp bx, 8
    je .full
    cmp bx, 471
    je .full
    cmp si, 1
    jne .right
    mov al, 0x80
    jmp .compare
.right:
    cmp si, 78
    jne .compare
    mov al, 1
    jmp .compare
.full:
    mov al, 0xFF
.compare:
    cmp [gs:di], al
    jne .failed
    inc di
    inc si
    cmp si, 80
    jb .byte
    inc bx
    cmp bx, 480
    jb .row
    inc bp
    cmp bp, 4
    jb .plane
    pop gs
    popa
    ret
.failed:
    pop gs
    popa
    mov al, 0x7A
    jmp fail
