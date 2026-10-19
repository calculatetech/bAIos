kbc_wait_input_clear:
    push cx
    mov cx, 100
.wait:
    in al, KBC_STATUS
    test al, 0x02
    jz .ready
    call kbc_delay_2ms
    loop .wait
    stc
    jmp .done
.ready:
    clc
.done:
    pop cx
    ret

; F000:87F8 in the repaired MR BIOS.  Its target-compatible output-port
; transaction uses a full 16-bit tight poll after each write.
kbc_wait_input_clear_mr:
    push cx
    xor cx, cx
.wait:
    in al, KBC_STATUS
    test al, 0x02
    loopne .wait
    jnz .timeout
    clc
    pop cx
    ret
.timeout:
    stc
    pop cx
    ret

kbc_wait_output_full:
    push cx
    mov cx, 100
.wait:
    in al, KBC_STATUS
    test al, 0x01
    jnz .ready
    call kbc_delay_2ms
    loop .wait
    stc
    jmp .done
.ready:
    clc
.done:
    pop cx
    ret

; Match the OEM wait primitive: one delay is about two milliseconds, measured
; against PIT channel 0 so it remains stable across CPU clock rates.
kbc_delay_2ms:
    push ax
    push bx
    push cx
    push dx
    mov dx, 0x0950
    pushf
    cli
    xor al, al
    out 0x43, al
    in al, 0x40
    mov ah, al
    in al, 0x40
    popf
    xchg al, ah
    mov bx, ax
.wait:
    pushf
    cli
    xor al, al
    out 0x43, al
    in al, 0x40
    mov ah, al
    in al, 0x40
    popf
    xchg al, ah
    mov cx, bx
    sub bx, ax
    jb .wrapped
    sub dx, bx
    jmp .sampled
.wrapped:
    sub dx, cx
.sampled:
    mov bx, ax
    jae .wait
    pop dx
    pop cx
    pop bx
    pop ax
    ret

kbc_command:
    push ax
    call kbc_wait_input_clear
    pop ax
    jc .done
    out KBC_COMMAND, al
.done:
    ret

kbc_write_data:
    push ax
    call kbc_wait_input_clear
    pop ax
    jc .done
    out KBC_DATA, al
.done:
    ret

kbc_read_data:
    call kbc_wait_output_full
    jc .done
    in al, KBC_DATA
.done:
    ret

kbc_drain:
    push ecx
    mov ecx, 0x00010000
.next:
    in al, KBC_STATUS
    test al, 0x01
    jz .empty
    in al, KBC_DATA
    dec ecx
    jnz .next
    stc
    jmp .done
.empty:
    clc
.done:
    pop ecx
    ret

arm_keyboard_runtime:
    mov al, 0xAD
    call kbc_command
    jc .failed
    call kbc_drain
    jc .failed
    mov al, 0x20
    call kbc_command
    jc .failed
    call kbc_read_data
    jc .failed
    or al, 0x41
    and al, 0xCF
    mov bl, al
    mov al, 0x60
    call kbc_command
    jc .failed
    mov al, bl
    call kbc_write_data
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    mov al, 0xAE
    call kbc_command
    jc .failed
    call kbc_wait_input_clear
    ret
.failed:
    stc
    ret

init_keyboard:
    ; Polling owns every controller response until runtime is armed.
    cli
    mov byte [0x0400 + KB_ABSENT], 0
    ; Match the OEM precondition sequence at F000:0319 and F000:F515.
    ; Let keyboard power-on finish before touching either 8042 interface.
    post_code 0xB4
    mov cx, 1000
.power_on_settle:
    in al, KBC_DATA
    call kbc_delay_2ms
    loop .power_on_settle

    mov al, 0xAD
    call kbc_command
    jc .pre_b4_failed
    call kbc_wait_input_clear
    jc .pre_b4_failed
    post_code 0xB5
    mov al, 0xA7
    call kbc_command
    jc .pre_b5_failed
    call kbc_wait_input_clear
    jc .pre_b5_failed
    post_code 0xB6
    call kbc_drain
    jc .pre_b6_failed

    post_code 0xC0
    mov al, 0xAD
    call kbc_command
    jc .input_failed
    call kbc_drain
    jc .input_failed
    post_code 0xC1

    mov al, 0xAA
    call kbc_command
    jc .self_test_timeout
    call kbc_read_data
    jc .self_test_timeout
    cmp al, 0x55
    jne .self_test_bad
    post_code 0xC2

    ; The repaired MR BIOS target path at F000:A420 performs this only after
    ; controller self-test.  It uses CFh, not the ProLinea OEM DFh/FFh path.
    post_code 0xB7
    mov al, 0xD1
    out KBC_COMMAND, al
    call kbc_wait_input_clear_mr
    jc .pre_b7_failed
    post_code 0xB8
    mov al, KBC_OUTPUT_PORT_VALUE
    out KBC_DATA, al
    call kbc_wait_input_clear_mr
    jc .pre_b8_failed
    post_code 0xBA

    mov al, 0x60
    call kbc_command
    jc .command_failed
    ; MR BIOS F000:88A0 chooses 5Ch for an AT controller, 7Ch for PS/2.
    ; Bit 5 means XT protocol on AT, not mouse-disable. Keep IRQ1 off here.
    mov al, KBC_INITIAL_COMMAND_BYTE
    call kbc_write_data
    jc .command_failed
    call kbc_wait_input_clear
    jc .command_failed
    post_code 0xC3
    ; Give the released keyboard clock ten bounded response windows. Consume
    ; anything left in the buffer before programming the physical keyboard.
    mov al, 0xAE
    call kbc_command
    jc .command_failed
    call kbc_wait_input_clear
    jc .command_failed
    mov cx, 10
.settle_keyboard:
    call kbc_read_data
    loop .settle_keyboard
    post_code 0xC4

    ; Match the OEM keyboard transaction at F000:E134. Reset is attempted
    ; twice. Each attempt requires FAh, then waits up to fifty OEM response
    ; windows for the mandatory AAh basic-assurance result.
    mov bl, 2
.reset_keyboard:
    post_code 0xC5
    mov al, 0xFF
    call kbc_write_data
    jc .reset_write_failed
    mov cx, 12
.wait_reset_ack:
    call kbc_read_data
    jnc .reset_reply
    loop .wait_reset_ack
    ; A silent device is recoverable only after all controller checks passed.
    mov byte [0x0400 + KB_ABSENT], 1
    post_code 0xD3
    ret
.reset_reply:
    cmp al, 0xFA
    je .wait_bat
    cmp al, 0xFE
    je .reset_resend
    post_code 0xD1
    loop .wait_reset_ack
    mov al, 0xD3
    jmp keyboard_halt
.wait_bat:
    post_code 0xC6
    mov cx, 50
.wait_bat_response:
    call kbc_read_data
    jnc .bat_reply
    loop .wait_bat_response
    post_code 0xC8
    dec bl
    jnz .reset_keyboard
    mov al, 0xD2
    jmp keyboard_halt
.bat_reply:
    cmp al, 0xAA
    jne .bat_failed
    post_code 0xC7
    mov al, 0xAE
    call kbc_command
    jc .command_failed
    call kbc_wait_input_clear
    jc .command_failed
    post_code 0xC9
    ret
.reset_resend:
    mov al, 0xD0
    jmp keyboard_halt
.bat_failed:
    mov al, 0xD4
    jmp keyboard_halt
.reset_write_failed:
    mov al, 0xEB
    jmp keyboard_halt

.pre_b4_failed:
    mov al, 0xB4
    jmp keyboard_halt
.pre_b5_failed:
    mov al, 0xB5
    jmp keyboard_halt
.pre_b6_failed:
    mov al, 0xB6
    jmp keyboard_halt
.pre_b7_failed:
    mov al, 0xB7
    jmp keyboard_halt
.pre_b8_failed:
    mov al, 0xB8
    jmp keyboard_halt
.input_failed:
    mov al, 0xE7
    jmp keyboard_halt
.self_test_timeout:
    mov al, 0xE8
    jmp keyboard_halt
.self_test_bad:
    mov al, 0xE9
    jmp keyboard_halt
.command_failed:
    mov al, 0xEA
    jmp keyboard_halt
keyboard_halt:
    mov dx, POST_PORT
    out dx, al
    jmp hard_halt
