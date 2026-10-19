bits 16
org 0x100
start:
    push cs
    pop ds
    push cs
    pop es
    mov byte [step], 1
    cmp byte [0x80], 0
    jne driver_test
    mov ax, 0x351C
    int 0x21
    mov [old_tick], bx
    mov [old_tick+2], es
    mov ax, 0x251C
    mov dx, tick_hook
    int 0x21
    call ticks
    push ds
    lds dx, [old_tick]
    mov ax, 0x251C
    int 0x21
    pop ds
    push ds
    pop es
    cmp word [tick_calls], 0
    je fail
    mov byte [step], 2
    mov ax, 0xC205
    mov bh, 3
    mov [init_bx], bx
    int 0x15
%ifdef NO_MOUSE
    jnc fail
    mov byte [step], 3
    cmp ah, 3
    je .absent
    cmp ah, 4                     ; Controller may return resend for no device.
    jne fail
.absent:
    mov byte [step], 4
    call keyboard_check
    jmp passed
%else
    jc fail
    cmp bx, [init_bx]              ; OEM C205 preserves packet length/input BX.
    jne fail
    in al, 0xA1
    test al, 0x10                 ; Initialization leaves IRQ12 ready.
    jnz fail
    mov ax, 0xC201
    int 0x15
    jc fail
    cmp bx, 0x00AA                ; C201 returns reset result and device ID.
    jne fail
    in al, 0xA1
    test al, 0x10
    jnz fail
    inc byte [step]
    mov ax, 0xC200
    mov bh, 1
    int 0x15
    jnc fail
    cmp ah, 5
    jne fail
    mov ax, 0xC207
    mov bx, callback
    int 0x15
    jc fail
    mov ax, 0xC203
    mov bh, 2
    int 0x15
    jc fail
    mov ax, 0xC202
    mov bh, 4
    int 0x15
    jc fail
    mov ax, 0xC206
    xor bh, bh
    int 0x15
    jc fail
    cmp cl, 2
    jne fail
    cmp dl, 80
    jne fail
    inc byte [step]
    mov ax, 0xC200
    mov bh, 1
    int 0x15
    jc fail
    mov si, packet
    call inject_packet
    cmp word [calls], 1
    jne fail
    cmp word [args], 0
    jne fail
    cmp word [args+2], 0xFE
    jne fail
    cmp word [args+4], 5
    jne fail
    cmp word [args+6], 0x29
    jne fail
    inc byte [step]
    call keyboard_check
    mov si, packet
    call inject_packet
    cmp word [calls], 2
    jne fail
    mov byte [step], 0x14
    mov ax, 0xC201
    int 0x15
    jc fail
    ; A driver may restart reporting directly after reset. Registered IRQ12
    ; callbacks must accept packets without another BIOS C200 enable call.
    mov si, packet
    call inject_packet
    mov byte [step], 0x15
    cmp word [calls], 3
    jne fail
    mov ax, 0xC200
    xor bh, bh
    int 0x15
    jc fail
    in al, 0xA1
    test al, 0x10                 ; Stopping F4 streaming must retain readiness.
    jnz fail
    xor bx, bx
    mov es, bx
    mov ax, 0xC207
    int 0x15
    jc fail
    in al, 0xA1
    test al, 0x10
    jnz fail
    mov ax, 0x4C00
    int 0x21
%endif
driver_test:
    mov byte [step], 5
    mov ax, 0x4300
    int 0x2F
    cmp al, 0x80
    jne fail
    smsw ax
    test al, 1
    jz fail
    xor ax, ax
    int 0x33
    cmp ax, 0xFFFF
    jne fail
    mov ax, 4
    mov cx, 320
    mov dx, 100
    int 0x33
    mov ax, 3
    int 0x33
    mov [position], cx
    mov [position+2], dx
    mov si, motion
    call inject_packet
    mov ax, 3
    int 0x33
    test bx, 1
    jz fail
    cmp cx, [position]
    jbe fail
    cmp dx, [position+2]
    jae fail
    inc byte [step]
    call keyboard_check
passed:
    mov al, 0x69
    jmp exit_vm
fail:
    mov [cs:failure_ax], ax
    pushf
    pop word [cs:failure_flags]
    push cs
    pop ds
    xor cx, cx
    mov dx, failure_name
    mov ah, 0x3C
    int 0x21
    jc .exit
    mov bx, ax
    mov dx, failure_ax
    mov cx, 4
    mov ah, 0x40
    int 0x21
    mov ah, 0x3E
    int 0x21
.exit:
    mov al, [cs:step]
    add al, 0x60                  ; Keep diagnostic codes below 86Box's 7F cap.
exit_vm:
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

callback:
    push bp
    mov bp, sp
    push ax
    mov ax, [ss:bp+6]
    mov [cs:args], ax
    mov ax, [ss:bp+8]
    mov [cs:args+2], ax
    mov ax, [ss:bp+10]
    mov [cs:args+4], ax
    mov ax, [ss:bp+12]
    mov [cs:args+6], ax
    inc word [cs:calls]
    pop ax
    pop bp
    retf

init_bx: dw 0

tick_hook:
    inc word [cs:tick_calls]
    jmp far [cs:old_tick]

inject_packet:
    mov cx, 3
.byte:
    lodsb
    push cx
    mov bl, al
    mov al, 0xD3
    call inject
    call ticks
    pop cx
    loop .byte
    ret

keyboard_check:
    mov byte [step], 0x10
    push es
    mov ax, 0x40
    mov es, ax
    cmp word [es:0x80], 0x1E
    jne fail
    cmp word [es:0x82], 0x3E
    jne fail
    mov byte [step], 0x11
    test byte [es:0x96], 0x10
    jz fail
    pop es
    mov byte [step], 0x12
    mov ax, 0x0900
    int 0x16
    cmp al, 0x20
    jne fail
    mov ax, 0xC137
    int 0x15
    jc fail
    cmp ax, 0xC137
    jne fail
    push ds
    mov bx, 0x40
    mov ds, bx
    mov bx, es
    cmp bx, [0x0E]
    pop ds
    jne fail
    mov byte [step], 0x13
    mov bl, 0x1E
    mov al, 0xD2
    call inject
    call ticks
    mov ah, 1
    int 0x16
    jz fail
    xor ah, ah
    int 0x16
    cmp ax, 0x1E61
    jne fail
    ret

inject:
    push ax
    call ready
    pop ax
    out 0x64, al
    call ready
    mov al, bl
    out 0x60, al
    sti
    ret
ready:
    push cx
    mov cx, 0xFFFF
.wait:
    in al, 0x64
    test al, 2
    jz .done
    loop .wait
    jmp fail
.done:
    pop cx
    ret
ticks:
    push ax
    push es
    mov ax, 0x40
    mov es, ax
    mov ax, [es:0x6C]
    add ax, 2
.wait:
    sti
    hlt
    cmp [es:0x6C], ax
    jne .wait
    pop es
    pop ax
    ret
step: db 0
failure_ax: dw 0
failure_flags: dw 0
failure_name: db 'MFAIL.BIN', 0
calls: dw 0
args: times 4 dw 0
position: dd 0
old_tick: dd 0
tick_calls: dw 0
packet: db 0x29,5,0xFE
motion: db 0x09,16,8
