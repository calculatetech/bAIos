int16:
    push bp
    mov bp, sp
    push bx
    push ds
    push dx
    push ax
    mov bl, ah
    mov dl, ah
    mov ax, 0x0040
    mov ds, ax
    cmp bl, 0x00
    je .read
    cmp bl, 0x10
    je .read
    cmp bl, 0x01
    je .status
    cmp bl, 0x11
    je .status
    cmp bl, 0x02
    je .shift_status
    cmp bl, 0x12
    je .enhanced_shift_status
    cmp bl, 0x09
    je .capabilities
    cmp bl, 0x05
    je .store
    pop ax                    ; Unsupported functions retain the caller's AX.
    jmp .done

.read:
    add sp, 2
    cli
.read_wait:
    call keyboard_poll
    mov bx, [KB_HEAD]
    cmp bx, [KB_TAIL]
    jne .consume
    sti
    hlt
    cli
    jmp .read_wait
.consume:
    mov ax, [bx]
    add bx, 2
    cmp bx, KB_BUFFER_END
    jb .store_head
    mov bx, KB_BUFFER_START
.store_head:
    mov [KB_HEAD], bx
    call keyboard_legacy_key
    jmp .done

.status:
    add sp, 2
    cli
    ; OEM E878/E8A1: keyboard polling returns with interrupts enabled,
    ; ZF set/CF clear when empty, ZF clear/CF set when a key is ready.
    ; POWER's polling hook relies on this return after its idle call.
    or word [ss:bp + 6], 0x0240
    and word [ss:bp + 6], 0xFFFE
    call keyboard_poll
    mov bx, [KB_HEAD]
    cmp bx, [KB_TAIL]
    jne .available
    jmp .done
.available:
    mov ax, [bx]
    call keyboard_legacy_key
    and word [ss:bp + 6], 0xFFBF
    or word [ss:bp + 6], 1
    jmp .done

.shift_status:
    add sp, 2
    mov al, [KB_FLAGS]
    xor ah, ah
    jmp .done
.enhanced_shift_status:
    add sp, 2
    mov ah, [KB_FLAGS2]
    and ah, 0x73
    test byte [KB_FLAGS2], 4
    jz .right_status
    or ah, 0x80
.right_status:
    mov al, [KB_EXT_FLAGS]
    and al, 0x0C
    or ah, al
    mov al, [KB_FLAGS]
    jmp .done
.capabilities:
    pop ax
    mov al, 0x20              ; AH10h..12h supported, no invented ID service.
    jmp .done
.store:
    add sp, 2
    cli
    mov ax, cx
    call keyboard_enqueue
    mov ax, 0x0500
    jnc .done
    inc al
.done:
    pop dx
    pop ds
    pop bx
    pop bp
    iret

; Preserve E0 identity for enhanced readers, normalize for original AT clients.
keyboard_legacy_key:
    test dl, 0x10
    jnz .done
    cmp al, 0xE0
    jne .keypad
    xor al, al
    ret
.keypad:
    cmp ah, 0xE0
    jne .done
    cmp al, '/'
    jne .enter
    mov ah, 0x35
    ret
.enter:
    mov ah, 0x1C
.done:
    ret

keyboard_poll:
    in al, KBC_STATUS
    ; Check the source before calling a hooked IRQ1 vector: EDIT reads 60h
    ; before chaining, so int09's own AUX check is too late for that caller.
    and al, 0x21
    cmp al, 0x01
    jne .done
    ; All callers have IF clear. A pending/in-service IRQ1 owns this byte;
    ; consuming it here would leave EDIT's empty-OBF latch path a duplicate.
    mov al, 0x0A
    out 0x20, al
    in al, 0x20
    test al, 2
    jnz .done
    mov al, 0x0B
    out 0x20, al
    in al, 0x20
    test al, 2
    mov al, 0x0A               ; Restore normal IRR register selection.
    out 0x20, al
    jnz .done
    int 0x09
.done:
    ret

; Drain pending input at POST boundaries, preserving the caller's IF.
; IRQ1 itself owns Pause, including callers which never reach this helper.
post_keyboard_wait:
    pushf
    push ax
    push cx
    push ds
    mov ax, 0x0040
    mov ds, ax
    mov cx, 10
    cli
.wait:
    call keyboard_poll
    cmp byte [KB_POST_STATE], 3
    jae .paused
    ; A Pause sequence can straddle this boundary. Allow its remaining
    ; bytes up to 20 ms to arrive; a truncated sequence must not hang POST.
    cmp byte [KB_E1_REMAIN], 0
    je .done
    sti
    call kbc_delay_2ms
    cli
    loop .wait
    jmp .done
.paused:
    sti
    hlt
    cli
    jmp .wait
.done:
    pop ds
    pop cx
    pop ax
    popf
    ret
