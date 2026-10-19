; Runs before ATA identification on every keyboard-test cold/warm POST.
; Inject through the 8042, not the decoder. IRQ1 must suspend the interrupted
; caller before it returns; timer IRQs supply the tail and delayed resume key.
%define POST_TEST_TICKS 0x0640
%define POST_TEST_IRQS  0x0642
%define POST_TEST_FLAGS 0x0644
%define POST_TEST_STATE 0x0646

post_pause_test_begin:
    pushad
    push es
    xor ax, ax
    mov es, ax
    cli
    mov word [POST_TEST_IRQS], 0
    mov ax, [0x0417]
    mov [POST_TEST_FLAGS], ax
    mov al, [0x0400 + KB_POST_STATE]
    mov [POST_TEST_STATE], al
    set_vector 0x09, post_pause_test_irq
    mov byte [POST_TEST_TICKS], 0
    set_vector 0x1C, post_pause_test_tick
    ; First E1 arrives with IF clear. The interrupted POST instruction
    ; stream must stop immediately when IRQ1 runs, without a boundary wait.
    mov al, 0xD2
    call kbc_command
    jc post_pause_test_failed
    mov al, 0xE1
    call kbc_write_data
    jc post_pause_test_failed
    call kbc_wait_output_full
    jc post_pause_test_failed
    sti
    nop                       ; IRQ1 must stop us here, before any POST wait.
    pop es
    popad
    ret

post_pause_test_end:
    pushad
    push es
    mov bl, 0x72
    cmp byte [POST_TEST_TICKS], 8
    jb post_pause_test_failed
    mov bl, 0x73
    mov al, [0x0400 + KB_POST_STATE]
    cmp al, [POST_TEST_STATE]
    jne post_pause_test_failed
    mov bl, 0x74
    mov ax, [0x041A]
    cmp ax, [0x041C]
    jne post_pause_test_failed
    mov bl, 0x75
    mov ax, [0x0417]
    cmp ax, [POST_TEST_FLAGS]
    jne post_pause_test_failed
    xor ax, ax
    mov es, ax
    set_vector 0x1C, default_iret
    sti
    mov bl, 0x76
    ; A fresh function key remains available for future setup entry.
    mov al, 0x3B
    call post_pause_test_scan
    mov ah, 1
    int 0x16
    jz post_pause_test_failed
    cmp ax, 0x3B00
    jne post_pause_test_failed
    xor ah, ah
    int 0x16
    cli
    set_vector 0x09, int09
    sti
    pop es
    popad
    ret

post_pause_test_tick:
    push ax
    push bx
    push ds
    xor ax, ax
    mov ds, ax
    mov bl, 0x77
    ; Start the tail/resume countdown only after IRQ1 has entered Pause.
    cmp byte [POST_TEST_TICKS], 0
    jne .started
    cmp byte [0x0400 + KB_PAUSED], 1
    jne .done
.started:
    ; D2 injection must not contend with a real LED reply or occupied buffer.
    cmp byte [0x0400 + KB_LED_PHASE], 2
    je .done
    cmp byte [0x0400 + KB_LED_PHASE], 4
    je .done
    in al, KBC_STATUS
    test al, 3
    jnz .done
    inc byte [POST_TEST_TICKS]
    cmp byte [POST_TEST_TICKS], 8
    ja .done
    cmp byte [0x0400 + KB_PAUSED], 1
    jne post_pause_test_failed
    mov al, 0xD2
    call kbc_command
    jc post_pause_test_failed
    mov al, [POST_TEST_TICKS]
    cmp al, 5
    ja .resume_event
    xor ah, ah
    mov bx, ax
    mov al, [cs:post_pause_test_scans+bx]
    jmp .send
.resume_event:
    mov al, 0x9E             ; Release cannot resume.
    cmp byte [POST_TEST_TICKS], 6
    je .send
    mov al, 0xFA             ; ACK cannot resume.
    cmp byte [POST_TEST_TICKS], 7
    je .send
    mov al, 0x1E             ; A make resumes, but is consumed.
.send:
    call kbc_write_data
    jc post_pause_test_failed
.done:
    pop ds
    pop bx
    pop ax
    iret

post_pause_test_scan:
    push bx
    mov bx, [POST_TEST_IRQS]
    push ax
    mov al, 0xD2
    call kbc_command
    pop ax
    jc .failed
    call kbc_write_data
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    push cx
    mov cx, 0xFFFF
.consumed:
    sti
    nop
    cmp bx, [POST_TEST_IRQS]
    jne .done
    loop .consumed
.failed:
    mov bl, 0x70
    jmp post_pause_test_failed
.done:
    pop cx
    pop bx
    ret

post_pause_test_irq:
    pushf
    call 0xF000:int09
    push ax
    push ds
    xor ax, ax
    mov ds, ax
    inc word [POST_TEST_IRQS]
    pop ds
    pop ax
    iret

post_pause_test_failed:
    mov al, bl
    call emulator_exit
    jmp hard_halt

post_pause_test_scans:
    db 0xE1, 0x1D, 0x45, 0xE1, 0x9D, 0xC5
