; PS/2 AUX services. OEM F000:9CC5/A01D: IRQ12, D4h transport, C2h ABI.
; Keep mouse state separate from ATA/floppy in the relocatable EBDA.
%define M_HANDLER  0xB0             ; Far callback, RETF, four word arguments.
%define M_ENABLED  0xB4
%define M_COUNT    0xB5
%define M_PACKET   0xB6             ; Three bytes, status/X/Y.
%define M_COMMAND  0xB9             ; BIOS controller policy, retained across calls.
%ifdef MOUSE_DIAGNOSTIC
%define M_TRACE_N  0xBA
%define M_TRACE    0xBB             ; Up to eight status/data reply pairs.
%define M_RAW_CB   0xCB
%define M_STAGE    0xCC
%endif

system_configuration:
    dw 8
    db 0xFC, 1, 0, 0x74, 0x40, 0, 0, 0 ; AT, RTC, IRQ1 intercept, EBDA, INT16/09.

init_mouse:
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    mov byte [fs:M_COMMAND], 0x4D ; arm_keyboard_runtime's AT policy, AUX IRQ off.
    cmp byte [fs:C_PORTS + P_MOUSE], 0
    jne .enabled
    xor ax, ax
    mov ds, ax
    and word [0x0410], 0xFFFB
    mov dword [fs:M_HANDLER], 0
    mov word [fs:M_ENABLED], 0
    mov byte [fs:M_PACKET], 0
    mov word [fs:M_PACKET+1], 0
    in al, 0xA1
    or al, 0x10
    out 0xA1, al
    mov al, 0xA7
    call kbc_command
    jmp .done
.enabled:
    post_code 0xA5
    mov ax, 0xC205
    mov bh, 3
    int 0x15
%ifdef MOUSE_DIAGNOSTIC
    pushf
    call mouse_report
    popf
%endif
    jc .absent
    xor ax, ax
    mov ds, ax
    or word [0x0410], 4
    post_code 0xA6
    jmp .done
.absent:
    ; A disconnected mouse must not prevent keyboard or disk boot.
    post_code 0xA7
.done:
    pop fs
    pop es
    pop ds
    popad
    ret

; Entry has the common INT15 BP frame. Poll with IF clear: IRQ1, IRQ12 and
; the timer LED writer cannot steal replies or split a D4/data transaction.
mouse_int15:
    cli                         ; EMM386 can reflect BIOS calls with virtual IF set.
    push si
    push di
    push ds
    push fs
    call load_bios_state
    cmp byte [fs:C_PORTS + P_MOUSE], 0
    je .interface_error
    cmp al, 7
    ja .bad_function
    cmp al, 7
    je .handler
    cmp al, 0
    jne .begin
    cmp bh, 1
    ja .bad_function
    jne .begin
    cmp word [fs:M_HANDLER+2], 0
    jne .begin
    cmp word [fs:M_HANDLER], 0
    je .no_handler
.begin:
    mov si, ax
    call mouse_begin
    jc .interface_error
    mov ax, si
    cmp al, 0
    je .enable
    cmp al, 1
    je .reset
    cmp al, 2
    je .rate
    cmp al, 3
    je .resolution
    cmp al, 4
    je .id
    cmp al, 5
    je .initialize
    ; C206: BH=0 status, 1/2 scaling.
    cmp bh, 2
    ja .invalid_active
    test bh, bh
    jz .status
    mov al, 0xE5
    add al, bh
    call mouse_send
    jmp .finish
.enable:
    mov al, 0xF5
    sub al, bh
    call mouse_send
    jc .finish
    mov [fs:M_ENABLED], bh
    jmp .finish
.initialize:
    cmp bh, 3
    jne .invalid_active
    push bx
    call mouse_reset_device
    pop bx                    ; C205 retains packet length; C201 returns AA/ID.
    jc .initialize_failed
    or byte [fs:M_COMMAND], 2  ; OEM initialized interface remains IRQ-ready.
    jmp .finish
.initialize_failed:
    and byte [fs:M_COMMAND], 0xFD
    stc
    jmp .finish
.reset:
    call mouse_reset_device
    jmp .finish
.rate:
    cmp bh, 6
    ja .invalid_active
    mov al, 0xF3
    call mouse_send
    jc .finish
    push bx
    mov bl, bh
    xor bh, bh
    mov al, [cs:mouse_rates+bx]
    pop bx
    call mouse_send
    jmp .finish
.resolution:
    cmp bh, 3
    ja .invalid_active
    mov al, 0xE8
    call mouse_send
    jc .finish
    mov al, bh
    call mouse_send
    jmp .finish
.id:
    mov al, 0xF2
    call mouse_send
    jc .finish
    call mouse_read
    jc .finish
    mov bh, al
    jmp .finish
.status:
    mov al, 0xE9
    call mouse_send
    jc .finish
    call mouse_read
    jc .finish
    mov bl, al
    call mouse_read
    jc .finish
    mov cl, al
    call mouse_read
    jc .finish
    mov dl, al
    jmp .finish
.handler:
    mov ax, es
    or ax, bx
    jnz .install
    ; Removal disables delivery before removing the far pointer.
    call mouse_begin
    jc .interface_error
    mov byte [fs:M_ENABLED], 0
    mov al, 0xF5
    call mouse_send
    pushf
    call mouse_end
    popf
    jc .return_error
.install:
    mov [fs:M_HANDLER], bx
    mov [fs:M_HANDLER+2], es
    mov byte [fs:M_COUNT], 0
    xor ah, ah
    jmp .good
.invalid_active:
    mov ah, 2
    stc
    jmp .finish
.finish:
    ; End always releases the keyboard and applies the current mouse state.
    push ax
    pushf
    call mouse_end
    jc .end_failed
    popf
    pop ax
    jc .return_error
    xor ah, ah
.good:
    and word [ss:bp+6], 0xFFFE
    jmp .return
.end_failed:
    popf
    pop ax
.interface_error:
    mov ah, 3
    jmp .return_error
.bad_function:
    mov ah, 1
    jmp .return_error
.no_handler:
    mov ah, 5
.return_error:
    or word [ss:bp+6], 1
.return:
    pop fs
    pop ds
    pop di
    pop si
    pop bp
    iret

; Inhibit both clocks, route queued keyboard bytes through its existing
; decoder, discard incomplete mouse packets, then take reply ownership.
mouse_begin:
    push ax
    push cx
%ifdef MOUSE_DIAGNOSTIC
    mov byte [fs:M_TRACE_N], 0
    mov byte [fs:M_STAGE], 1
%endif
    mov al, 0xA7
    call kbc_command
    jc .failed
    mov cx, 32
.drain:
    mov al, 0xAD
    call kbc_command
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    in al, KBC_STATUS
    test al, 1
    jz .empty
    test al, 0x20
    jnz .aux
    int 0x09
    jmp .next
.aux:
    in al, KBC_DATA
.next:
    loop .drain
    jmp .failed
.empty:
%ifdef MOUSE_DIAGNOSTIC
    mov byte [fs:M_STAGE], 2
%endif
    ; OEM programs its known policy. Windows VKD does not reliably provide
    ; a controller-byte reply with the keyboard inhibited. Retain our policy
    ; rather than issue20h and wait for a reply that never becomes available.
    mov al, [fs:M_COMMAND]
%ifdef MOUSE_DIAGNOSTIC
    mov [fs:M_RAW_CB], al
%endif
    and al, 0xCF                   ; Preserve established AUX IRQ readiness.
    mov [fs:M_COMMAND], al
    or al, 0x10                    ; Keyboard clock off for polling.
    and al, 0xFD                   ; Suppress AUX IRQ only while owning replies.
    call mouse_command_byte
    jc .failed
    mov byte [fs:M_COUNT], 0
%ifdef MOUSE_DIAGNOSTIC
    mov byte [fs:M_STAGE], 3
%endif
    clc
    jmp .done
.failed:
    call mouse_end
    stc
.done:
    pop cx
    pop ax
    ret

mouse_end:
    push ax
    mov al, [fs:M_COMMAND]
    cmp byte [fs:C_PORTS + P_MOUSE], 0
    jne .enabled
    mov byte [fs:M_ENABLED], 0
    mov byte [fs:M_COUNT], 0
    and al, 0xCD
    or al, 0x20
.enabled:
    cmp byte [fs:M_ENABLED], 0
    je .write
    or al, 2
.write:
    mov ah, al
    call mouse_command_byte
    pushf
    in al, 0xA1
    or al, 0x10
    test ah, 2                    ; Readiness is independent of F4/F5 streaming.
    jz .mask
    and al, 0xEF
.mask:
    out 0xA1, al
    in al, 0x21
    and al, 0xFB
    out 0x21, al
    popf
    pop ax
    ret

mouse_reset_device:
    mov byte [fs:M_ENABLED], 0
    mov al, 0xFF
    call mouse_send
    jc .done
    call mouse_read
    jc .done
    cmp al, 0xAA
    jne .bad_reply
    mov bl, al
    call mouse_read
    jc .done
    mov bh, al
.done:
    ret
.bad_reply:
    mov ah, 4
    stc
    ret

mouse_command_byte:
    push ax
    mov al, 0x60
    call kbc_command
    pop ax
    jc .done
    call kbc_write_data
    jc .done
    call kbc_wait_input_clear
.done:
    ret

; Send one AUX byte, require FA, retry FE only twice. All waits are bounded.
mouse_send:
    push bx
%ifdef MOUSE_DIAGNOSTIC
    mov byte [fs:M_STAGE], 4
%endif
    mov bl, al
    mov bh, 3
.again:
    mov al, 0xD4
    call kbc_command
    jc .timeout
    mov al, bl
    call kbc_write_data
    jc .timeout
    call mouse_read
    jc .done
    cmp al, 0xFA
    je .ok
    cmp al, 0xFE
    jne .bad
    dec bh
    jnz .again
.bad:
    mov ah, 4
    stc
    jmp .done
.timeout:
    mov ah, 3
    stc
    jmp .done
.ok:
    xor ah, ah
    clc
.done:
    pop bx
    ret

mouse_read:
    push cx
%ifdef MOUSE_DIAGNOSTIC
    push dx
%endif
    mov cx, 500
.wait:
    in al, KBC_STATUS
%ifdef MOUSE_DIAGNOSTIC
    mov dl, al
%endif
    and al, 0x21
    cmp al, 0x21
    je .ready
    call kbc_delay_2ms
    loop .wait
    mov ah, 3
    mov al, 0xFF
    stc
    jmp .done
.ready:
    in al, KBC_DATA
    clc
.done:
%ifdef MOUSE_DIAGNOSTIC
    pushf
    push bx
    movzx bx, byte [fs:M_TRACE_N]
    cmp bl, 8
    jae .trace_full
    inc byte [fs:M_TRACE_N]
    shl bx, 1
    mov [fs:M_TRACE+bx], dl
    mov [fs:M_TRACE+bx+1], al
.trace_full:
    pop bx
    popf
    pop dx
%endif
    pop cx
    ret

int74:
    pushad
    push ds
    push es
    push fs
    push gs
    call load_bios_state
    in al, KBC_STATUS
    and al, 0x21
    cmp al, 0x21
    jne .eoi
    in al, KBC_DATA
    cmp byte [fs:C_PORTS + P_MOUSE], 0
    je .eoi
    ; OEM and Windows use the registered callback even when software has
    ; restarted F4 reporting directly after a BIOS reset.
    cmp word [fs:M_HANDLER], 0
    jne .handler_present
    cmp word [fs:M_HANDLER+2], 0
    je .eoi
.handler_present:
    movzx bx, byte [fs:M_COUNT]
    test bx, bx
    jnz .byte
    test al, 8                     ; First byte synchronization.
    jz .eoi
.byte:
    mov [fs:M_PACKET+bx], al
    inc bl
    cmp bl, 3
    jb .partial
    mov byte [fs:M_COUNT], 0
    xor ax, ax
    mov al, [fs:M_PACKET]
    push ax
    mov al, [fs:M_PACKET+1]
    push ax
    mov al, [fs:M_PACKET+2]
    push ax
    push word 0
    ; OEM 9E08 stack order: status, X, Y, zero. Callback returns with RETF.
    call far [fs:M_HANDLER]
    add sp, 8
    cli
    jmp .eoi
.partial:
    mov [fs:M_COUNT], bl
.eoi:
    mov al, 0x20
    out 0xA0, al
    out 0x20, al
    pop gs
    pop fs
    pop es
    pop ds
    popad
    iret

mouse_rates: db 10,20,40,60,80,100,200

%ifdef MOUSE_DIAGNOSTIC
mouse_report:
    pushad
    push fs
    call load_bios_state
    mov dx, ax
    mov di, bx
    mov si, mouse_report_title
    call print_string
    mov al, dh
    call mouse_hex
    mov al, '/'
    call mouse_char
    mov ax, di
    xchg al, ah
    call mouse_hex
    mov ax, di
    call mouse_hex
    mov si, mouse_report_platform
    call print_string
    out CHIPSET_CONFIG_ON, al
    mov al, KBC_PLATFORM_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    out CHIPSET_CONFIG_OFF, al
    call mouse_hex
    mov si, mouse_report_cb
    call print_string
    mov al, [fs:M_RAW_CB]
    call mouse_hex
    mov al, '/'
    call mouse_char
    mov al, [fs:M_COMMAND]
    call mouse_hex
    mov si, mouse_report_stage
    call print_string
    mov al, [fs:M_STAGE]
    call mouse_hex
    mov si, mouse_report_rx
    call print_string
    xor di, di
    movzx cx, byte [fs:M_TRACE_N]
    jcxz .done
.reply:
    mov al, [fs:M_TRACE+di]
    call mouse_hex
    mov al, ':'
    call mouse_char
    mov al, [fs:M_TRACE+di+1]
    call mouse_hex
    mov al, ' '
    call mouse_char
    add di, 2
    loop .reply
.done:
    mov si, mouse_report_end
    call print_string
    mov cx, 2500
.hold:
    call kbc_delay_2ms
    loop .hold
    pop fs
    popad
    ret
mouse_hex:
    push ax
    shr al, 4
    call .nibble
    pop ax
    and al, 15
.nibble:
    add al, '0'
    cmp al, '9'
    jbe mouse_char
    add al, 7
mouse_char:
    push ax
    push bx
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    pop bx
    pop ax
    ret
mouse_report_title: db 13,10,'PS/2 init AH/BX=',0
mouse_report_platform: db ' KBCFG=',0
mouse_report_cb: db ' CB=',0
mouse_report_stage: db ' stage=',0
mouse_report_rx: db 13,10,'PS/2 RX status:data = ',0
mouse_report_end: db 13,10,'Mouse probe complete; boot in 5 seconds.',13,10,0
%endif
