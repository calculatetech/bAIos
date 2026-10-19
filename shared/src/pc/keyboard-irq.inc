int09:
    push ax
    push bx
    push cx
    push dx
    push si
    push ds
    mov ax, 0x0040
    mov ds, ax
    in al, KBC_STATUS
    ; EDIT/QBasic reads the scan latch before chaining IRQ1. OEM E987-EA02
    ; reads port60 even with OBF clear. Polling callers already require OBF.
    ; A pending AUX byte still belongs exclusively to IRQ12.
    and al, 0x21
    cmp al, 0x21
    je .eoi

    mov al, 0xAD
    call kbc_command
    jc .controller_failed
    in al, KBC_DATA
    ; OEM EA04: let EMM386 leave V86 before Ctrl+Alt+Del enters warm POST.
    ; Interceptors may replace AL or clear CF to consume the scan.
    stc
    mov ah, 0x4F
    int 0x15
    jnc .scan_consumed
    mov bl, al
%ifdef KEYBOARD_DIAGNOSTIC
    inc byte [0x00A4]
    mov [0x00A5], bl
%endif

    ; Command replies can interleave with E0/E1 scan sequences. Do not clear
    ; the scan prefix or treat an LED acknowledgement as a keystroke.
    cmp bl, 0xFA
    je .led_ack
    cmp bl, 0xFE
    je .led_resend

    cmp byte [KB_E1_REMAIN], 0
    je .not_e1_tail
    dec byte [KB_E1_REMAIN]
    jnz .reenable
    and byte [KB_EXT_FLAGS], 0xFE
    jmp .reenable
.not_e1_tail:
    cmp bl, 0xE1
    jne .not_e1
    mov byte [KB_E1_REMAIN], 5
    or byte [KB_EXT_FLAGS], 1
    mov byte [KB_PAUSED], 1
    cmp byte [KB_POST_STATE], 1
    jb .reenable
    cmp byte [KB_POST_STATE], 2
    ja .reenable
    add byte [KB_POST_STATE], 2
    jmp .reenable
.not_e1:
    cmp bl, 0xE0
    jne .not_e0
    or byte [KB_EXT_FLAGS], 0x02
    jmp .reenable
.not_e0:
    xor cx, cx
    test byte [KB_EXT_FLAGS], 0x02
    jz .prefix_ready
    mov cl, 1
    and byte [KB_EXT_FLAGS], 0xFD
.prefix_ready:
    mov dl, bl
    and bl, 0x7F

    ; Only a fresh make resumes POST. Do not queue that key. Prefix tails,
    ; command replies, and key releases must not release Pause.
    test dl, 0x80
    jnz .post_resume_done
    cmp byte [KB_PAUSED], 0
    je .post_resume_done
    mov byte [KB_PAUSED], 0
    cmp byte [KB_POST_STATE], 3
    jb .reenable
    sub byte [KB_POST_STATE], 2
    jmp .reenable
.post_resume_done:

    cmp bl, 0x2A
    je .left_shift
    cmp bl, 0x36
    je .right_shift
    cmp bl, 0x1D
    je .control
    cmp bl, 0x38
    je .alt
    cmp bl, 0x3A
    je .caps_lock
    cmp bl, 0x45
    je .num_lock
    cmp bl, 0x46
    je .scroll_lock

    test dl, 0x80
    jnz .reenable
    test cl, cl
    jz .unprefixed_make
    cmp bl, 0x2A
    je .reenable
    cmp bl, 0x37
    je .reenable
    cmp bl, 0x1C
    je .keypad_enter
    cmp bl, 0x35
    je .keypad_divide
    cmp bl, 0x47
    jb .reenable
    cmp bl, 0x53
    ja .reenable
    cmp bl, 0x53
    jne .queue_extended
    mov al, [KB_FLAGS]
    and al, 0x0C
    cmp al, 0x0C
    je warm_reset
.queue_extended:
    xor al, al
    mov ah, bl
    test cl, cl
    jz .navigation_modifiers
    mov al, 0xE0
.navigation_modifiers:
    test byte [KB_FLAGS], 0x08
    jz .navigation_control
    test cl, cl
    jz .navigation_queue
    add ah, 0x50
    xor al, al
    jmp .navigation_queue
.navigation_control:
    test byte [KB_FLAGS], 0x04
    jz .navigation_queue
    xor bh, bh
    mov ah, [cs:keyboard_keypad_control + bx - 0x47]
    xor al, al
.navigation_queue:
    call keyboard_enqueue
    jmp .reenable

.keypad_enter:
    mov ax, 0xE00D
    test byte [KB_FLAGS], 0x08
    jz .keypad_enter_control
    mov ax, 0xA600
    jmp .navigation_queue
.keypad_enter_control:
    test byte [KB_FLAGS], 0x04
    jz .navigation_queue
    mov al, 0x0A
    jmp .navigation_queue
.keypad_divide:
    mov ax, 0xE02F
    test byte [KB_FLAGS], 0x08
    jz .keypad_divide_control
    mov ax, 0xA400
    jmp .navigation_queue
.keypad_divide_control:
    test byte [KB_FLAGS], 0x04
    jz .navigation_queue
    mov ax, 0x9500
    jmp .navigation_queue

.unprefixed_make:
    cmp bl, 0x54                 ; SysRq is not ordinary Alt input.
    je .reenable
    cmp bl, 0x53
    jne .not_keypad_delete
    mov al, [KB_FLAGS]
    and al, 0x0C
    cmp al, 0x0C
    je warm_reset
.not_keypad_delete:
    cmp bl, 0x47
    jb .not_keypad
    cmp bl, 0x53
    ja .not_keypad
    xor bh, bh
    mov al, [cs:keyboard_keypad + bx - 0x47]
    cmp bl, 0x4A
    je .alt_text
    cmp bl, 0x4E
    je .alt_text
    mov ah, [KB_FLAGS]
    test ah, 0x0C
    jnz .queue_extended
    test ah, 0x03
    jz .keypad_num
    xor ah, 0x20
.keypad_num:
    test ah, 0x20
    jz .queue_extended
.keypad_text:
    mov ah, bl
    call keyboard_enqueue
    jmp .reenable
.not_keypad:
    cmp bl, 0x3B
    jb .not_function
    cmp bl, 0x44
    jbe .function_legacy
    cmp bl, 0x57
    je .f11
    cmp bl, 0x58
    je .f12
    jmp .not_function
.f11:
    mov ah, 0x85
    jmp .function_enhanced
.f12:
    mov ah, 0x86
.function_enhanced:
    mov si, keyboard_function_enhanced
    jmp .function_modifier
.function_legacy:
    mov ah, bl
    mov si, keyboard_function_legacy
.function_modifier:
    xor bx, bx
    mov al, [KB_FLAGS]
    test al, 0x08
    jnz .function_alt
    test al, 0x04
    jnz .function_control
    test al, 0x03
    jz .function_queue
    inc bx
    jmp .function_queue
.function_control:
    mov bl, 2
    jmp .function_queue
.function_alt:
    mov bl, 3
.function_queue:
    add ah, [cs:si+bx]
    xor al, al
    call keyboard_enqueue
    jmp .reenable

.not_function:
    cmp bl, 0x58
    ja .reenable
.translate:
    xor bh, bh
    mov al, [cs:keyboard_normal + bx]
    mov dh, al
    mov ah, [KB_FLAGS]
    test ah, 0x03
    jz .caps
    mov al, [cs:keyboard_shift + bx]
.caps:
    test byte [KB_FLAGS], 0x40
    jz .control_text
    cmp dh, 'a'
    jb .control_text
    cmp dh, 'z'
    ja .control_text
    xor al, 0x20
.control_text:
    test byte [KB_FLAGS], 0x04
    jz .alt_text
    cmp dh, 'a'
    jb .alt_text
    cmp dh, 'z'
    ja .alt_text
    mov al, dh
    sub al, 0x60
.alt_text:
    test byte [KB_FLAGS], 0x08
    jz .text_ready
    xor al, al
    mov ah, bl
    cmp bl, 2
    jb .alt_queue
    cmp bl, 0x0D
    ja .alt_queue
    add ah, 0x76              ; Alt1..Alt0, Alt-, Alt= use 78h..83h.
.alt_queue:
    call keyboard_enqueue
    jmp .reenable
.text_ready:
    test al, al
    jz .reenable
    mov ah, bl
    call keyboard_enqueue
    jmp .reenable

.left_shift:
    test cl, cl
    jnz .reenable
    test dl, 0x80
    jnz .left_shift_up
    or byte [KB_FLAGS], 0x02
    jmp .reenable
.left_shift_up:
    and byte [KB_FLAGS], 0xFD
    jmp .reenable

.right_shift:
    test cl, cl
    jnz .reenable
    test dl, 0x80
    jnz .right_shift_up
    or byte [KB_FLAGS], 0x01
    jmp .reenable
.right_shift_up:
    and byte [KB_FLAGS], 0xFE
    jmp .reenable

.control:
    test cl, cl
    jnz .right_control
    mov al, 0x01
    jmp .set_control_side
.right_control:
    test dl, 0x80
    jnz .right_control_up
    or byte [KB_EXT_FLAGS], 0x04
    jmp .combine_control
.right_control_up:
    and byte [KB_EXT_FLAGS], 0xFB
    jmp .combine_control
.set_control_side:
    test dl, 0x80
    jnz .clear_control_side
    or [KB_FLAGS2], al
    jmp .combine_control
.clear_control_side:
    not al
    and [KB_FLAGS2], al
.combine_control:
    and byte [KB_FLAGS], 0xFB
    test byte [KB_FLAGS2], 1
    jnz .control_down
    test byte [KB_EXT_FLAGS], 4
    jz .reenable
.control_down:
    or byte [KB_FLAGS], 0x04
    jmp .reenable

.alt:
    test cl, cl
    jnz .right_alt
    mov al, 0x02
    jmp .set_alt_side
.right_alt:
    test dl, 0x80
    jnz .right_alt_up
    or byte [KB_EXT_FLAGS], 0x08
    jmp .combine_alt
.right_alt_up:
    and byte [KB_EXT_FLAGS], 0xF7
    jmp .combine_alt
.set_alt_side:
    test dl, 0x80
    jnz .clear_alt_side
    or [KB_FLAGS2], al
    jmp .combine_alt
.clear_alt_side:
    not al
    and [KB_FLAGS2], al
.combine_alt:
    and byte [KB_FLAGS], 0xF7
    test byte [KB_FLAGS2], 2
    jnz .alt_down
    test byte [KB_EXT_FLAGS], 8
    jz .reenable
.alt_down:
    or byte [KB_FLAGS], 0x08
    jmp .reenable

.caps_lock:
    test cl, cl
    jnz .reenable
    test dl, 0x80
    jnz .caps_up
    test byte [KB_FLAGS2], 0x40
    jnz .reenable
    or byte [KB_FLAGS2], 0x40
    xor byte [KB_FLAGS], 0x40
    jmp .reenable
.caps_up:
    and byte [KB_FLAGS2], 0xBF
    jmp .reenable

.num_lock:
    test cl, cl
    jnz .reenable
    test dl, 0x80
    jnz .num_up
    test byte [KB_FLAGS2], 0x20
    jnz .reenable
    or byte [KB_FLAGS2], 0x20
    xor byte [KB_FLAGS], 0x20
    jmp .reenable
.num_up:
    and byte [KB_FLAGS2], 0xDF
    jmp .reenable

.scroll_lock:
    test cl, cl
    jnz .reenable
    test dl, 0x80
    jnz .scroll_up
    test byte [KB_FLAGS2], 0x10
    jnz .reenable
    or byte [KB_FLAGS2], 0x10
    xor byte [KB_FLAGS], 0x10
    jmp .reenable
.scroll_up:
    and byte [KB_FLAGS2], 0xEF
    jmp .reenable

.led_ack:
    cmp byte [KB_LED_PHASE], 2
    jne .led_data_ack
    mov byte [KB_LED_PHASE], 3
    mov byte [KB_LED_RETRIES], 3
    jmp .reenable
.led_data_ack:
    cmp byte [KB_LED_PHASE], 4
    jne .reenable
    mov al, [KB_LED_SENT]
    mov [KB_LED_APPLIED], al
    and byte [KB_LED_FLAGS], 0xF8
    or [KB_LED_FLAGS], al
    mov byte [KB_LED_PHASE], 0
    jmp .reenable
.led_resend:
    test byte [KB_LED_PHASE], 1
    jnz .reenable
    ; The next timer tick retries the outstanding byte with a fixed limit.
    mov byte [KB_LED_WAIT], 1
    jmp .reenable
.scan_consumed:
    and byte [KB_EXT_FLAGS], 0xFC
    mov byte [KB_E1_REMAIN], 0
.reenable:
    mov al, 0xAE
    call kbc_command
    jc .controller_failed
.eoi:
    mov al, 0x61               ; Only acknowledge IRQ1, not a polling caller.
    out 0x20, al
    ; Stop the interrupted instruction stream before IRET. Release IRQ1 and
    ; the controller first so nested keyboard IRQs can consume the E1 tail
    ; and resume key. Timer IRQs may wake HLT but cannot resume the caller.
    cmp byte [KB_PAUSED], 0
    je .return
    cmp byte [KB_PAUSE_OWNER], 0
    jne .return
    mov byte [KB_PAUSE_OWNER], 1
.pause:
    sti
    hlt
    cli
    cmp byte [KB_PAUSED], 0
    jne .pause
    mov byte [KB_PAUSE_OWNER], 0
.return:
    pop ds
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    iret
.controller_failed:
    mov al, 0xEA
    jmp keyboard_halt

; Nonblocking EDh handshake. DS is the BDA; only AX is clobbered. Timer and
; IRQ1 run with IF clear. Pending scans continue through the ordinary decoder.
keyboard_led_tick:
    cmp byte [KB_LED_PHASE], 0xFF
    jne .active
    mov al, [KB_FLAGS]
    shr al, 4
    and al, 7
    cmp al, [KB_LED_SENT]
    je .done
    mov byte [KB_LED_PHASE], 0
.active:
    cmp byte [KB_LED_PHASE], 0
    jne .pending
    mov al, [KB_FLAGS]
    shr al, 4
    and al, 7
    cmp al, [KB_LED_APPLIED]
    je .done
    mov [KB_LED_SENT], al
    mov byte [KB_LED_PHASE], 1
    mov byte [KB_LED_RETRIES], 3
.pending:
    test byte [KB_LED_PHASE], 1
    jnz .send
    dec byte [KB_LED_WAIT]
    jnz .done
    dec byte [KB_LED_RETRIES]
    jz .abandon
    dec byte [KB_LED_PHASE]
.send:
    in al, KBC_STATUS
    test al, 3
    jnz .done
    mov al, 0xED
    cmp byte [KB_LED_PHASE], 1
    je .write
    mov al, [KB_LED_SENT]
.write:
    inc byte [KB_LED_PHASE]
    mov byte [KB_LED_WAIT], 4
    out KBC_DATA, al
.done:
    ret
.abandon:
    ; A failed lamp update must not stop typing or retry forever. A later
    ; change to the lock bits permits another bounded attempt.
    mov byte [KB_LED_PHASE], 0xFF
    ret

keyboard_enqueue:
    cmp ax, 0x011B
    jne .delete
    cmp byte [KB_POST_STATE], 1
    jne .queue
.escape_test:
    push ax
    push es
    mov ax, [0x000E]
    mov es, ax
    test byte [es:P_RAM_FLAGS], 1
    jz .escape_queue
    or byte [es:P_RAM_FLAGS], 2
    pop es
    pop ax
    clc
    ret
.escape_queue:
    pop es
    pop ax
    jmp .queue
.delete:
    ; Only navigation Delete (not NumLock decimal) reaches AX=5300h.
    ; Preserve the ordinary runtime queue and all BIOS-owned registers.
    cmp ax, 0x5300
    je .setup_delete
    cmp ax, 0x53E0
    jne .queue
.setup_delete:
    cmp byte [KB_POST_STATE], 1
    jne .queue
    test byte [KB_FLAGS], 0x0F
    jnz .queue
    push ax
    push es
    mov ax, [0x000E]
    mov es, ax
    mov byte [es:S_SETUP_REQUEST], 1
    pop es
    pop ax
    clc
    ret
.queue:
    mov bx, [KB_TAIL]
    mov dx, bx
    add dx, 2
    cmp dx, KB_BUFFER_END
    jb .not_wrapped
    mov dx, KB_BUFFER_START
.not_wrapped:
    cmp dx, [KB_HEAD]
    je .full
    mov [bx], ax
    mov [KB_TAIL], dx
    clc
    ret
.full:
    stc
    ret
