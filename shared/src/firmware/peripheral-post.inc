; Existing POST-only peripheral detection/initialization owner.
    pushf
    cli
    pushad
    push ds
    push es
    push fs
    call ports_apply
    call load_bios_state
    xor ax, ax
    mov ds, ax
    mov es, ax
    set_vector 0x14, int14
    set_vector 0x17, int17
    mov di, 0x400
    mov cx, 7
    rep stosw                 ; Stops before the EBDA pointer040E.
    and word [0x410], 0x31FF ; Replace only COM/LPT equipment counts.
    mov dword [0x47C], 0x01010101
    mov word [0x478], 0x1414
    mov byte [0x47A], 20
    ; Six complete candidates live on the stack, never in reserved EBDA state.
    sub sp, 18
    mov bp, sp
    mov al, [fs:C_PORTS]
    call ports_uart_base
    mov [ss:bp], ax
    mov al, [fs:C_PORTS+1]
    call ports_uart_base
    mov [ss:bp+2], ax
    mov dword [ss:bp+4], 0x02F803F8
    mov dword [ss:bp+8], 0x02E803E8
    mov cx, 2
    cmp byte [fs:C_PORTS+7], 0
    je .serial_start
    mov cx, 6
.serial_start:
    xor si, si
    xor di, di
.serial:
    mov dx, [ss:bp+si]
    call .unique
    jc .serial_next
    call ports_uart_probe
    jc .serial_next
    call ports_uart_initialize
    cmp di, 8
    jae .serial_next         ; Every detected UART is initialized before this cap.
    mov [0x400+di], dx
    add di, 2
.serial_next:
    add si, 2
    loop .serial
    shl di, 8               ; Four entries => equipment count4 at bits9..11.
    or [0x410], di
    movzx bx, byte [fs:C_PORTS+3]
    shl bx, 1
%ifdef PNP_PRIVATE_PERIPHERALS
    call pnp_module_parallel_base
%else
    mov ax, [cs:ports_parallel+bx]
%endif
    mov [ss:bp], ax
    mov dword [ss:bp+2], 0x037803BC
    mov word [ss:bp+6], 0x278
    mov cx, 4
    xor si, si
    xor di, di
.printer:
    mov dx, [ss:bp+si]
    call .unique
    jc .printer_next
    call ports_printer_probe
    jc .printer_next
    mov [0x408+di], dx
    add di, 2
.printer_next:
    add si, 2
    loop .printer
    shr di, 1
    shl di, 14
    or [0x410], di
    add sp, 18
    pop fs
    pop es
    pop ds
    popad
    popf
    ret
.unique:
    push di
    test dx, dx
    jz .duplicate
    xor di, di
.previous:
    cmp di, si
    jae .new
    cmp dx, [ss:bp+di]
    je .duplicate
    add di, 2
    jmp .previous
.new:
    pop di
    clc
    ret
.duplicate:
    pop di
    stc
    ret

; Scratch and IER distinguish a decoded16450 from a floating bus; restore both.
ports_uart_probe:
    push ax
    push bx
    push dx
    add dx, 3
    in al, dx
    mov bh, al
    and al, 0x7F
    out dx, al
    sub dx, 2
    in al, dx
    mov bl, al
    xor al, al
    out dx, al
    in al, dx
    test al, al
    jnz .bad
    add dx, 6
    in al, dx
    mov ah, al
    mov al, 0x55
    out dx, al
    in al, dx
    cmp al, 0x55
    jne .scratch_bad
    mov al, 0xAA
    out dx, al
    in al, dx
    cmp al, 0xAA
    jne .scratch_bad
    clc
    jmp .scratch_restore
.scratch_bad:
    stc
.scratch_restore:
    mov al, ah
    out dx, al
    sub dx, 6
    jmp .restore
.bad:
    stc
.restore:
    pushf
    mov al, bl
    out dx, al
    add dx, 2
    mov al, bh
    out dx, al
    popf
    pop dx
    pop bx
    pop ax
    ret

ports_uart_initialize:
    push ax
    push dx
    mov ax, 12
    mov bl, 3
    call serial_initialize
    add dx, 4
    xor al, al              ; Quiet: neither modem lines nor UART IRQ asserted.
    out dx, al
    pop dx
    pop ax
    ret

ports_printer_probe:
    push ax
    push bx
    push dx
    add dx, 2
    in al, dx
    mov bh, al
    and al, 0xDF           ; Test output latch, temporarily leave input direction.
    out dx, al
    sub dx, 2
    in al, dx              ; Input-direction reads pins, not the saved latch.
    mov bl, al
    mov al, 0x55
    out dx, al
    in al, dx
    cmp al, 0x55
    jne .bad
    mov al, 0xAA
    out dx, al
    in al, dx
    cmp al, 0xAA
    jne .bad
    clc
    jmp .restore
.bad:
    stc
.restore:
    pushf
    mov al, bl
    out dx, al
    add dx, 2
    mov al, bh
    out dx, al
    popf
    pop dx
    pop bx
    pop ax
    ret
