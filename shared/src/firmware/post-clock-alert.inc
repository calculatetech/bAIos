    pushad
    push ds
    push fs
    call load_bios_state
    xor ax, ax
    mov ds, ax
    ; A reset during the tone must not leave the previous POST beep active.
    in al, 0x61
    test al, 3
    jz .clock
    and al, 0xFC
    out 0x61, al
.clock:
    cmp byte [fs:C_VALID], 1
    je .date
    or byte [fs:C_ERROR], 4
.date:
    xor bl, bl              ; Invalid clock domains: time=1, date=2.
    mov ah, 4
    int 0x1A
    jnc .time
    or bl, 2
.time:
    mov ah, 2
    int 0x1A
    jnc .clock_checked
    or bl, 1
.clock_checked:
    test bl, bl
    jz .checked
    or byte [fs:C_ERROR], 1
.checked:
    test byte [fs:C_ERROR], 5
    jz .done
.alert:
    cmp byte [fs:P_PHASE], 0
    je .alert_cursor_ready
    pushad
    call post_message_cursor
    popad                    ; BL retains the invalid clock domains.
.alert_cursor_ready:
    mov ax, [0x041C]
    mov [0x041A], ax          ; A stale queued key must not dismiss this notice.
    mov al, [fs:C_ERROR]
    and al, 5
    cmp al, 5
    jne .settings_notice
    mov si, u_cmos_clock_invalid
    call print_string
    jmp .choices
.settings_notice:
    test byte [fs:C_ERROR], 4
    jz .clock_notice
    mov si, u_cmos_invalid
    call print_string
.clock_notice:
    test byte [fs:C_ERROR], 1
    jz .choices
    mov si, u_clock_unset
    call print_string
.choices:
    cmp byte [fs:C_BASE_VALID], 1
    jne .recover
    cmp byte [fs:C_HALT], 1
    je .done
.recover:
    mov si, u_cmos_recover
    call print_string
    call post_error_tone
.choice:
    call post_notice_wait
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .done
    cmp al, 13
    je .defaults
    or al, 0x20
    cmp al, 'd'
    jne .choice
.defaults:
    test bl, 2
    jz .default_time
    mov cx, 0x1980
    mov dx, 0x0101
    mov ah, 5
    int 0x1A
    jc .clock_error
.default_time:
    test bl, 1
    jz .verify_clock
    mov al, 0x0B
    call rtc_read
    xor cx, cx
    xor dx, dx
    and al, 1
    mov dl, al              ; Retain the native daylight-saving flag.
    mov ah, 3
    int 0x1A
    jc .clock_error
.verify_clock:
    mov ah, 4
    int 0x1A
    jc .clock_error
    mov ah, 2
    int 0x1A
    jc .clock_error
    test byte [fs:C_ERROR], 4
    jz .done                 ; Keep valid settings when only the clock failed.
    call setup_defaults
    call settings_save
    jc .settings_error
    call settings_load
    cmp byte [fs:C_VALID], 1
    jne .settings_error
    jmp controlled_defaults_restart
.clock_error:
    mov si, u_clock_save_error
    jmp .save_error
.settings_error:
    mov si, u_save_error
.save_error:
    call print_string
    mov byte [fs:S_SETUP_REQUEST], 1
.done:
    pop fs
    pop ds
    popad
    ret
