; Shared decoded-port POST/INT14/INT17 policy; board owns device routing.
ports_defaults:
    pushad
    mov si, ports_default
    mov cx, 8
.byte:
    mov al, [cs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    popad
%ifdef BOARD_PORTS_DEFAULT_FILTER
    call BOARD_PORTS_DEFAULT_FILTER
%endif
    ret

ports_valid:
    pushad
    xor bx, bx
.enum:
    mov al, [fs:si+bx]
    cmp al, [cs:ports_limits+bx]
    ja .bad
    inc bx
    cmp bx, 8
    jb .enum
    call ports_record_valid
    jc .bad
    mov al, [fs:si]
    test al, al
    jz .good
    cmp al, [fs:si+1]
    je .bad
.good:
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

ports_settings_load:
    pushad
    mov di, C_PORTS
    call ports_defaults
    mov al, 0x5D
    call rtc_read
    cmp al, 'P'
    jne .done
    mov bl, al
    mov al, 0x5E
    call rtc_read
    cmp al, '1'
    jne .bad
    add bl, al
    mov al, 0x5F
    call rtc_read
    cmp al, 1
    jne .bad
    add bl, al
    mov dl, 0x60
    mov cx, 8
.read:
    mov al, dl
    call rtc_read
    mov [fs:di], al
    add bl, al
    inc di
    inc dl
    loop .read
    mov al, 0x68
    call rtc_read
    add bl, al
    jnz .bad
    mov si, C_PORTS
    call ports_valid
    jnc .done
.bad:
    mov di, C_PORTS
    call ports_defaults
    mov byte [fs:C_VALID], 0
.done:
    ; One board connector: UART B must not claim the ISA modem's COM2.
%ifndef BOARD_PORTS_PAIRS
    mov byte [fs:C_PORTS+2], 1  ; Only standard 3E8h/2E8h addresses are exposed.
%endif
    mov byte [fs:C_PORTS+7], 1
%ifdef BOARD_PORTS_LOAD_FILTER
    call BOARD_PORTS_LOAD_FILTER
%endif
    popad
    ret

ports_settings_save:
    pushad
%ifdef BOARD_PORTS_SAVE_FILTER
    call BOARD_PORTS_SAVE_FILTER
%endif
%ifndef BOARD_PORTS_PAIRS
    mov byte [fs:U_PORTS+2], 1
%endif
    mov byte [fs:U_PORTS+7], 1
    mov si, U_PORTS
    call ports_valid
    jc .bad
    mov ax, 0x005D
    call rtc_write
    mov bl, 'P'+'1'+1
    mov dl, 0x60
    mov cx, 8
.write:
    mov ah, [fs:si]
    add bl, ah
    mov al, dl
    call rtc_write
    inc si
    inc dl
    loop .write
    neg bl
    mov ah, bl
    mov al, 0x68
    call rtc_write
    mov ax, 0x015F
    call rtc_write
    mov ax, ('1' << 8)|0x5E
    call rtc_write
    mov ax, ('P' << 8)|0x5D
    call rtc_write
    mov ax, ('P' << 8)|0x5D
    call settings_verify_byte
    jne .bad
    mov ax, ('1' << 8)|0x5E
    call settings_verify_byte
    jne .bad
    mov ax, 0x015F
    call settings_verify_byte
    jne .bad
    mov al, 0x68
    mov ah, bl
    call settings_verify_byte
    jne .bad
    mov si, U_PORTS
    mov dl, 0x60
    mov cx, 8
.verify:
    mov ah, [fs:si]
    mov al, dl
    call settings_verify_byte
    jne .bad
    inc dl
    inc si
    loop .verify
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

; AL=logical onboard selection0..4; AX=base (zero for Disabled).
ports_uart_base:
    push bx
    movzx bx, al
    shl bx, 1
    mov ax, [cs:ports_fixed+bx]
    cmp bx, 6
    jb .done
    sub bx, 6
    push dx
    movzx dx, byte [fs:C_PORTS+2]
    shl dx, 2
    add bx, dx
    mov ax, [cs:ports_pairs+bx]
    pop dx
.done:
    pop bx
    ret

init_peripherals:
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
    mov ax, [cs:ports_parallel+bx]
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

; AX=divisor, BL=LCR. DX always returns to base; clears IER and DLAB.
serial_initialize:
    push ax
    add dx, 3
    mov al, 0x80
    out dx, al
    sub dx, 3
    pop ax
    out dx, al
    inc dx
    mov al, ah
    out dx, al
    add dx, 2
    mov al, bl
    out dx, al
    sub dx, 2
    xor al, al
    out dx, al
    dec dx
    ret

; DX=status register, BL=required bits, BH=timeout seconds. No IRQ dependence.
ports_wait:
    pushf
    push cx
    push esi
    sti                    ; IRQ0/keyboard must run during a device timeout.
    movzx esi, bh
    imul esi, 500
.sample:
    in al, dx
    mov cl, al
    and cl, bl
    cmp cl, bl
    je .ready
    test esi, esi
    jz .timeout
    call kbc_delay_2ms
    dec esi
    jmp .sample
.timeout:
    pop esi
    pop cx
    popf
    stc
    ret
.ready:
    pop esi
    pop cx
    popf
    clc
    ret

int14:
    push bp
    mov bp, sp
    pushad
    push ds
    cmp ah, 5
    ja .return              ; Unsupported preserves AX, including invalid DX.
    cmp dx, 3
    ja .absent
    mov si, dx
    push ax
    xor ax, ax
    mov ds, ax
    movzx di, byte [0x47C+si]
    pop ax
    shl si, 1
    mov dx, [0x400+si]
    test dx, dx
    jz .absent
    cmp ah, 0
    je .initialize
    cmp ah, 1
    je .send
    cmp ah, 2
    je .receive
    cmp ah, 3
    je .status
    cmp ah, 4
    je .extended
    cmp al, 1
    ja .return
    add dx, 4
    test al, al
    jz .modem_read
    mov al, [ss:bp-16]
    and al, 0x1F
    out dx, al
    jmp .modem_status
.modem_read:
    in al, dx
    mov [ss:bp-16], al      ; Documented function05 AL0 output BL=MCR.
.modem_status:
    sub dx, 4
    jmp .status
.initialize:
    mov bl, al
    and bl, 0x1F
    movzx si, al
    shr si, 5
    shl si, 1
    mov ax, [cs:serial_divisors+si]
    call serial_initialize
    jmp .status
.extended:
    cmp al, 1
    ja .return
    cmp bh, 5
    ja .return
    cmp bl, 1
    ja .return
    cmp ch, 3
    ja .return
    cmp cl, 10
    ja .return
    shl al, 6
    shl bl, 2
    or al, bl
    or al, ch
    movzx si, bh
    or al, [cs:serial_parity+si]
    mov bl, al
    movzx si, cl
    shl si, 1
    mov ax, [cs:serial_divisors+si]
    call serial_initialize
    jmp .status
.send:
    mov bx, di
    mov bh, bl
    add dx, 4
    mov al, 3
    out dx, al              ; Traditional BIOS TX asserts DTR/RTS, never OUT2.
    add dx, 2
    mov bl, 0x30            ; DSR and CTS.
    call ports_wait
    jc .timed_out
    dec dx
    mov bl, 0x20
    call ports_wait
    jc .timed_out
    mov ah, al
    sub dx, 5
    mov al, [ss:bp-4]
    out dx, al
    jmp .result
.receive:
    mov bx, di
    mov bh, bl
    add dx, 4
    mov al, 1
    out dx, al
    add dx, 2
    mov bl, 0x20            ; DSR.
    call ports_wait
    jc .timed_out
    dec dx
    mov bl, 1
    call ports_wait
    jc .timed_out
    mov ah, al
    and ah, 0x1E
    sub dx, 5
    in al, dx
    jmp .result
.timed_out:
    mov ax, [ss:bp-4]
    mov ah, 0x80
    jmp .result
.status:
    add dx, 5
    in al, dx
    mov ah, al
    inc dx
    in al, dx
    jmp .result
.absent:
    mov ax, [ss:bp-4]
    mov ah, 0x80
.result:
    mov [ss:bp-4], ax
.return:
    pop ds
    popad
    pop bp
    iret

int17:
    push bp
    mov bp, sp
    pushad
    push ds
    cmp ah, 2
    ja .return
    cmp dx, 2
    ja .absent
    mov si, dx
    xor bx, bx
    mov ds, bx
    mov bh, [0x478+si]
    shl si, 1
    mov dx, [0x408+si]
    test dx, dx
    jz .absent
    test ah, ah
    jz .send
    cmp ah, 1
    jne .status
    add dx, 2
    in al, dx
    mov bl, al
    or al, 8               ; Assert inverted SLCTIN while INIT is low.
    and al, 0xFB
    out dx, al
    call kbc_delay_2ms
    mov al, bl
    or al, 0x0C
    out dx, al
    dec dx
    jmp .read_status
.send:
    inc dx
    mov bl, 0x80
    call ports_wait
    jc .timeout
    inc dx
    in al, dx
    mov bl, al
    and al, 0xDE           ; Present data in output mode with STROBE idle.
    out dx, al
    sub dx, 2
    mov al, [ss:bp-4]
    out dx, al
    add dx, 2
    mov al, bl
    and al, 0xDF
    or al, 1
    out dx, al
    call kbc_delay_2ms
    mov al, bl
    and al, 0xFE
    out dx, al
    dec dx
    jmp .read_status
.status:
    inc dx
.read_status:
    in al, dx
    and al, 0xF8
    xor al, 0x48
    jmp .result
.timeout:
    and al, 0xF8
    xor al, 0x48
    or al, 1
    jmp .result
.absent:
    mov al, 1
.result:
    mov [ss:bp-3], al
.return:
    pop ds
    popad
    pop bp
    iret

ports_fixed dw 0,0x3F8,0x2F8
%ifdef BOARD_PORTS_PAIRS
ports_pairs dw BOARD_PORTS_PAIRS
%else
ports_pairs dw 0x338,0x238,0x3E8,0x2E8,0x2E8,0x2E0,0x220,0x228
%endif
ports_parallel dw 0,0x3BC,0x378,0x278
serial_divisors dw 1047,768,384,192,96,48,24,12,6,3,2
serial_parity db 0,8,0x18,0x28,0x38,0x3C

ports_report:
    pushad
    push ds
    xor ax, ax
    mov ds, ax
    mov si, ports_com_title
    call print_string
    mov di, 0x400
    mov cx, 4
    call .table
    mov si, ports_lpt_title
    call print_string
    mov di, 0x408
    mov cx, 3
    call .table
    mov si, ports_policy_title
    call print_string
    mov di, C_PORTS
    mov cx, 8
.policy:
    movzx ax, byte [fs:di]
    call .hex
    inc di
    loop .policy
    mov si, ports_line_end
    call print_string
    pop ds
    popad
    ret
.table:
    mov ax, [di]
    call .hex
    add di, 2
    loop .table
    ret
.hex:
    pushad
    mov cx, 4
    mov bx, 7
.digit:
    rol ax, 4
    push ax
    and al, 15
    add al, '0'
    cmp al, '9'
    jbe .character
    add al, 7
.character:
    mov ah, 0x0E
    int 0x10
    pop ax
    loop .digit
    mov ax, 0x0E20
    int 0x10
    popad
    ret
ports_com_title db 'Serial bases: ',0
ports_lpt_title db 13,10,'Printer bases: ',0
ports_policy_title db 13,10,'Devices A/B/Pair/LPT/Mode/FDC/Mouse/ISA: ',0
ports_line_end db 13,10,0
