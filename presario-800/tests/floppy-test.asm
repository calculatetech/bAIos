bits 16
org 0x7C00
%ifndef TYPE_A
%define TYPE_A 4
%define TYPE_B 2
%define MEDIA_A 4
%define MEDIA_B 2
%endif
start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti
    cld
    mov ax, 0x020F
    mov bx, stage2
    mov cx, 2
    mov dx, 0x0080
    int 0x13
    jc fail
    jmp stage2
times 510-($-$$) db 0
dw 0xAA55
stage2:
    ; Preserve the POST text, including the diagnostic ROM's read-only report.
    ; This write targets only the disposable test HDD, never a physical disk.
    mov si, post_packet
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    jc fail
    xor ax, ax
    mov es, ax
    mov byte [drive], 0
.drive:
    mov byte [step], 1
    call progress
    mov dl, [drive]
    mov ah, 8
    int 0x13
    jc fail
    xor ax, ax
    mov es, ax
    movzx si, byte [drive]
    cmp bl, [types+si]
    jne fail
    cmp dl, 2
    jne fail
    mov byte [step], 2
    call progress
    mov dl, [drive]
    mov ah, 0
    int 0x13
    jc fail
    movzx si, byte [drive]
    movzx si, byte [media+si]
    shl si, 1
    mov cx, [geometry+si]
    mov [maximum], ch
    mov [spt], cl
%ifndef READ_ONLY
    mov dl, [drive]
    mov ah, 0x18
    int 0x13
    jc fail
%endif
    xor ax, ax
    mov es, ax
    mov byte [cylinder], 0
.cylinder:
    mov byte [head], 0
.head:
%ifndef READ_ONLY
    mov byte [step], 3
    call progress
    mov bx, ids
    xor si, si
    xor cx, cx
    mov cl, [spt]
.ids:
    mov al, [cylinder]
    mov [bx+si], al
    mov al, [head]
    mov [bx+si+1], al
    mov ax, si
    shr al, 2
    inc al
    mov [bx+si+2], al
    mov byte [bx+si+3], 2
    add si, 4
    loop .ids
    call chs
    mov ah, 5
    int 0x13
%ifdef WRITE_PROTECTED
    jnc fail
    cmp ah, 3
    jne fail
    inc byte [drive]
    cmp byte [drive], 2
    jb .drive
    mov al, 0x68
    jmp exit_emulator
%endif
    jc fail
    mov al, [cylinder]
    test al, al
    jz .data
    cmp al, [maximum]
    je .data
    cmp al, 39
    jne .next
%endif
.data:
    mov byte [step], 4
    mov bx, 0
    mov ax, 0x1000
    mov es, ax
    call chs
    mov ah, 2
    std
    cli
    call checked_floppy_read
    jc fail
    call chs
    mov ah, 2
    sti
    call checked_floppy_read
    jc fail
    cld
%ifndef READ_ONLY
    mov byte [step], 5
    xor di, di
    movzx cx, byte [spt]
    shl cx, 8
.pattern:
    mov ax, di
    xor ah, [cylinder]
    xor al, [head]
    xor ah, [drive]
    stosw
    loop .pattern
    call chs
    xor bx, bx
    mov ah, 3
    int 0x13
    jc fail
    mov byte [step], 6
    call chs
    mov ah, 4
    int 0x13
    jc fail
    mov byte [step], 7
    xor di, di
    movzx cx, byte [spt]
    shl cx, 8
    xor ax, ax
    rep stosw
    call chs
    mov ah, 2
    int 0x13
    jc fail
    xor di, di
    movzx cx, byte [spt]
    shl cx, 8
.compare:
    mov ax, di
    xor ah, [cylinder]
    xor al, [head]
    xor ah, [drive]
    scasw
    jne fail
    loop .compare
%endif
.next:
    xor ax, ax
    mov es, ax
    inc byte [head]
    cmp byte [head], 2
    jb .head
    inc byte [cylinder]
    mov al, [cylinder]
    cmp al, [maximum]
    jbe .cylinder
    inc byte [drive]
    cmp byte [drive], 2
    jb .drive
%ifdef READ_ONLY
    mov al, 0x68
    jmp exit_emulator
%endif
    ; A/B state must remain independent after formatting B.
    mov byte [step], 8
    mov byte [drive], 0
.revisit:
    movzx si, byte [drive]
    movzx si, byte [media+si]
    shl si, 1
    mov cx, [geometry+si]
    mov [spt], cl
    mov [cylinder], ch
    mov byte [head], 1
    mov ax, 0x1000
    mov es, ax
    xor bx, bx
    call chs
    mov ah, 2
    int 0x13
    jc fail
    xor di, di
    mov ax, di
    xor ah, [cylinder]
    xor al, [head]
    xor ah, [drive]
    cmp [es:di], ax
    jne fail
    ; A two-sector request must split at the head boundary, not wrap R.
    mov byte [step], 10
    mov ch, 39
    mov cl, [spt]
    xor dh, dh
    mov dl, [drive]
    mov ax, 0x0202
    int 0x13
    jc fail
    movzx ax, byte [spt]
    dec ax
    shl ax, 9
    xor ah, 39
    xor ah, [drive]
    cmp [es:0], ax
    jne fail
    mov ax, 0x2701
    xor ah, [drive]
    cmp [es:512], ax
    jne fail
    ; Verify has no buffer: even an unusable far address must be ignored.
    ; With FIFO enabled it must also leave the DMA count untouched.
    mov byte [step], 11
    mov al, 6
    out 0x0A, al
    xor al, al
    out 0x0C, al
    mov al, 0x34
    out 0x05, al
    mov al, 0x12
    out 0x05, al
    push es
    mov ax, 0xFFFF
    mov es, ax
    mov bx, 0xFFFF
    mov ax, 0x0401
    mov cx, 0x2701
    xor dh, dh
    mov dl, [drive]
    int 0x13
    pop es
    jc fail
    xor al, al
    out 0x0C, al
    in al, 0x05
    cmp al, 0x34
    jne fail
    in al, 0x05
    cmp al, 0x12
    jne fail
    inc byte [drive]
    cmp byte [drive], 2
    jb .revisit
    mov byte [step], 9
    ; Physical DMA page overflow must fail before issuing a write.
    xor ax, ax
    mov es, ax
    mov bx, 0xFF00
    mov ax, 0x0301
    mov cx, 1
    xor dx, dx
    int 0x13
    jnc fail
    cmp ah, 9
    jne fail
    mov al, 0x68
    jmp exit_emulator
chs:
    mov ch, [cylinder]
    mov cl, 1
    mov dh, [head]
    mov dl, [drive]
    mov al, [spt]
    ret
checked_floppy_read:
    int 0x13                ; Complete real FDC/DMA service with DF1, IF0/IF1.
    pushf
    pop word [cs:read_flags]
    push ax
    mov ax, [cs:read_flags]
    and ax, 0x600
    cmp ax, 0x600
    pop ax
    jne fail
    test word [cs:read_flags], 1
    jnz .return
    cmp ah, 0
    jne fail
    cmp al, [cs:spt]
    jne fail
    push ax
    push cx
    push di
    cld
    xor di, di
    movzx cx, byte [cs:spt]
    shl cx, 8
    mov ax, 0xF6F6
    repe scasw               ; Check this read before the other side overwrites it.
    jne fail
    pop di
    pop cx
    pop ax
.return:
    push word [cs:read_flags]
    popf                    ; Retain the actual CF and documented AX result.
    ret
progress:
    pushad
    push es
    push fs
    xor ax, ax
    mov es, ax
    mov fs, [0x040E]
    xor si, si
.copy:
    mov al, [fs:0x80+si]
    mov [report+si], al
    inc si
    cmp si, 48
    jb .copy
    mov ax, 0x0301
    mov bx, report
    mov cx, 31
    mov dx, 0x0080
    int 0x13
    pop fs
    pop es
    popad
    ret
fail:
    ; Record call result and production state on the disposable HDD.
    mov [cs:failure_ax], ax
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov bx, report
    mov si, [0x040E]
    mov fs, si
    xor si, si
.copy:
    mov al, [fs:0x80+si]
    mov [bx+si], al
    inc si
    cmp si, 48
    jb .copy
    mov ax, 0x0301
    mov bx, report
    mov cx, 31
    mov dx, 0x0080
    int 0x13
    mov al, 0x69
exit_emulator:
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
    cli
    hlt
types: db TYPE_A,TYPE_B
post_packet: db 0x10,0
    dw 8,0,0xB800
    dq 32
media: db MEDIA_A,MEDIA_B
geometry: dw 0,0x2709,0x4F0F,0x4F09,0x4F12,0x4F24
ids: times 36*4 db 0
report: times 48 db 0
failure_ax: dw 0
read_flags: dw 0
step: db 0
drive: db 0
maximum: db 0
spt: db 0
cylinder: db 0
head: db 0
times 512-($-report) db 0
times 8192-($-$$) db 0
