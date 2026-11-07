halt_forever:
    cli
    xor dx, dx
    mov ds, dx
    call load_bios_state
    mov byte [0x0400 + KB_POST_STATE], 2
%ifdef EMULATOR_TEST
%ifndef EMULATOR_BOOT_POLICY_TEST
    call verify_terminal_diagnostic
    jnc .diagnostic_ok
    mov al, 0x77
    call emulator_exit
.diagnostic_ok:
    push ax
    xor ax, ax
    mov es, ax
    mov word [es:0x046C], 0
    mov word [es:0x046E], 0
%endif
%endif
.halt:
    call post_keyboard_wait
.idle:
    sti
    hlt
    cli
%ifdef EMULATOR_TEST
%ifndef EMULATOR_BOOT_POLICY_TEST
%ifndef EMULATOR_PORTS_TEST
    cmp word [es:0x046C], 0
    jne .timer_woke_halt
    mov al, 0x78
    call emulator_exit
.timer_woke_halt:
    pop ax
    call emulator_exit
%endif
%endif
%endif
    jmp .halt

hard_halt:
    cli
.halt:
    hlt
    jmp .halt

%ifdef EMULATOR_TEST
verify_terminal_diagnostic:
    push ax
    push cx
    push dx
    push si
    push di
    push es
    mov dl, al
    cmp dl, 0x63
    jne .boot_error
    mov si, msg_no_disk
    jmp .scan
.boot_error:
    mov si, msg_boot_error
.scan:
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov cx, 2000
.next_cell:
    push cx
    push si
    push di
.compare:
    cs lodsb
    cmp al, 32
    jb .found
    cmp al, [es:di]
    jne .not_here
    add di, 2
    jmp .compare
.not_here:
    pop di
    pop si
    pop cx
    add di, 2
    loop .next_cell
    stc
    jmp .done
.found:
    add sp, 6
    clc
.done:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop ax
    ret

%endif
