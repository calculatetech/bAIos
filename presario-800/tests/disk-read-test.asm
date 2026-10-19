; Read-only physical-disk benchmark. No filesystem cache, no disk writes.
; Assemble normally for DOS; EMULATOR_TEST writes a log only on a disposable VHD.
bits 16
org 0x100

start:
    cld
    push cs
    pop ds
    push cs
    pop es
    ; Presario-only snapshot. Do not change clock, timing or DMA settings.
    pushf
    cli
    out 0xFB, al
    mov bl, 5
    mov di, bus_registers
.register:
    mov al, bl
    out 0xEC, al
    in al, 0xED
    call hex_byte
    inc bl
    cmp bl, 10
    jb .register
    out 0xF9, al
    mov al, 0x0F
    out 0x70, al
    in al, 0x71
    mov di, shutdown_code
    call hex_byte
    popf
    mov dx, progress
    mov ah, 9
    int 0x21
    mov ah, 8
    mov dl, 0x80
    int 0x13
    jc failed
    and cl, 63
    cmp cl, 16
    jb failed                  ; Both shapes stay within the detected first track.
    push cs
    pop es
    mov bx, reference
    mov ax, 0x0210
    mov cx, 1
    mov dx, 0x0080
    int 0x13
    jc failed

    mov byte [request_size], 1
    mov di, one_seconds
    call measure
    mov byte [request_size], 16
    mov di, bulk_seconds
    call measure
    mov dx, message
    mov ah, 9
    int 0x21
%ifdef EMULATOR_TEST
    mov dx, log_name
    xor cx, cx
    mov ah, 0x3C
    int 0x21
    jc failed
    mov bx, ax
    mov dx, message
    mov cx, message_end - message
    mov ah, 0x40
    int 0x21
    jc failed
    mov ah, 0x3E
    int 0x21
    jc failed
    mov al, 0x67
    jmp emulator_exit
%else
    mov ax, 0x4C00
    int 0x21
%endif

measure:
    push di
    mov di, buffer
    mov ax, 0xDEAD
    mov cx, 4096
    rep stosw
    call rtc_seconds
    mov [started], ax
    mov bp, 1024               ; 1024 * 16 sectors = 8 MiB, each shape.
.block:
    mov bx, buffer
    mov cx, 1
.request:
    mov ah, 2
    mov al, [request_size]
    mov dx, 0x0080
    push bx
    push cx
    push bp
    int 0x13
    pop bp
    pop cx
    pop bx
    jc failed
    xor ax, ax
    mov al, [request_size]
    add cl, al
    shl ax, 9
    add bx, ax
    cmp cl, 17
    jb .request
    dec bp
    jnz .block
    call rtc_seconds
    sub ax, [started]
    jnc .elapsed
    add ax, 3600               ; Minute counter wraps each hour.
.elapsed:
    pop di
    call decimal
    mov si, reference
    mov di, buffer
    mov cx, 4096
    repe cmpsw
    jne failed
    ret

; Use RTC seconds, not IRQ0 ticks: a long BIOS call can defer timer IRQs.
; Return 0..3599; read a stable minute/second pair, honoring binary/BCD mode.
rtc_seconds:
    push bx
    push cx
    push dx
    pushf
    cli
.retry:
    mov al, 0x0A
    out 0x70, al
    in al, 0x71
    test al, 0x80
    jnz .retry
    mov al, 0x0B
    out 0x70, al
    in al, 0x71
    mov dl, al
    xor al, al
    out 0x70, al
    in al, 0x71
    mov bl, al
    mov al, 2
    out 0x70, al
    in al, 0x71
    mov bh, al
    xor al, al
    out 0x70, al
    in al, 0x71
    cmp al, bl
    jne .retry
    mov al, 0x0A
    out 0x70, al
    in al, 0x71
    test al, 0x80
    jnz .retry
    mov al, bh
    call .convert
    imul ax, 60
    mov cx, ax
    mov al, bl
    call .convert
    add ax, cx
    popf
    pop dx
    pop cx
    pop bx
    ret
.convert:
    xor ah, ah
    test dl, 4
    jnz .converted
    mov ah, al
    and al, 15
    shr ah, 4
    aad
.converted:
    ret

hex_byte:
    mov ah, al
    shr al, 4
    call .digit
    mov al, ah
    and al, 15
    call .digit
    mov al, ' '
    stosb
    ret
.digit:
    add al, '0'
    cmp al, '9'
    jbe .store
    add al, 7
.store:
    stosb
    ret

decimal:
    add di, 4
    mov bx, 10
    mov cx, 5
.digit:
    xor dx, dx
    div bx
    add dl, '0'
    mov [di], dl
    dec di
    loop .digit
    ret

failed:
    mov dx, failure
    mov ah, 9
    int 0x21
%ifdef EMULATOR_TEST
    mov al, 0x68
emulator_exit:
    mov bl, al
    mov si, signature
    mov dx, 0x80
    mov cx, 7
.unlock:
    lodsb
    out dx, al
    loop .unlock
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
%endif
    mov ax, 0x4C01
    int 0x21

request_size db 0
started dw 0
progress db 'Presario disk read test running; no sectors will be written.',13,10,'$'
message db 'Read-only BIOS test, 8 MiB per shape; RTC seconds (1-second resolution).',13,10
    db 'Chipset 05 06 07 08 09: '
bus_registers db '00 00 00 00 00 ',13,10
    db 'CMOS shutdown 0F: '
shutdown_code db '00 ',13,10
    db '1 sector/request: '
one_seconds db '00000',13,10
    db '16 sectors/request: '
bulk_seconds db '00000',13,10
    db 'Final buffers match.',13,10
message_end:
    db '$'
failure db 'Disk benchmark failed: read, geometry, or data mismatch.',13,10,'$'
%ifdef EMULATOR_TEST
log_name db 'DISKREAD.TXT',0
signature db '86Box',1,5
%endif
reference times 8192 db 0
buffer times 8192 db 0
