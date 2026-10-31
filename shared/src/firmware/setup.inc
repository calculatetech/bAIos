
; CMOS10 holds logical drive types; C/U_TYPES retain physical connector order.
; Loading fallback never writes CMOS.
settings_load:
    pushad
    push fs
    call load_bios_state
    mov dword [fs:C_TYPES], (0x01010100 | FLOPPY_DEFAULT_TYPES)
    mov byte [fs:C_SLAVE], 1
    mov dword [fs:C_BASE_VALID], 0x02000100
    mov byte [fs:C_BOOT], DEFAULT_BOOT_FIRST
    mov word [fs:C_BOOT_SECOND], DEFAULT_BOOT_REST
    mov byte [fs:C_BOOT_FOURTH], 0
    mov byte [fs:C_VALID], 0
    mov byte [fs:C_THEME], 0
    mov byte [fs:U_THEME_ACTIVE], 0
    xor bp, bp
    mov byte [fs:C_CLOCK24], 0
    mov al, 0x10
    call rtc_read
    mov dl, al
    call settings_types_valid
    jc .record
    test dl, dl
    jz .record
    mov [fs:C_TYPES], dl
.record:
    mov al, 0x38
    call rtc_read
    cmp al, 'B'
    jne .done
    mov bl, al
    mov al, 0x39
    call rtc_read
    cmp al, '8'
    jne .done
    add bl, al
    mov al, 0x3A
    call rtc_read
    cmp al, 1
    je .schema
    cmp al, 2
    je .schema
    cmp al, 3
    je .schema
    cmp al, 4
    je .schema
    cmp al, 5
    jne .done
.schema:
    mov ch, al
    xor bh, bh              ; Legacy records have no fourth target.
    add bl, al
    mov al, dl
    call settings_types_valid
    jc .done
    add bl, dl
    mov al, 0x3B
    call rtc_read
    mov dh, al
    add bl, al
    mov al, 0x3C
    call rtc_read
    add bl, al              ; Checksum covers the packed byte, before decoding.
    cmp ch, 4
    jb .first_boot
    cmp ch, 5
    je .schema5_theme
    test al, 0xC0
    jnz .done
    movzx bp, al
    shr bp, 2
    cmp bp, THEME_COUNT
    jae .done
    and al, 3
    jmp .first_boot
.schema5_theme:
    test al, 0x80
    jnz .done
    movzx bp, al
    shr bp, 3
    cmp bp, THEME_COUNT
    jae .done
    and al, 7
.first_boot:
    cmp al, 2
    jbe .boot_valid
    cmp ch, 4
    jb .done
    cmp al, 3
    je .boot_valid
    cmp ch, 5
    jne .done
    cmp al, 4
    ja .done
.boot_valid:
    mov cl, al
    mov al, 0x3D
    call rtc_read
    add bl, al
    cmp ch, 2
    jae .schema2
    test bl, bl
    jnz .done
    cmp dh, 1
    ja .done
    mov [fs:C_HDD], dh
    mov al, 0x3E
    call rtc_read
    cmp al, 0xA5
    jne .legacy_slave
    mov byte [fs:C_SEEK], 0
.legacy_slave:
    mov al, 0x3F
    call rtc_read
    cmp al, 0xA5
    jne .legacy_boot
    mov byte [fs:C_SLAVE], 0
.legacy_boot:
    mov byte [fs:C_BOOT], 1
    mov word [fs:C_BOOT_SECOND], 2
    test cl, cl
    jz .publish
    mov byte [fs:C_BOOT], 2
    mov byte [fs:C_BOOT_SECOND], 1
    cmp cl, 1
    je .publish
    mov byte [fs:C_BOOT_SECOND], 0
    jmp .publish
.schema2:
    cmp ch, 3
    jae .policy_flags
    test dh, 0x80
    jnz .done
.policy_flags:
    mov al, dh
    and al, 0x18
    cmp al, 0x18
    je .done
    mov al, 0x3E
    call rtc_read
    add bl, al
    cmp ch, 5
    jne .second_plain
    test al, 0xC0
    jnz .done
    mov ah, al
    shr ah, 3
    cmp ah, 4
    ja .done
    mov bh, ah
    and al, 7
.second_plain:
    cmp al, 4
    ja .done
    cmp ch, 5
    je .second_valid
    cmp al, 3
    ja .done
    cmp ch, 4
    je .second_valid
    cmp al, 2
    ja .done
.second_valid:
    movzx si, al
    mov al, 0x3F
    call rtc_read
    cmp al, 4
    ja .done
    cmp ch, 5
    je .third_valid
    cmp al, 3
    ja .done
    cmp ch, 4
    je .third_valid
    cmp al, 2
    ja .done
.third_valid:
    movzx di, al
    add bl, al
    jnz .done
    test cl, cl
    jz .second_duplicate
    mov ax, si
    cmp al, cl
    je .done
    mov ax, di
    cmp al, cl
    je .done
.second_duplicate:
    test si, si
    jz .fourth_duplicate
    cmp si, di
    je .done
.fourth_duplicate:
    test bh, bh
    jz .flags
    cmp bh, cl
    je .done
    mov ax, si
    cmp bh, al
    je .done
    mov ax, di
    cmp bh, al
    je .done
.flags:
    mov [fs:C_BOOT_FOURTH], bh
    mov al, dh
    shr al, 7
    mov [fs:C_CLOCK24], al
    mov [fs:C_BOOT], cl
    mov ax, si
    mov [fs:C_BOOT_SECOND], al
    mov ax, di
    mov [fs:C_BOOT_THIRD], al
    mov al, dh
    and al, 1
    mov [fs:C_NUMLOCK], al
    mov al, dh
    shr al, 1
    and al, 1
    mov [fs:C_SEEK], al
    mov al, dh
    shr al, 2
    and al, 1
    mov [fs:C_SWAP], al
    mov al, dh
    shr al, 3
    and al, 3
    mov [fs:C_HALT], al
    mov al, dh
    shr al, 5
    not al
    and al, 1
    mov [fs:C_HDD], al
    mov al, dh
    shr al, 6
    not al
    and al, 1
    mov [fs:C_SLAVE], al
.publish:
    mov ax, bp
    mov [fs:C_THEME], al
    mov [fs:C_TYPES], dl
    mov byte [fs:C_BASE_VALID], 1
    mov byte [fs:C_VALID], 1
.done:
    cmp byte [fs:C_SWAP], 0
    je .physical_types
    ror byte [fs:C_TYPES], 4
.physical_types:
    call ide_settings_load
    call ports_settings_load
    call chipset_settings_load
    pop fs
    popad
    ret

settings_types_valid:
    push ax
    mov ah, al
    and al, 15
    shr ah, 4
    cmp al, 5
    ja .bad
    cmp ah, 5
    ja .bad
    pop ax
    clc
    ret
.bad:
    pop ax
    stc
    ret

settings_save:
    pushf
    cli
    pushad
    push fs
    call load_bios_state
    call settings_recovery_read
    movzx di, al            ; Keep prior recovery selection until the whole save succeeds.
    mov bh, [fs:U_SLAVE]
    xor bh, 1
    shl bh, 1
    mov al, [fs:U_HDD]
    xor al, 1
    or bh, al
    shl bh, 2
    or bh, [fs:U_HALT]
    shl bh, 1
    or bh, [fs:U_SWAP]
    shl bh, 1
    or bh, [fs:U_SEEK]
    shl bh, 1
    or bh, [fs:U_NUMLOCK]
    mov al, [fs:U_CLOCK24]
    shl al, 7
    or bh, al
    call settings_logical_types
    mov bl, ah
    add bl, 'B' + '8' + 5
    add bl, bh
    call settings_theme_boot
    add bl, ah
    call settings_second_fourth
    add bl, ah
    add bl, [fs:U_BOOT_THIRD]
    neg bl
.write:
    mov ax, 0x0038          ; Invalidate before data; signature published last.
    call rtc_write
%if BOARD_ATA_DEVICE_COUNT = 4
    call settings_format_prepare
    jc .bad
%endif
    call ide_settings_save
    jc .bad
    call ports_settings_save
    jc .bad
    call chipset_settings_save
    jc .bad
    call settings_logical_types
    mov al, 0x10
    call rtc_write
    mov ax, ('8' << 8) | 0x39
    call rtc_write
    mov ax, 0x053A
    call rtc_write
    mov al, 0x3B
    mov ah, bh
    call rtc_write
    mov al, 0x3C
    call settings_theme_boot
    call rtc_write
    mov al, 0x3D
    mov ah, bl
    call rtc_write
    mov al, 0x3E
    call settings_second_fourth
    call rtc_write
    mov al, 0x3F
    mov ah, [fs:U_BOOT_THIRD]
    call rtc_write
    call update_cmos_checksum
    mov ax, ('B' << 8) | 0x38
    call rtc_write
    call settings_logical_types
    mov al, 0x10
    call settings_verify_byte
    jne .bad
    mov al, 0x38
    mov ah, 'B'
    call settings_verify_byte
    jne .bad
    mov al, 0x39
    mov ah, '8'
    call settings_verify_byte
    jne .bad
    mov al, 0x3A
    mov ah, 5
    call settings_verify_byte
    jne .bad
    mov al, 0x3B
    mov ah, bh
    call settings_verify_byte
    jne .bad
    mov al, 0x3C
    call settings_theme_boot
    call settings_verify_byte
    jne .bad
    mov al, 0x3D
    mov ah, bl
    call settings_verify_byte
    jne .bad
    mov al, 0x3E
    call settings_second_fourth
    call settings_verify_byte
    jne .bad
    mov al, 0x3F
    mov ah, [fs:U_BOOT_THIRD]
    call settings_verify_byte
    jne .bad
%ifdef BOARD_SETTINGS_SAVED
    call BOARD_SETTINGS_SAVED
    jc .bad
%endif
    pop fs
    popad
    popf
    clc
    ret
.bad:
    cmp di, 0xD2
    jne .restore
    call settings_recovery_publish ; A later failure must retain Compatibility.
.restore:
    pop fs
    popad
    popf
    stc
    ret

; AH=packed theme/first boot. AL retains the caller's CMOS index.
settings_theme_boot:
    mov ah, [fs:U_THEME]
    shl ah, 3
    or ah, [fs:U_BOOT]
    ret

; Schema5 CMOS3E: second in bits0..2, fourth in bits3..5.
settings_second_fourth:
    mov ah, [fs:U_BOOT_FOURTH]
    shl ah, 3
    or ah, [fs:U_BOOT_SECOND]
    ret

; AH=logical CMOS10 types, without changing the physical Setup draft.
settings_logical_types:
    mov ah, [fs:U_TYPES]
    cmp byte [fs:U_SWAP], 0
    je .done
    ror ah, 4
.done:
    ret

; ZF reports equality. A persisted byte must not fail on one transient read.
settings_verify_byte:
    mov [fs:U_SAVE_TRACE], al
    mov [fs:U_SAVE_TRACE + 1], ah
    call rtc_read
    cmp al, ah
    je .done
    mov al, [fs:U_SAVE_TRACE]
    call kbc_delay_2ms
    call rtc_read
    cmp al, ah
.done:
    mov [fs:U_SAVE_TRACE + 2], al
    ret

post_success_tone:
    call load_bios_state
    cmp byte [fs:C_ERROR], 0
    jne .done
    push si
    mov si, post_happy_notes
    call post_tone
    pop si
.done:
    ret

post_error_tone:
    push si
    mov si, post_sad_notes
    call post_tone
    pop si
    ret

; PIT2 only. IRQ0 measures time; IRQ1 remains available during every note.
post_tone:
    pushad
    push ds
    xor ax, ax
    mov ds, ax
.note:
    cs lodsw
    test ax, ax
    jz .off
    push ax
    mov al, 0xB6
    out 0x43, al
    pop ax
    out 0x42, al
    mov al, ah
    out 0x42, al
    cs lodsb
    movzx cx, al
    in al, 0x61
    or al, 3
    out 0x61, al
    mov bp, [0x046C]
.wait:
    sti
    hlt
    mov ax, [0x046C]
    sub ax, bp
    cmp ax, cx
    jb .wait
    jmp .note
.off:
    in al, 0x61
    and al, 0xFC
    out 0x61, al
    pop ds
    popad
    ret

post_happy_notes: dw 2281
    db 2
    dw 1810
    db 2
    dw 1522
    db 2
    dw 0
post_sad_notes: dw 2712
    db 2
    dw 3419
    db 2
    dw 4571
    db 3
    dw 0

; OEM F000:2783: 250 kb/s, seek48 then8, step back to physical TRK0.
; Configured40-track drives stop at39 instead of probing beyond their travel.
post_floppy_seek:
    pushad
    push ds
    push fs
    call load_bios_state
    cmp byte [fs:C_PORTS + P_FLOPPY], 0
    je .done
    cmp byte [fs:C_SEEK], 1
    jne .done
    xor ax, ax
    mov ds, ax
    mov byte [fs:F_BUSY], 1
    mov byte [fs:0x176], 0 ; Per-drive failures; stage/status pairs at178h.
    mov byte [fs:F_CAL], 0
    xor si, si
.drive:
    cmp byte [fs:F_TYPES + si], 0
    je .next
    mov ax, si
    add al, 0x62
    out POST_PORT, al
    mov ax, si
    mov [fs:F_DRIVE], al
    mov byte [fs:F_HEAD], 0
    mov byte [fs:F_CYL], 0
    mov byte [fs:F_FUNC], 0
    mov byte [fs:F_STATUS], 0
    call fdc_prepare
    jc .error
    mov bl, 0x10
    call post_track_zero
    jc .error
    mov byte [fs:F_RATE], 2 ; OEM2825/2786: 250 kb/s gives the POST step rate.
    call fdc_specify
    jc .error
    mov al, 48
    cmp byte [fs:F_TRACKS], 40
    jne .outward
    mov al, 39
.outward:
    mov [fs:F_CYL], al
    call fdc_seek
    jc .error
    xor bl, bl
    call post_track_zero
    jc .error
    mov byte [fs:F_CYL], 8
.inward:
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .finish
    call fdc_seek
    jc .error
    cmp byte [fs:F_CYL], 0
    je .at_zero
    xor bl, bl
    call post_track_zero
    jc .error
    dec byte [fs:F_CYL]
    jmp .inward
.at_zero:
    mov bl, 0x10
    call post_track_zero
    jc .error
    mov ax, si
    add al, 0x64
    out POST_PORT, al
    jmp .next
.error:
    or byte [fs:C_ERROR], 2
    mov cx, si
    mov al, 1
    shl al, cl
    or [fs:0x176], al
    not al
    and [fs:F_CAL], al      ; Failed physical motion is not a calibrated drive.
    cmp byte [fs:P_PHASE], 0
    je .seek_error_text
    pushad
    call post_message_cursor
    popad
.seek_error_text:
    push si
    mov si, u_seek_error_a
    cmp byte [fs:F_DRIVE], 0
    je .print
    mov si, u_seek_error_b
.print:
    call print_string
    pop si
    mov ax, si
    add al, 0xEC
    out POST_PORT, al
.next:
    cmp byte [fs:F_TYPES + si], 0
    je .advance
    mov bx, si
    shl bx, 1
    mov al, [fs:F_STAGE]
    mov ah, [fs:F_STATUS]
    mov [fs:0x178 + bx], ax
.advance:
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .finish
    inc si
    cmp si, 2
    jb .drive
.finish:
    mov dx, FDC_DOR
    mov al, 0x0C
    out dx, al
    mov word [0x043F], 0
    mov byte [fs:F_BUSY], 0
    cmp byte [fs:0x176], 0
    je .done
    call post_error_notice
.done:
    pop fs
    pop ds
    popad
    ret

post_track_zero:
    mov byte [fs:F_STAGE], 4
    mov al, 4
    call fdc_write
    jc .done
    call fdc_unit_head
    call fdc_write
    jc .done
    call fdc_read
    jc .done
    and al, 0x10
    cmp al, bl
    jne .bad
    clc
.done:
    ret
.bad:
    mov byte [fs:F_STATUS], 0x40
    stc
    ret

setup_draft_defaults:
    mov byte [fs:U_THEME], 0
    mov byte [fs:U_CLOCK24], 0
    mov dword [fs:U_TYPES], (0x01010100 | FLOPPY_DEFAULT_TYPES)
    mov byte [fs:U_SLAVE], 1
    mov byte [fs:U_NUMLOCK], 1
    mov byte [fs:U_SWAP], 0
    mov byte [fs:U_HALT], 2
    mov byte [fs:U_BOOT], DEFAULT_BOOT_FIRST
    mov word [fs:U_BOOT_SECOND], DEFAULT_BOOT_REST
    mov byte [fs:U_BOOT_FOURTH], 0
    ret

; Confirmed defaults action shared by both Setup entry paths.
setup_defaults:
    call setup_draft_defaults
    mov di, U_IDE
    call ide_defaults
    mov di, U_PORTS
    call ports_defaults
    mov di, U_CHIP
    call chipset_defaults
    ret

post_numlock_apply:
    pushf
    cli
    pushad
    push ds
    call load_bios_state
    mov ax, 0x40
    mov ds, ax
    and byte [KB_FLAGS], 0xDF
    cmp byte [fs:C_NUMLOCK], 0
    je .led
    or byte [KB_FLAGS], 0x20
.led:
    mov byte [KB_LED_APPLIED], 0xFF
    cmp byte [KB_LED_PHASE], 0xFF
    jne .tick
    mov byte [KB_LED_PHASE], 0
.tick:
    call keyboard_led_tick
    pop ds
    popad
    popf
    ret

post_keyboard_presence:
    pushad
    push ds
    call load_bios_state
    xor ax, ax
    mov ds, ax
    cmp byte [0x0400 + KB_ABSENT], 0
    je .done
    or byte [fs:C_ERROR], 8
    mov si, u_keyboard_absent
    call print_string
    cmp byte [fs:C_HALT], 0
    jne .done
    call post_error_notice
.done:
    pop ds
    popad
    ret

post_error_notice:
    cmp byte [fs:C_HALT], 1
    je .done
    mov ax, [0x041C]
    mov [0x041A], ax
    mov si, u_post_continue
    call print_string
    call post_error_tone
    call post_notice_wait
.done:
    ret

; Called after VGA and keyboard arming. Getters retain RTC validation ownership.
post_clock_alert:
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

; Shared fresh-key gate. Caller has resolved FS and supplies DS=0.
post_notice_wait:
.wait_key:
    call post_keyboard_wait
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .done
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait_key
.key:
    xor ah, ah
    int 0x16                 ; Consume the notice key, not later setup input.
.done:
    ret

; Consume only requests received during hardware detection. Close before tone.
setup_post_gate:
    pushad
    push ds
    call load_bios_state
    xor ax, ax
    mov ds, ax
    call post_keyboard_wait
    cli
    mov byte [0x0400 + KB_POST_STATE], 2
    sti
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .open
    jmp .done
.open:
    call post_entering_setup
    call setup_main
    cmp byte [fs:P_PHASE], 0
    je .restored
    call post_ui_begin
.restored:
    mov byte [0x0400 + KB_POST_STATE], 2
.done:
    pop ds
    popad
    ret

setup_main:
    pushad
    push ds
    push es
    push fs
    cld
    call load_bios_state
    xor ax, ax
    mov es, ax
    mov byte [es:0x0400 + KB_POST_STATE], 0
    mov ax, [es:0x041C]
    mov [es:0x041A], ax       ; Discard only old POST input, not the controller.
    mov byte [fs:S_SETUP_REQUEST], 0
    mov dword [fs:U_PAGE], 0
    mov byte [fs:U_CONFIRMED], 0
    mov byte [fs:U_POSITION], 0
    mov al, [fs:C_THEME]
    mov [fs:U_THEME], al
    mov byte [fs:U_THEME_ACTIVE], 1
    mov al, [fs:C_CLOCK24]
    mov [fs:U_CLOCK24], al
    mov eax, [fs:C_TYPES]
    mov [fs:U_TYPES], eax
    mov al, [fs:C_SLAVE]
    mov [fs:U_SLAVE], al
    mov al, [fs:C_NUMLOCK]
    mov [fs:U_NUMLOCK], al
    mov al, [fs:C_SWAP]
    mov [fs:U_SWAP], al
    mov al, [fs:C_HALT]
    mov [fs:U_HALT], al
    mov ax, [fs:C_BOOT_SECOND]
    mov [fs:U_BOOT_SECOND], ax
    mov al, [fs:C_BOOT_FOURTH]
    mov [fs:U_BOOT_FOURTH], al
    mov si, C_IDE
    mov di, U_IDE
    mov cx, IDE_SETTINGS_SIZE
    call ide_copy_bytes
    mov si, C_PORTS
    mov di, U_PORTS
    mov cx, 8
    call ide_copy_bytes
    mov si, C_CHIP
    mov di, U_CHIP
    mov cx, CHIP_SIZE
    call ide_copy_bytes
    mov byte [fs:U_CHIP_SCREEN], 0
    mov byte [fs:U_IDE_DEVICE], 0xFF
    call setup_video_mode
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
.redraw:
    mov cl, [fs:U_FIELD]
.normalize_field:
    call setup_field_available
    jnc .draw
%ifdef BOARD_SETUP_READONLY_PAGES
    test cl,cl
    jnz .previous_field
    mov byte [fs:U_FOCUS],0
    jmp .draw
.previous_field:
%endif
    dec cl
    jmp .normalize_field
.draw:
    mov [fs:U_FIELD], cl
    call setup_draw
.input:
%ifdef EMULATOR_CHIPSET_TEST
    call chipset_test_capture_drain
%endif
%ifdef EMULATOR_PORTS_TEST
    call ports_test_capture_drain
%endif
    call setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .input
.key:
    xor ah, ah
    int 0x16
    cmp ah, 0x3E
    je .theme
    cmp ah, 0x3F
    je .theme
    cmp ah, 0x3B
    je .help
    cmp byte [fs:U_EDIT], 0
    jne .edit_key
    cmp ah, 0x43
    je .defaults
    cmp ah, 0x44
    je .save
    cmp al, 27
    je .escape
    cmp al, 9
    je .tab
    cmp ah, 0x48
    je .up
    cmp ah, 0x50
    je .down
    cmp ah, 0x49
    je .chip_page
    cmp ah, 0x51
    je .chip_page
    cmp ah, 0x4B
    je .change
    cmp ah, 0x4D
    je .change
    cmp al, 13
    jne .input
    cmp byte [fs:U_FOCUS], 0
    je .select_page
    mov cl, [fs:U_FIELD]
    call setup_field_available
    jc .input
    cmp byte [fs:U_PAGE], 0
    jne .non_clock_enter
    cmp byte [fs:U_FIELD], 2
    jb .start_edit
    jmp .choices
.non_clock_enter:
    cmp byte [fs:U_PAGE], 4
    je .exit_action
    cmp byte [fs:U_PAGE], 1
    jne .choices
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    jbe .ide_select
    cmp byte [fs:U_FIELD], 2
    jb .choices
    cmp byte [fs:U_FIELD], BOARD_ATA_DEVICE_COUNT+1
    ja .choices
    mov al, [fs:U_FIELD]
    sub al, 2
    mov [fs:U_IDE_DEVICE], al
    mov byte [fs:U_FIELD], 0
    jmp .redraw
.ide_select:
    call ide_ui_select
    jmp .redraw
.choices:
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_choices
    call chipset_ui_select
    jmp .redraw
.ordinary_choices:
    call setup_choices
    jmp .redraw
.theme:
    mov al, [fs:U_THEME]
    cmp ah, 0x3E
    jne .next_theme
    dec al
    cmp al, 0xFF
    jne .theme_selected
    mov al, THEME_COUNT - 1
    jmp .theme_selected
.next_theme:
    inc al
    cmp al, THEME_COUNT
    jb .theme_selected
    xor al, al
.theme_selected:
    mov [fs:U_THEME], al
    jmp .redraw
.select_page:
    mov byte [fs:U_FOCUS], 1
    jmp .redraw
.start_edit:
    call setup_edit_begin
    jmp .redraw
.tab:
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .tab_pane
    mov byte [fs:U_IDE_DEVICE], 0xFF
    mov byte [fs:U_FIELD], 0
.tab_pane:
    xor byte [fs:U_FOCUS], 1
    jmp .redraw
.chip_page:
    cmp byte [fs:U_PAGE], 5
    jne .input
    cmp byte [fs:U_FOCUS], 1
    jne .input
    call chipset_ui_page
    jmp .redraw
.up:
    cmp byte [fs:U_FOCUS], 0
    jne .field
    cmp byte [fs:U_PAGE], 0
    je .input
    mov al, [fs:U_PAGE]
    cmp al, 4
    je .up_exit
    cmp al, 5
    jne .up_regular
    mov al, 4
.up_regular:
    dec al
    jmp .sidebar_selected
.up_exit:
    mov al, 5
.sidebar_selected:
    mov [fs:U_PAGE], al
    mov byte [fs:U_FIELD], 0
    jmp .redraw
.down:
    cmp byte [fs:U_FOCUS], 0
    jne .field
    mov al, [fs:U_PAGE]
    cmp al, 4
    je .input
    cmp al, 5
    jne .down_regular
    mov al, 4
    jmp .sidebar_selected
.down_regular:
    inc al
    cmp al, 4
    jne .sidebar_selected
    mov al, 5
    jmp .sidebar_selected
.field:
    mov bl, 1
    cmp byte [fs:U_PAGE], 0
    jne .field_count
    mov bl, 2
.field_count:
    cmp byte [fs:U_PAGE], 5
    jne .non_chip_field
    call chipset_ui_count
    mov bl, cl
    dec bl
.non_chip_field:
    cmp byte [fs:U_PAGE], 3
    jne .old_field
%ifdef BOARD_PORTS_SETUP_COUNT
    mov bl, BOARD_PORTS_SETUP_COUNT-1
%else
    mov bl, 6
%endif
.old_field:
    cmp byte [fs:U_PAGE], 2
    jne .drive_field_limit
    mov bl, BOOT_FIELD_COUNT-1
.drive_field_limit:
    cmp byte [fs:U_PAGE], 1
    jne .field_limit
    mov bl, BOARD_ATA_DEVICE_COUNT+4
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .field_limit
    mov bl, IDE_FIELD_COUNT-1
.field_limit:
    mov cl, [fs:U_FIELD]
    cmp ah, 0x48
    jne .field_down
.field_up:
    test cl, cl
    je .input
    dec cl
    call setup_field_available
    jc .field_up
    jmp .field_selected
.field_down:
    cmp cl, bl
    jae .input
    inc cl
    call setup_field_available
    jc .field_down
.field_selected:
    mov [fs:U_FIELD], cl
    jmp .redraw
.change:
    cmp byte [fs:U_FOCUS], 1
    jne .input
    mov cl, [fs:U_FIELD]
    call setup_field_available
    jc .input
    cmp byte [fs:U_PAGE], 0
    jne .non_clock_change
    cmp byte [fs:U_FIELD], 2
    jb .input
.non_clock_change:
    cmp byte [fs:U_PAGE], 4
    je .input
    cmp byte [fs:U_PAGE], 1
    jne .old_change
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .old_change
    call ide_ui_change
    jmp .redraw
.old_change:
    call setup_change
    jmp .redraw
.escape:
    cmp byte [fs:U_PAGE], 5
    jne .non_chip_escape
%ifndef BOARD_SETUP_READONLY_PAGES
    cmp byte [fs:U_FOCUS], 1
    jne .non_chip_escape
%endif
    cmp byte [fs:U_CHIP_SCREEN], 0
    je .non_chip_escape
    mov al, [fs:U_CHIP_SCREEN]
    dec al
    mov [fs:U_FIELD], al
    mov byte [fs:U_CHIP_SCREEN], 0
%ifdef BOARD_SETUP_READONLY_PAGES
    mov byte [fs:U_FOCUS], 1
%endif
    jmp .redraw
.non_chip_escape:
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .escape_pane
    mov al, [fs:U_IDE_DEVICE]
    add al, 2
    mov [fs:U_FIELD], al
    mov byte [fs:U_IDE_DEVICE], 0xFF
    jmp .redraw
.escape_pane:
    cmp byte [fs:U_FOCUS], 0
    je .discard
    mov byte [fs:U_FOCUS], 0
    jmp .redraw
.help:
    call setup_help
    jmp .redraw
.exit_action:
    cmp byte [fs:U_FIELD], 0
    je .save
.discard:
    mov si, u_discard_confirm
    call setup_confirm
    jc .redraw
    call setup_restore_text
    pop fs
    pop es
    pop ds
    popad
    ret
.defaults:
    mov si, u_defaults_confirm
    call setup_confirm
    jc .redraw
    call setup_defaults
    jmp .redraw
.save:
    mov si, u_save_confirm
    call setup_confirm
    jc .redraw
    call settings_save
    jc .save_error
    call setup_restore_text
    mov ax, 0x0040
    mov ds, ax
    jmp warm_reset
.save_error:
    ui_text 19, 23, u_save_error, 0x0C
    ui_text 20, 23, u_save_trace, 0x07
    mov di, 20 * 160 + 49 * 2
    mov bx, U_SAVE_TRACE
    mov cx, 3
.save_byte:
    mov al, [fs:bx]
    call setup_hex8
    mov ax, 0x0720
    push ax
    call setup_color
    stosw
    pop ax
    inc bx
    loop .save_byte
    jmp .input
.edit_key:
    cmp al, 27
    je .cancel_edit
    cmp al, 13
    je .apply_edit
    cmp al, 8
    je .backspace
    cmp byte [fs:U_EDIT], 2
    jne .edit_digit
    cmp byte [fs:U_CLOCK24], 0
    jne .edit_digit
    cmp al, 'A'
    je .meridiem
    cmp al, 'a'
    je .meridiem
    cmp al, 'P'
    je .meridiem
    cmp al, 'p'
    je .meridiem
.edit_digit:
    cmp al, '0'
    jb .input
    cmp al, '9'
    ja .input
    movzx bx, byte [fs:U_POSITION]
    mov [fs:U_BUFFER + bx], al
    inc bl
    cmp byte [fs:U_EDIT], 1
    jne .time_position
    cmp bl, 2
    je .skip_separator
    cmp bl, 5
    je .skip_separator
    cmp bl, 10
    jb .position
    xor bl, bl
    jmp .position
.time_position:
    cmp bl, 2
    je .skip_separator
    cmp bl, 5
    je .skip_separator
    cmp bl, 8
    jb .position
    xor bl, bl
    jmp .position
.skip_separator:
    inc bl
.position:
    mov [fs:U_POSITION], bl
    jmp .redraw
.meridiem:
    and al, 0xDF
    mov [fs:U_BUFFER + 9], al
    jmp .redraw
.backspace:
    mov bl, [fs:U_POSITION]
    test bl, bl
    jz .input
    dec bl
    cmp byte [fs:U_EDIT], 1
    jne .back_time
    cmp bl, 2
    je .back_separator
    cmp bl, 5
    je .back_separator
    jmp .position
.back_time:
    cmp bl, 2
    je .back_separator
    cmp bl, 5
    jne .position
.back_separator:
    dec bl
    jmp .position
.apply_edit:
    call setup_edit_apply
    jc .invalid
.cancel_edit:
    mov byte [fs:U_EDIT], 0
    jmp .redraw
.invalid:
    ui_text 20, 23, u_invalid, 0x0C
    jmp .input

setup_video_mode:
    push fs
    push gs
    mov ax, 0x1202
    mov bl, 0x30
    int 0x10
    mov ax, 3
    int 0x10
    mov ax, 0x1114
    xor bx, bx
    int 0x10
    mov ax, 0x1003
    xor bx, bx             ; Bright backgrounds, no blinking in Setup.
    int 0x10
    mov ah, 1
    mov cx, 0x2000
    int 0x10
    pop gs
    pop fs
    cld
    ret

; Read-only snapshot of active settings. Setup entry is already closed.
post_debug_summary:
    pushad
    push ds
    push es
    push fs
    call load_bios_state
%ifdef EMULATOR_CHIPSET_SUMMARY_LONG
    call summary_test_prepare_long
%endif
    call setup_restore_text
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov ax, 0x0720
    mov cx, 2000
    cld
    push ax
    call setup_color
    rep stosw
    pop ax
    ; Header at row0; complete frame on rows1..11, blank row12.
    mov di, 1*160
    mov cx, 9+BOARD_ATA_DEVICE_COUNT
.frame:
    mov word [es:di], 0x0BBA
    mov word [es:di+158], 0x0BBA
    add di, 160
    loop .frame
    mov di, 1*160
    call .rule
    mov word [es:1*160], 0x0BC9
    mov word [es:1*160+158], 0x0BBB
    mov di, 5*160
    call .rule
    mov di, 8*160
    call .rule
    mov di, (9+BOARD_ATA_DEVICE_COUNT)*160
    call .rule
    mov word [es:(9+BOARD_ATA_DEVICE_COUNT)*160], 0x0BC8
    mov word [es:(9+BOARD_ATA_DEVICE_COUNT)*160+158], 0x0BBC
    call post_header
    ui_text 2, 3, u_summary_processor, 0x0B
    call post_processor_name
    mov di, 2*160+20*2
    mov bh, 7
    call setup_text
    ui_text 3, 3, u_summary_fpu, 0x0B
    mov si, u_absent
    push ds
    xor ax, ax
    mov ds, ax
    test word [0x0410], 2
    pop ds
    jz .fpu
    mov si, u_detected
.fpu:
    mov di, 3*160+20*2
    mov bh, 7
    call setup_text
    ui_text 4, 3, u_l2, 0x0B
    call post_summary_cache
.memory:
    ui_text 2, 40, u_base, 0x0B
    push ds
    xor ax, ax
    mov ds, ax
    movzx eax, word [0x0413]
    pop ds
    mov di, 2*160+58*2
    call setup_number
    ui_text 2, 64, u_kb, 0x07
    ui_text 3, 40, u_extended, 0x0B
    memory_extended_kib eax
    mov di, 3*160+58*2
    call setup_number
    ui_text 3, 64, u_kb, 0x07
    ui_text 4, 40, u_summary_banks, 0x0B
    mov di, 4*160+58*2
    call post_memory_banks
    ui_text 6, 3, u_drive_a, 0x0B
    mov al, [fs:F_TYPES]
    mov di, 6*160+20*2
    call .floppy
    ui_text 7, 3, u_drive_b, 0x0B
    mov al, [fs:F_TYPES+1]
    mov di, 7*160+20*2
    call .floppy
    call ports_summary
    push fs
    mov bp,9*160
    mov cx,BOARD_ATA_DEVICE_COUNT
.disk:
    push cx
    call post_device_label
    mov di,bp
    add di,3*2
    mov bh,0x0B
    call setup_text
    call .device
    mov ax,fs
    add ax,0x20
    mov fs,ax
    add bp,160
    pop cx
    loop .disk
    pop fs
    mov bp, 11+BOARD_ATA_DEVICE_COUNT                    ; First message row after the blank separator.
    cmp byte [fs:C_ERROR], 0
    je .recovery
    mov bp, 12+BOARD_ATA_DEVICE_COUNT
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 3, u_warnings, 0x0E
    test byte [fs:C_ERROR], 1
    jz .floppy_warning
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 18, u_clock_warning, 0x0E
.floppy_warning:
    test byte [fs:C_ERROR], 2
    jz .settings_warning
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 24, u_floppy_warning, 0x0E
.settings_warning:
    test byte [fs:C_ERROR], 4
    jz .keyboard_warning
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 31, u_settings_warning, 0x0E
.keyboard_warning:
    test byte [fs:C_ERROR], 8
    jz .rom_warning
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 40, u_keyboard_warning, 0x0E
.rom_warning:
    test byte [fs:C_ERROR], 0x10
    jz .recovery
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 49, u_rom_warning, 0x0E
.recovery:
    mov al, 0x36
    call rtc_read
    and al, 0xBF
    cmp al, 0x1A
    jne .done
    mov bp, 12+BOARD_ATA_DEVICE_COUNT
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 54, u_summary_recovery, 0x0C
.done:
%ifdef BOARD_FLOPPY_POST_DETAILS
    test byte [fs:C_ERROR],2
    jz .no_floppy_details
    call BOARD_FLOPPY_POST_DETAILS
    mov bp,13+BOARD_ATA_DEVICE_COUNT
.no_floppy_details:
%endif
    mov dx, bp
    shl dx, 8
    xor bx, bx
    mov ah, 2
    int 0x10                      ; Normal BIOS/OS output continues from here.
%ifdef EMULATOR_POST_SUMMARY_TEST
    call summary_test_begin
%endif
%ifdef EMULATOR_TEST
%ifndef EMULATOR_POST_SUMMARY_TEST
%ifndef EMULATOR_CHIPSET_PREVIEW
    call summary_test_begin
%endif
%endif
%endif
    pop fs
    pop es
    pop ds
    popad
    ret
.rule:
    mov ax, 0x0BCD
    mov cx, 80
    push ax
    call setup_color
    rep stosw
    pop ax
    mov word [es:di-160], 0x0BCC
    mov word [es:di-2], 0x0BB9
    ret
.floppy:
    movzx bx, al
    mov si, u_floppies
.enum:
    shl bx, 1
    mov si, [si+bx]
    mov bh, 7
    jmp setup_text
.device:
    mov di, bp
    add di, 23*2
    mov si, u_absent
    cmp byte [fs:S_PRESENT], 1
    je .model
    cmp byte [fs:S_ATAPI], 1
    jne .device_done
.model:
    mov si, S_MODEL
    mov cx, 40                     ; Full ATA model, columns23..62.
.model_char:
    mov al, [fs:si]
    inc si
    test al, al
    jz .kind
    mov ah, 7
    push ax
    call setup_color
    stosw
    pop ax
    loop .model_char
.kind:
    mov di, bp
    add di, 64*2
    mov ax, 0x0B5B                 ; Teal brackets around compact device details.
    call setup_color
    stosw
    mov si, msg_atapi
    cmp byte [fs:S_ATAPI], 1
    je .pio
    mov eax, [fs:S_CAPACITY]
    shr eax, 11
    call setup_number
.size_end:
    cmp byte [es:di], ' '          ; Number preserves DI; find its trailing blank.
    je .size_unit
    add di, 2
    jmp .size_end
.size_unit:
    mov si, u_summary_mb
    mov bh, 7
    call setup_text
    add di, 3*2
    jmp .pio_label
.pio:
    mov bh, 7
    call setup_text
    add di, 5*2
.pio_label:
    mov si, u_summary_pio
    mov bh, 7
    call setup_text
    add di, 4*2
%ifdef BOARD_ATA_PIO_MAX
%ifdef BOARD_ATA_PIO_ADAPTER
    mov al,[fs:S_PIO_MODE]
    add al,'0'
    mov ah,7
    call setup_color
    stosw
%else
    call ide_pio_mode_text
%endif
%endif
    mov ax, 0x0B5D
    call setup_color
    stosw
    ret
.device_done:
    mov bh, 7
    jmp setup_text

post_header:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov ax, 0x1F20
    mov cx, 80
    push ax
    call setup_color
    rep stosw
    pop ax
    ui_text 0, 3, u_platform, 0x1B
    ui_text 0, 37, u_summary, 0x1F
    ui_text 0, 58, u_build, 0x1B
    mov di, 69*2
    mov si, 0xFFF5
    mov cx, 8
.date:
    lodsb
    mov ah, 0x1F
    push ax
    call setup_color
    stosw
    pop ax
    loop .date
    pop es
    pop ds
    popad
    ret

; Intel AP-485 reset signature, retained across software warm POST.
; Report the model, without deriving a core clock from a timing profile.
post_processor_name:
    call cpu_detect_name
    test si,si
    jnz .done
    mov ax, [fs:S_CPU_SIGNATURE]
    mov si, u_summary_unknown
    mov bx, ax
    and bx, 0x0F00
    cmp bx, 0x0500
    je .pentium
    cmp bx, 0x0400
    jne .done
    shr ax, 4
    and ax, 15
    mov bx, ax
    shl bx, 1
    mov si, [cs:u_summary_cpu_models+bx]
.done:
    ret
.pentium:
    mov si, u_summary_pentium
    and ax, 0x3FF0             ; Intel type1/family5/model3, either P24T stepping.
    cmp ax, 0x1530
    jne .done
    mov si, u_summary_p24t
    ret
u_summary_cpu_models dw u_summary_dx,u_summary_dx,u_summary_sx,u_summary_dx2
    dw u_summary_sl,u_summary_sx2,u_summary_486,u_summary_dx2
    dw u_summary_dx4,u_summary_dx4,u_summary_486,u_summary_486
    dw u_summary_486,u_summary_486,u_summary_486,u_summary_486
u_summary_486 db '486',0
u_summary_unknown db 'Unknown',0
u_summary_dx db '486DX',0
u_summary_sx db '486SX',0
u_summary_dx2 db '486DX2',0
u_summary_sx2 db '486SX2',0
u_summary_sl db '486SL',0
u_summary_dx4 db '486DX4',0
u_summary_pentium db 'Pentium',0
u_summary_p24t db 'Pentium P24T',0
u_summary_processor db 'Processor',0
u_summary_fpu db 'FPU',0
u_summary_banks db 'Memory Banks',0
u_summary_interleaved db ', Interleaved',0
u_summary_recovery db 'RAM recovered',0
u_summary_mb db ' MB',0
u_summary_pio db ' PIO',0

setup_hex8:
    push ax
    push bx
    mov bl, al
    shr al, 4
    call .digit
    mov al, bl
    and al, 15
    call .digit
    pop bx
    pop ax
    ret
.digit:
    cmp al, 10
    sbb al, 0x69
    das
    mov ah, 7
    push ax
    call setup_color
    stosw
    pop ax
    ret

; EAX=value, CL=hex digit count1..8, BH=logical color, ES:DI=position.
; Like setup_text, preserve caller registers and destination position.
setup_hex_number:
    pushad
    movzx edx, cl
    mov ebp, eax
    mov cl, 8
    sub cl, dl
    shl cl, 2
    shl ebp, cl
    mov ecx, edx
.digit:
    rol ebp, 4
    mov eax, ebp
    and al, 15
    cmp al, 10
    jb .decimal
    add al, 'A'-10
    jmp .write
.decimal:
    add al, '0'
.write:
    mov ah, bh
    call setup_color
    stosw
    loop .digit
    popad
    ret

setup_restore_text:
    push fs
    push gs
    mov byte [fs:U_THEME_ACTIVE], 0
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ax, 0x1202
    mov bl, 0x30
    int 0x10
    mov ax, 0x0003           ; Restore retained 80x25 / 8x16 font before boot.
    int 0x10
    mov ax, 0x1114
    xor bx, bx
    int 0x10
    mov ax, 0x1003
    mov bx, 1              ; Restore normal POST/OS text blink behavior.
    int 0x10
    mov ax,0x0500
    int 0x10
    pop gs
    pop fs
    cld
    ret

; AH selects Left/Right. Non-clock edits stay in the draft, not active state.
setup_change:
    cmp byte [fs:U_PAGE], 0
    jne .non_clock
    xor byte [fs:U_CLOCK24], 1
    ret
.non_clock:
    cmp byte [fs:U_PAGE], 5
    je chipset_ui_change
    cmp byte [fs:U_PAGE], 3
    je ports_ui_change
    mov dl, 1
    cmp ah, 0x4B
    jne .field
    mov dl, -1
.field:
    mov bx, U_TYPES
    mov cl, [fs:U_FIELD]
    mov ch, 5
    cmp byte [fs:U_PAGE], 1
    jne .boot
    cmp cl, 2
    jae .hdd
    mov al, [fs:bx]
    test cl, cl
    jnz .low
    shr al, 4
.low:
    and al, 15
    call .cycle
    test cl, cl
    jnz .b
    shl al, 4
    and byte [fs:bx], 15
    or [fs:bx], al
    ret
.b:
    and byte [fs:bx], 0xF0
    or [fs:bx], al
    ret
.hdd:
    cmp cl, BOARD_ATA_DEVICE_COUNT+4
    jne .fdc
    mov bx, U_SWAP
    mov ch, 1
    jmp .enum
.fdc:
    cmp cl, BOARD_ATA_DEVICE_COUNT+3
    jne .ide
    mov bx, U_PORTS+P_FLOPPY
    mov ch, 1
    jmp .enum
.ide:
    cmp cl, BOARD_ATA_DEVICE_COUNT+2
    jne .device_policy
    mov bx, U_IDE
    mov ch, 1
    jmp .enum
.device_policy:
    mov al,cl
    sub al,2
    call ide_ui_enable_index
.hdd_limit:
    mov ch, 1
    jmp .enum
.boot:
    push dx
    call setup_boot_parameters
    pop dx
    mov ch, cl
    dec ch
.enum:
    mov al, [fs:bx]
.candidate:
    call .cycle
    call setup_boot_choice_valid
    jc .candidate
    call setup_enum_store
    ret
.cycle:
    add al, dl
    cmp al, 0xFF
    jne .upper
    mov al, ch
.upper:
    cmp al, ch
    jbe .done
    xor al, al
.done:
    ret

setup_enum_store:
    pushf
    pushad
    cmp byte [fs:U_PAGE],1
    jne .boot
    cmp byte [fs:U_IDE_DEVICE],BOARD_ATA_DEVICE_COUNT-1
    ja .boot
    popad
    popf
    jmp ide_ui_store
.boot:
%ifdef BOARD_PORTS_SETUP_COMMIT
    cmp byte [fs:U_PAGE],3
    jne .ordinary_store
    popad
    popf
    jmp BOARD_PORTS_SETUP_COMMIT
.ordinary_store:
%endif
    cmp byte [fs:U_PAGE], 2
    jne .store
    cmp byte [fs:U_FIELD], 4
    jae .store
    test al, al
    jz .store
    movzx dx, byte [fs:U_FIELD]
    xor di, di
.find:
    mov si, di
    shl si, 1
    mov si, [cs:u_boot_pointers+si]
    cmp al, [fs:si]
    je .move
    inc di
    cmp di, 4
    jb .find
    jmp .store
.move:
    mov si, di
    shl si, 1
    mov si, [cs:u_boot_pointers+si]
    cmp di, dx
    je .store
    jb .left
    dec di
    jmp .copy
.left:
    inc di
.copy:
    mov bx, di
    shl bx, 1
    mov bx, [cs:u_boot_pointers+bx]
    mov ah, [fs:bx]
    mov [fs:si], ah
    jmp .move
.store:
    popad
    popf
    mov [fs:bx], al
    ret

; All saved boot targets share the existing enum popup and quick-change path.
setup_boot_parameters:
    movzx bx, byte [fs:U_FIELD]
    shl bx, 1
    mov bx, [cs:u_boot_pointers + bx]
    mov si, u_boot_values
    mov cx, 5
    cmp byte [fs:U_FIELD], 4
    jb .done
    mov si, u_seek_values
    mov cx, 2
    cmp byte [fs:U_FIELD], 6
    jne .done
    mov si, u_halt_values
    mov cx, 3
.done:
    ret

; Allocated targets remain selectable; setup_enum_store moves their slots.
setup_boot_choice_valid:
    clc
    ret

; Enter opens the complete enum. Arrows still offer the normal quick change.
setup_choices:
    cmp byte [fs:U_PAGE], 5
    je chipset_ui_choices
    cmp byte [fs:U_PAGE], 3
    je ports_ui_choices
    pushad
    cmp byte [fs:U_PAGE], 0
    jne .non_clock
    mov bx, U_CLOCK24
    mov si, u_clock_formats
    mov cx, 2
    jmp .enum
.non_clock:
    mov bx, U_TYPES
    mov si, u_floppies
    mov cx, 6
    mov dl, [fs:U_FIELD]
    cmp byte [fs:U_PAGE], 1
    jne .boot
    cmp dl, 2
    jb .value
    cmp dl, BOARD_ATA_DEVICE_COUNT+4
    jne .fdc
    mov bx, U_SWAP
    mov si, u_seek_values
    mov cx, 2
    jmp .enum
.fdc:
    cmp dl, BOARD_ATA_DEVICE_COUNT+3
    jne .ide
    mov bx, U_PORTS+P_FLOPPY
    mov si, u_seek_values
    mov cx, 2
    jmp .enum
.ide:
    cmp dl, BOARD_ATA_DEVICE_COUNT+2
    jne .device_policy
    mov bx, U_IDE
    mov si, u_seek_values
    mov cx, 2
    jmp .enum
.device_policy:
    mov al,dl
    sub al,2
    call ide_ui_enable_index
.hdd:
    mov si, u_hdd_values
    mov cx, 2
    jmp .enum
.boot:
    call setup_boot_parameters
.enum:
    mov dl, 2
.value:
    mov al, [fs:bx]
    cmp dl, 2
    je .selected
    test dl, dl
    jnz .low
    shr al, 4
.low:
    and al, 15
.selected:
    movzx bp, al
.draw:
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_draw
    call chipset_ui_choice_draw
    jc .wait
.ordinary_draw:
    call setup_modal_footer
    pushad
    mov di, 8 * 160 + UI_POPUP_COL * 2
    mov ax, 0x1E20
    mov dx, 15
.clear:
    mov cx, UI_POPUP_WIDTH
    push ax
    call setup_color
    rep stosw
    pop ax
    add di, (80 - UI_POPUP_WIDTH) * 2
    dec dx
    jnz .clear
    ui_text 8, UI_POPUP_TEXT, u_choices, 0x1B
    popad
    pushad
    xor dx, dx
.item:
    mov di, dx
    add di, 10
    imul di, di, 160
    add di, UI_POPUP_TEXT * 2
    push bx
    mov bx, dx
    shl bx, 1
    push si
    mov si, [si + bx]
    mov bh, 0x17
    cmp dx, bp
    jne .text
    mov bh, 0x70
.text:
    push ax
    mov ax, dx
    call setup_boot_choice_valid
    jnc .choice_color
    mov bh, 0x18
.choice_color:
    pop ax
    call setup_choice_highlight
    call setup_text
    pop si
    pop bx
    inc dx
    cmp dx, cx
    jb .item
    ui_text 22, UI_POPUP_TEXT, u_choices_keys, 0x1B
    popad
.wait:
%ifdef EMULATOR_CHIPSET_TEST
    call chipset_test_capture_drain
%endif
    call setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait
.key:
    xor ah, ah
    int 0x16
    cmp al, 27
    je .done
    cmp al, 13
    je .apply
    cmp ah, 0x3B
    jne .arrows
    call setup_help
    pushad
    call setup_draw
    popad
    jmp .draw
.arrows:
    cmp ah, 0x48
    je .previous
    cmp ah, 0x4B
    je .previous
    cmp ah, 0x50
    je .next
    cmp ah, 0x4D
    jne .wait
.next:
    inc bp
    cmp bp, cx
    jb .choice_check
    xor bp, bp
    jmp .choice_check
.previous:
    test bp, bp
    jnz .decrement
    mov bp, cx
.decrement:
    dec bp
.choice_check:
    push ax
    mov ax, bp
    call setup_boot_choice_valid
    pop ax
    jc .skip_choice
    cmp byte [fs:U_PAGE], 3
    jne .draw
    push ax
    mov ax, bp
    call ports_ui_choice_valid
    pop ax
    jnc .draw
.skip_choice:
    cmp ah, 0x48
    je .previous
    cmp ah, 0x4B
    je .previous
    jmp .next
.apply:
    mov ax, bp
    call setup_boot_choice_valid
    jc .wait
    cmp dl, 2
    je .store
    test dl, dl
    jnz .b
    shl al, 4
    and byte [fs:bx], 15
    or [fs:bx], al
    jmp .done
.b:
    and byte [fs:bx], 0xF0
    or [fs:bx], al
    jmp .done
.store:
    call setup_enum_store
    cmp byte [fs:U_PAGE], 5
    jne .done
    call chipset_ui_commit
.done:
    popad
    ret

; AH logical attribute, AL glyph, DI byte offset. Only AH changes; flags retained.
; CS lookup works for shared consumers whose DS points at the BDA.
setup_color:
    pushf
    cmp byte [fs:U_THEME_ACTIVE], 1
    jne .done
    push bx
    push dx
    mov dl, al
    xor bx, bx
    ; Selected field labels discard the highlight background before mapping.
    cmp ah, 0x0F
    jne .find
    cmp byte [fs:U_THEME], 0
    je .restore
    mov ah, 0x07
.find:
    cmp ah, [cs:setup_color_keys + bx]
    je .role
    inc bx
    cmp bl, 10
    jb .find
    jmp .restore
.role:
    cmp di, 24 * 160
    jb .header
    mov bl, 12
    jmp .lookup
.header:
    cmp di, 2 * 160
    jae .border
    cmp ah, 0x1F
    jne .detail
    mov bl, 10
    jmp .lookup
.detail:
    cmp ah, 0x1B
    jne .lookup
    mov bl, 11
    jmp .lookup
.border:
    cmp ah, 0x0B
    jne .lookup
    cmp dl, 0xB3
    jb .lookup
    cmp dl, 0xDA
    ja .lookup
    mov bl, 13
.lookup:
    movzx dx, byte [fs:U_THEME]
    cmp dx, THEME_COUNT
    jb .bounded_theme
    xor dx, dx
.bounded_theme:
    imul dx, 14
    add bx, dx
    mov ah, [cs:setup_colors + bx]
.restore:
    pop dx
    pop bx
.done:
    popf
    ret
setup_color_keys db 0x07,0x08,0x0B,0x0C,0x0E,0x1F,0x17,0x70,0x1B,0x1E
; Body, locked, accent, error, warning, selected, popup, cursor, panel accent,
; panel text, header title, header detail, footer, border.
setup_colors:
    db 0x07,0x08,0x0B,0x0C,0x0E,0x1F,0x17,0x70,0x1B,0x1F,0x1F,0x1B,0x0B,0x0B ; Current
    db 0x1F,0x18,0x1E,0x1C,0x1E,0xE1,0x1F,0xE1,0x1E,0x1F,0x1F,0x1F,0x1F,0x1F ; Award Blue
    db 0x70,0x78,0x71,0x74,0x74,0x1F,0x70,0x1F,0x71,0x70,0x30,0x31,0x30,0x70 ; Award Gray
    db 0x1F,0x18,0x1F,0x1C,0x1E,0x5F,0x1F,0x5F,0x1F,0x1F,0x1F,0x1F,0x1F,0x1D ; AMI Purple
    db 0x1F,0x18,0x1B,0x1C,0x1E,0x30,0x1F,0x30,0x1B,0x1F,0x1B,0x1B,0x1B,0x1B ; AMI Teal
    db 0x57,0x58,0x5F,0x5C,0x5E,0x70,0x67,0x70,0x6F,0x67,0x2F,0x2F,0x20,0x2A ; AMI Classic
    db 0x0E,0x08,0x0E,0x0E,0x0E,0xE0,0x0E,0xE0,0x0E,0x0E,0x0E,0x0E,0x0E,0x0E ; Monochrome Amber
    db 0x0F,0x08,0x0F,0x0F,0x0F,0x70,0x0F,0x70,0x0F,0x0F,0x0F,0x0F,0x0F,0x0F ; Black and White
    db 0x0E,0x08,0x0E,0x0C,0x0F,0x30,0x1E,0x30,0x1E,0x1E,0x1E,0x1E,0x0E,0x0E ; High Contrast
THEME_COUNT equ ($ - setup_colors) / 14

; Hide main-loop function hints while a modal owner consumes the keys.
setup_modal_footer:
    pushad
    mov di, 24 * 160
    mov ax, 0x0B20
    call setup_color
    mov cx, 80
    rep stosw
    popad
    ret

setup_text:
    push ax
    push si
    push di
.next:
    lodsb
    test al, al
    jz .done
    mov ah, bh
    push ax
    call setup_color
    stosw
    pop ax
    jmp .next
.done:
    pop di
    pop si
    pop ax
    ret

setup_value:
    push ax
    push si
    push di
.next:
    mov al, [fs:si]
    inc si
    test al, al
    jz .done
    mov ah, bh
    push ax
    call setup_color
    stosw
    pop ax
    jmp .next
.done:
    pop di
    pop si
    pop ax
    ret

setup_number:
    pushad
    xor cx, cx
    mov ebx, 10
.digit:
    xor edx, edx
    div ebx
    push dx
    inc cx
    test eax, eax
    jnz .digit
.write:
    pop ax
    add al, '0'
    mov ah, 7
    push ax
    call setup_color
    stosw
    pop ax
    loop .write
    popad
    ret

setup_draw:
    mov di, 0
    mov ax, 0x0720
    mov cx, 2000
    push ax
    call setup_color
    rep stosw
    pop ax
    ; Cyan frame, compact sidebar, and blue masthead follow the concept.
    mov di, 0
    mov ax, 0x1F20
    mov cx, 80 * 2
    push ax
    call setup_color
    rep stosw
    pop ax
    mov bx, 0x0B00
    mov cx, 80
    mov di, 2 * 160
    mov ax, 0x0BCD
    push ax
    call setup_color
    rep stosw
    pop ax
    mov di, 23 * 160
    mov cx, 80
    push ax
    call setup_color
    rep stosw
    pop ax
    mov di, 3 * 160 + 20 * 2
    mov cx, 20
    mov ax, 0x0BB3
.vertical:
    push ax
    call setup_color
    mov [es:di], ax
    pop ax
    add di, 160
    loop .vertical
    mov di, 2 * 160 + 20 * 2
    mov ax, 0x0BD1
    call setup_color
    mov [es:di], ax
    mov di, 23 * 160 + 20 * 2
    mov ax, 0x0BCF
    call setup_color
    mov [es:di], ax
    ui_text 0, 3, u_platform, 0x1B
    ui_text 0, 34, u_title, 0x1F
    call post_processor_name
    mov di, 1 * 160 + 3 * 2
    mov bh, 0x1B
    call setup_text
    ui_text 0, 58, u_version, 0x1B
    ui_text 0, 72, bios_version, 0x1B
    ui_text 1, 58, u_build, 0x1B
    mov di, 1 * 160 + 69 * 2
    mov si, 0xFFF5
    mov cx, 8
.build_date:
    lodsb
    mov ah, 0x1B
    push ax
    call setup_color
    stosw
    pop ax
    loop .build_date
    ui_text 3, 2, u_menu, 0x0B
    ui_text 5, 2, u_standard, 0x07
    ui_text 6, 2, u_drives, 0x07
    ui_text 7, 2, u_boot, 0x07
    ui_text 8, 2, u_devices, 0x07
    ui_text 9, 2, u_chip_menu, 0x07
    ui_text 10, 2, u_exit, 0x07
    movzx ax, byte [fs:U_PAGE]
    cmp al, 4
    jb .sidebar_row
    xor al, 1
.sidebar_row:
    add ax, 5
    imul di, ax, 160
    add di, 2 * 2
    mov bx, ax
    mov si, u_standard
    cmp byte [fs:U_PAGE], 0
    je .sidebar
    mov si, u_drives
    cmp byte [fs:U_PAGE], 1
    je .sidebar
    mov si, u_boot
    cmp byte [fs:U_PAGE], 2
    je .sidebar
    mov si, u_devices
    cmp byte [fs:U_PAGE], 3
    je .sidebar
    mov si, u_exit
    cmp byte [fs:U_PAGE], 4
    je .sidebar
    mov si, u_chip_menu
.sidebar:
    mov bh, 0x1F
    cmp byte [fs:U_FOCUS], 0
    je .highlight
    mov bh, 0x0B
.highlight:
    call setup_text
    cmp byte [fs:U_FOCUS], 0
    jne .footer
    pushad
    sub di, 2
    mov cx, 18
    mov dx, 1
    call setup_selection_bar
    popad
.footer:
    cmp byte [fs:U_THEME], 0
    je .footer_ready
    mov di, 24 * 160
    mov ax, 0x0B20
    call setup_color
    mov cx, 80
    rep stosw
.footer_ready:
    mov si, u_footer
    cmp byte [fs:U_EDIT], 0
    je .footer_text
    mov si, u_edit_footer
    cmp byte [fs:U_EDIT], 2
    jne .footer_text
    cmp byte [fs:U_CLOCK24], 0
    jne .footer_text
    mov si, u_time_footer
.footer_text:
    mov di, 24 * 160 + 2 * 2
    mov bh, 0x0B
    call setup_text
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_page
    call chipset_ui_draw
    jmp .done
.ordinary_page:
    cmp byte [fs:U_PAGE], 1
    je .drives
    cmp byte [fs:U_PAGE], 2
    je .boot
    cmp byte [fs:U_PAGE], 3
    je .devices
    cmp byte [fs:U_PAGE], 4
    je .exit_page
    ui_text 3, 23, u_standard_title, 0x0B
    ui_text 5, UI_LABEL_COL, u_date, 0x07
    ui_text 6, UI_LABEL_COL, u_time, 0x07
    ui_text 7, UI_LABEL_COL, u_clock_format, 0x07
    movzx bx, byte [fs:U_CLOCK24]
    shl bx, 1
    mov si, [u_clock_formats + bx]
    mov di, 7 * 160 + UI_VALUE_COL * 2
    mov bh, 7
    call setup_text
    ui_text 9, UI_LABEL_COL, u_total, 0x07
    memory_extended_kib eax
    add eax, 1024
    mov di, 9 * 160 + UI_VALUE_COL * 2
    call setup_number
    ui_text 9, 59, u_kb, 0x07
    ui_text 10, UI_LABEL_COL, u_base, 0x07
    push es
    xor ax, ax
    mov es, ax
    movzx eax, word [es:0x0413]
    pop es
    mov di, 10 * 160 + UI_VALUE_COL * 2
    call setup_number
    ui_text 10, 59, u_kb, 0x07
    ui_text 11, UI_LABEL_COL, u_extended, 0x07
    memory_extended_kib eax
    mov di, 11 * 160 + UI_VALUE_COL * 2
    call setup_number
    ui_text 11, 59, u_kb, 0x07
    cmp byte [fs:U_EDIT], 0
    je .done
    mov si, U_BUFFER
    mov di, 19 * 160 + 24 * 2
    mov bh, 0x1E
    call setup_value
    movzx bx, byte [fs:U_POSITION]
    shl bx, 1
    push di
    add di, bx
    mov ax, 0x7020
    call setup_color
    mov [es:di + 1], ah
    pop di
    jmp .done
.drives:
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .channel
    call ide_ui_draw
    jmp .done
.channel:
    ui_text 3, 23, u_drives_title, 0x0B
    ui_text 5, UI_LABEL_COL, u_drive_a, 0x07
    mov al, [fs:U_TYPES]
    shr al, 4
    call .floppy
    mov di, 5 * 160 + UI_VALUE_COL * 2
    xor cl, cl
    call setup_field_color
    call setup_text
    ui_text 6, UI_LABEL_COL, u_drive_b, 0x07
    mov al, [fs:U_TYPES]
    and al, 15
    call .floppy
    mov di, 6 * 160 + UI_VALUE_COL * 2
    mov cl, 1
    call setup_field_color
    call setup_text
    xor bp,bp
.ide_policy:
    mov bx,bp
    shl bx,1
    mov si,[cs:u_ide_policy_labels+bx]
    mov di,bp
    add di,8
    imul di,160
    push di
    add di,UI_LABEL_COL*2
    mov cx,bp
    add cl,2
    call setup_field_color
    and bh,0x0F
    call setup_text
    pop di
    add di,UI_VALUE_COL*2
    mov cx,bp
    add cl,2
    call setup_field_color
    push bx
    mov ax,bp
    call ide_ui_enable_index
    cmp byte [fs:bx],0
    je .ide_disabled
    mov bx,bp
    imul bx,IDE_RECORD_SIZE
    mov al,[fs:U_IDE+1+bx+IDE_TYPE]
    pop bx
    call ide_ui_type_text
    jmp .ide_arrow
.ide_disabled:
    pop bx
    mov si,u_ide_none
    call setup_text
.ide_arrow:
    call setup_submenu_arrow
    inc bp
    cmp bp,BOARD_ATA_DEVICE_COUNT
    jb .ide_policy
.controller:
    ui_text BOARD_ATA_DEVICE_COUNT+9, UI_LABEL_COL, u_ide_controller, 0x07
    movzx bx, byte [fs:U_IDE]
    shl bx, 1
    mov si, [u_seek_values + bx]
    mov di, (BOARD_ATA_DEVICE_COUNT+9) * 160 + UI_VALUE_COL * 2
    mov cl, BOARD_ATA_DEVICE_COUNT+2
    call setup_field_color
    call setup_text
    ui_text BOARD_ATA_DEVICE_COUNT+10, UI_LABEL_COL, u_fdc, 0x07
    movzx bx, byte [fs:U_PORTS+P_FLOPPY]
    shl bx, 1
    mov si, [u_seek_values + bx]
    mov di, (BOARD_ATA_DEVICE_COUNT+10) * 160 + UI_VALUE_COL * 2
    mov cl, BOARD_ATA_DEVICE_COUNT+3
    call setup_field_color
    call setup_text
    ui_text BOARD_ATA_DEVICE_COUNT+11, UI_LABEL_COL, u_swap, 0x07
    movzx bx, byte [fs:U_SWAP]
    shl bx, 1
    mov si, [u_seek_values + bx]
    mov di, (BOARD_ATA_DEVICE_COUNT+11) * 160 + UI_VALUE_COL * 2
    mov cl, BOARD_ATA_DEVICE_COUNT+4
    call setup_field_color
    call setup_text
    jmp .done
.floppy:
    movzx bx, al
    shl bx, 1
    mov si, [u_floppies + bx]
    ret
.exit_page:
    ui_text 3, 23, u_exit_title, 0x0B
    mov si, u_save
    mov di, 5 * 160 + 24 * 2
    xor cl, cl
    call setup_field_color
    call setup_text
    mov si, u_discard
    mov di, 6 * 160 + 24 * 2
    mov cl, 1
    call setup_field_color
    call setup_text
    jmp .done
.devices:
%ifdef BOARD_PORTS_SETUP_DRAW
    call BOARD_PORTS_SETUP_DRAW
%else
%ifdef BOARD_PORTS_NOTE1
    ui_text 5,UI_LABEL_COL,BOARD_PORTS_NOTE1,7
    ui_text 6,UI_LABEL_COL,BOARD_PORTS_NOTE2,7
%endif
    call ports_ui_draw
%endif
    jmp .done
.boot:
    ui_text 3, 23, u_boot_title, 0x0B
    xor bp, bp
.boot_field:
    mov bx, bp
    shl bx, 1
    mov si, [u_boot_labels + bx]
    mov di, bp
    movzx di, byte [cs:u_boot_rows + di]
    imul di, 160
    add di, UI_LABEL_COL * 2
    mov bh, 7
    call setup_text
    add di, (UI_VALUE_COL - UI_LABEL_COL) * 2
    mov bx, bp
    shl bx, 1
    mov bx, [u_boot_pointers + bx]
    movzx bx, byte [fs:bx]
    shl bx, 1
    mov si, [u_boot_values + bx]
    cmp bp, 4
    jb .boot_value
    mov si, [u_seek_values + bx]
    cmp bp, 6
    jne .boot_value
    mov si, [u_halt_values + bx]
.boot_value:
    mov cx, bp
    call setup_field_color
    call setup_text
    inc bp
    cmp bp, BOOT_FIELD_COUNT
    jb .boot_field
.done:
    call setup_field_highlight
    ret

; Color whole cells, including spaces, without changing their characters.
; DI=top-left, CX=width, DX=height, BH=attribute. Preserve every caller register.
setup_selection_bar:
    pushad
    mov bp, cx
.row:
    mov cx, bp
.cell:
    mov ah, bh
    mov al, ' '
    call setup_color
    mov [es:di + 1], ah
    add di, 2
    loop .cell
    add di, 160
    mov ax, bp
    shl ax, 1
    sub di, ax
    dec dx
    jnz .row
    popad
    ret

setup_choice_highlight:
    cmp bh, 0x70
    jne .done
    pushad
    sub di, 2
    mov cx, UI_POPUP_WIDTH - 2
    mov dx, 1
    call setup_selection_bar
    popad
.done:
    ret

setup_field_highlight:
    pushad
    cmp byte [fs:U_FOCUS], 1
    jne .done
    mov cl, [fs:U_FIELD]
    call setup_field_available
    jc .done
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_highlight
    call chipset_ui_row
    imul di, 160
    add di, (UI_VALUE_COL - 1) * 2
    mov cx, UI_VALUE_WIDTH + 2
    jmp .paint
.ordinary_highlight:
    movzx bx, cl
    mov si, u_clock_rows
    cmp byte [fs:U_PAGE], 0
    je .value
    mov si, u_drive_rows
    cmp byte [fs:U_PAGE], 1
    jne .boot
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .value
    mov si, u_ide_rows
    jmp .value
.boot:
    mov si, u_boot_rows
    cmp byte [fs:U_PAGE], 2
    je .value
    mov si, u_ports_rows
    cmp byte [fs:U_PAGE], 3
    je .value
    mov si, u_exit_rows
    movzx di, byte [cs:si + bx]
    imul di, 160
    add di, (UI_LABEL_COL - 1) * 2
    mov cx, UI_POPUP_WIDTH + 1
    jmp .paint
.value:
    movzx di, byte [cs:si + bx]
    imul di, 160
    add di, (UI_VALUE_COL - 1) * 2
    mov cx, UI_VALUE_WIDTH + 2
.paint:
    mov dx, 1
    mov bh, 0x1F
    call setup_selection_bar
.done:
    popad
    ret

u_clock_rows db 5,6,7
u_drive_rows db 5,6
%assign ide_row 8
%rep BOARD_ATA_DEVICE_COUNT
    db ide_row
%assign ide_row ide_row+1
%endrep
    db BOARD_ATA_DEVICE_COUNT+9,BOARD_ATA_DEVICE_COUNT+10,BOARD_ATA_DEVICE_COUNT+11
u_boot_rows db 5,6,7,8,9,10,11
%ifdef BOARD_FAST_BOOT_SETTING
    db 12
%endif
u_boot_pointers dw U_BOOT,U_BOOT_SECOND,U_BOOT_THIRD,U_BOOT_FOURTH,U_SEEK,U_NUMLOCK,U_HALT
%ifdef BOARD_FAST_BOOT_SETTING
    dw U_CHIP+(BOARD_FAST_BOOT_SETTING-C_CHIP)
%endif
BOOT_FIELD_COUNT equ ($-u_boot_pointers)/2
u_boot_labels dw u_boot_order,u_boot_second,u_boot_third,u_boot_fourth,u_seek,u_numlock,u_halt
%ifdef BOARD_FAST_BOOT_SETTING
    dw u_fast_boot
%endif
u_ide_rows db 5,6,7,8,9,10,11,14,15,16
%ifdef BOARD_IDE_32BIT_POLICY
    db 17
%endif
%ifdef BOARD_ATA_PIO_POLICY
    db 18
%endif
u_exit_rows db 5,6

; Append the retained VGA font's right arrow after the complete value.
; A single internal space in Type/User labels must not end the scan.
setup_submenu_arrow:
    pushad
    mov cx, UI_VALUE_WIDTH - 1
.scan:
    cmp byte [es:di], ' '
    jne .next
    cmp byte [es:di + 2], ' '
    je .arrow
.next:
    add di, 2
    loop .scan
    jmp .done
.arrow:
    mov al, 0x1A
    mov ah, bh
    push di
    add di, 2
    call setup_color
    mov [es:di], ax
    pop di
.done:
    popad
    ret

setup_field_color:
    mov bh, 7
    call setup_field_available
    jnc .enabled
    mov bh, 8
    ret
.enabled:
    cmp byte [fs:U_FOCUS], 1
    jne .done
    cmp [fs:U_FIELD], cl
    jne .done
    mov bh, 0x1F
.done:
    ret

; CL=field. Carry means unavailable. Drawing and input share this rule.
setup_field_available:
    pushad
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_available
    call chipset_ui_available
    jc .unavailable
    jmp .available
.ordinary_available:
    cmp byte [fs:U_PAGE], 3
    je .ports
    cmp byte [fs:U_PAGE], 1
    jne .available
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    jbe .device
    cmp cl, 2
    jb .available
    cmp cl, BOARD_ATA_DEVICE_COUNT+1
    ja .available
%if BOARD_ATA_DEVICE_COUNT = 2
    cmp byte [fs:U_IDE], 0
    je .unavailable
%endif
    jmp .available
.device:
    cmp cl, 1                     ; None must still allow a new disk type.
    jbe .available
    call ide_ui_enable_pointer
    cmp byte [fs:bx], 0
    je .unavailable
    cmp cl, 2
    jb .available
    cmp cl, 6
    ja .available
    call ide_ui_record
    cmp byte [fs:bx + IDE_TYPE], 48
    jne .unavailable
    jmp .available
.ports:
    call ports_ui_available
    jc .unavailable
    jmp .available
.available:
    popad
    clc
    ret
.unavailable:
    popad
    stc
    ret

; F1 follows the selected page or clock field, including a pending edit.
setup_help:
    pushad
    call setup_modal_footer
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_help
    call chipset_ui_help
    jmp .wait
.ordinary_help:
    mov di, 17 * 160 + 23 * 2
    mov dx, 6
    mov ax, 0x1E20
.clear:
    mov cx, 55
    push ax
    call setup_color
    rep stosw
    pop ax
    add di, (80 - 55) * 2
    dec dx
    jnz .clear
%ifdef BOARD_PORTS_SETUP_HELP
    cmp byte [fs:U_PAGE],3
    jne .ordinary_port_help
    call BOARD_PORTS_SETUP_HELP
    jmp .wait
.ordinary_port_help:
%endif
    movzx bx, byte [fs:U_PAGE]
    cmp bx, 3
    jne .old_help
    mov bx, 25
    cmp byte [fs:U_FOCUS], 0
    je .topic
    movzx bx, byte [fs:U_FIELD]
    add bx, 26
    jmp .topic
.old_help:
    cmp bx, 4
    jne .old_help_page
    mov bx, 3
.old_help_page:
    cmp bx, 1
    jne .normal_help
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .channel_help
%ifdef BOARD_IDE_32BIT_POLICY
    cmp byte [fs:U_FIELD],10
    jne .ordinary_ide_help
    mov bx,IDE_DWORD_HELP_TOPIC
    jmp .topic
.ordinary_ide_help:
%endif
%ifdef BOARD_ATA_PIO_POLICY
    cmp byte [fs:U_FIELD],11
    jne .ordinary_pio_help
    mov bx,IDE_PIO_HELP_TOPIC
    jmp .topic
.ordinary_pio_help:
%endif
    movzx bx, byte [fs:U_FIELD]
    add bx, 14
    jmp .topic
.channel_help:
    cmp byte [fs:U_FIELD], BOARD_ATA_DEVICE_COUNT+4
    jne .channel_existing
    mov bx, 35
    jmp .topic
.channel_existing:
    cmp byte [fs:U_FOCUS], 1
    jne .normal_help
    mov al,[fs:U_FIELD]
    sub al,2
    cmp al,BOARD_ATA_DEVICE_COUNT
    jae .channel_controls
    mov bx,8
    jmp .topic
.channel_controls:
    cmp byte [fs:U_FIELD], BOARD_ATA_DEVICE_COUNT+3
    jne .ide_help
    mov bx, 31             ; Existing Floppy Controller topic.
    jmp .topic
.ide_help:
    cmp byte [fs:U_FIELD], BOARD_ATA_DEVICE_COUNT+2
    jne .normal_help
    mov bx, 24
    jmp .topic
.normal_help:
    cmp byte [fs:U_FOCUS], 0
    je .page
    cmp bx, 1
    je .drive_field
    cmp bx, 2
    je .boot_field
    cmp bx, 3
    je .exit_field
    movzx bx, byte [fs:U_FIELD]
    cmp bx, 2
    jne .clock_time_help
    mov bx, 37
    jmp .topic
.clock_time_help:
    cmp bx, 1
    jne .clock_date_help
    cmp byte [fs:U_CLOCK24], 1
    jne .clock_date_help
    mov bx, 38
    jmp .topic
.clock_date_help:
    inc bx
    jmp .topic
.drive_field:
    mov bx, 6
    cmp byte [fs:U_FIELD], 3
    jne .field
    mov bx, 13
    jmp .topic
    jmp .field
.boot_field:
%ifdef BOARD_FAST_BOOT_SETTING
    cmp byte [fs:U_FIELD], 7
    jne .ordinary_boot_help
    mov bx, FAST_BOOT_HELP_TOPIC
    jmp .topic
.ordinary_boot_help:
%endif
    mov bx, 9
    cmp byte [fs:U_FIELD], 4
    jb .topic
    mov bx, 10
    cmp byte [fs:U_FIELD], 4
    je .topic
    mov bx, 34
    cmp byte [fs:U_FIELD], 5
    je .topic
    mov bx, 36
    jmp .topic
.exit_field:
    mov bx, 11
.field:
    movzx ax, byte [fs:U_FIELD]
    add bx, ax
    jmp .topic
.page:
    test bx, bx
    jz .topic
    add bx, 2
.topic:
    imul bx, bx, 6
    mov si, [u_help_topics + bx]
    mov bp, bx
    cmp byte [fs:U_PAGE],1
    jne .boot_title
    cmp byte [fs:U_IDE_DEVICE],BOARD_ATA_DEVICE_COUNT-1
    jbe .help_title
    cmp byte [fs:U_FOCUS],1
    jne .help_title
    movzx ax,byte [fs:U_FIELD]
    sub ax,2
    cmp ax,BOARD_ATA_DEVICE_COUNT
    jae .help_title
    shl ax,1
    push bx
    mov bx,ax
    mov si,[u_ide_policy_labels+bx]
    pop bx
    jmp .help_title
.boot_title:
    cmp byte [fs:U_PAGE], 2
    jne .help_title
    cmp byte [fs:U_FOCUS], 1
    jne .help_title
    movzx ax, byte [fs:U_FIELD]
    cmp ax, 4
    jae .help_title
    shl ax, 1
    push bx
    mov bx, ax
    mov si, [u_boot_labels + bx]
    pop bx
.help_title:
    mov di, 18 * 160 + 25 * 2
    mov bh, 0x1E
    call setup_text
    mov si, [ds:u_help_topics + bp + 2]
    mov di, 19 * 160 + 25 * 2
    call setup_text
    mov si, [ds:u_help_topics + bp + 4]
    mov di, 20 * 160 + 25 * 2
    call setup_text
.wait:
%ifdef EMULATOR_CHIPSET_TEST
    call chipset_test_capture_drain
%endif
    call setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait
.key:
    xor ah, ah
    int 0x16
    cmp al, 27
    je .done
    cmp ah, 0x3B
    jne .wait
.done:
    popad
    ret

setup_pair:
    push ax
    mov ah, al
    shr al, 4
    add al, '0'
    mov [fs:di], al
    inc di
    mov al, ah
    and al, 15
    add al, '0'
    mov [fs:di], al
    inc di
    pop ax
    ret

; Read live RTC on idle iterations. Edit buffer is separate and never touched.
setup_clock:
    pushad
    mov di, U_DATE
    mov ah, 4
    int 0x1A
    jc .bad_date
    and byte [fs:U_CONFIRMED], 0xFD
    mov al, dh
    call setup_pair
    mov byte [fs:di], '/'
    inc di
    mov al, dl
    call setup_pair
    mov byte [fs:di], '/'
    inc di
    mov al, ch
    call setup_pair
    mov al, cl
    call setup_pair
    mov byte [fs:di], 0
    jmp .time
.bad_date:
    test byte [fs:U_CONFIRMED], 2
    jnz .time
    mov dword [fs:U_DATE], '01/0'
    mov dword [fs:U_DATE + 4], '1/19'
    mov word [fs:U_DATE + 8], '80'
    mov byte [fs:U_DATE + 10], 0
.time:
    mov ah, 2
    int 0x1A
    jc .bad_time
    and byte [fs:U_CONFIRMED], 0xFE
    mov [fs:U_DST], dl
    mov [fs:U_HOUR], ch
    mov [fs:U_MINUTE], cl
    mov [fs:U_SECOND], dh
    jmp .display
.bad_time:
    mov al, 0x0B
    call rtc_read
    and al, 1
    mov [fs:U_DST], al
    test byte [fs:U_CONFIRMED], 1
    jnz .display
    mov word [fs:U_HOUR], 0
    mov byte [fs:U_SECOND], 0
.display:
    call setup_format_time
    cmp byte [fs:U_PAGE], 0
    jne .done
    mov si, U_DATE
    mov di, 5 * 160 + 49 * 2
    mov bh, 7
    cmp byte [fs:U_FOCUS], 1
    jne .date
    cmp byte [fs:U_FIELD], 0
    jne .date
    mov bh, 0x1F
.date:
    call setup_value
    mov si, U_TIME
    mov di, 6 * 160 + 49 * 2
    mov bh, 7
    cmp byte [fs:U_FOCUS], 1
    jne .time_field
    cmp byte [fs:U_FIELD], 1
    jne .time_field
    mov bh, 0x1F
.time_field:
    call .clear_suffix
    call setup_value
.done:
    popad
    ret
.clear_suffix:
    push ax
    mov ah, bh
    mov al, ' '
    call setup_color
    ; Shortening24-hour text must also erase the previous AM/PM suffix.
    mov byte [es:di + 16], ' '
    mov byte [es:di + 17], ah
    mov byte [es:di + 18], ' '
    mov byte [es:di + 19], ah
    mov byte [es:di + 20], ' '
    mov byte [es:di + 21], ah
    pop ax
    ret

setup_format_time:
    pushad
    mov di, U_TIME
    mov al, [fs:U_HOUR]
    cmp byte [fs:U_CLOCK24], 1
    je .hour
    test al, al
    jnz .afternoon
    mov al, 0x12
    jmp .hour
.afternoon:
    cmp al, 0x12
    jbe .hour
    sub al, 0x12
    das
.hour:
    call setup_pair
    mov byte [fs:di], ':'
    inc di
    mov al, [fs:U_MINUTE]
    call setup_pair
    mov byte [fs:di], ':'
    inc di
    mov al, [fs:U_SECOND]
    call setup_pair
    cmp byte [fs:U_CLOCK24], 1
    je .end
    mov byte [fs:di], ' '
    inc di
    mov al, 'A'
    cmp byte [fs:U_HOUR], 0x12
    jb .suffix
    mov al, 'P'
.suffix:
    mov [fs:di], al
    inc di
    mov byte [fs:di], 'M'
    inc di
.end:
    mov byte [fs:di], 0
    popad
    ret

setup_edit_begin:
    mov byte [fs:U_POSITION], 0
    mov si, U_DATE
    mov di, U_BUFFER
    mov cx, 11
    mov al, 1
    cmp byte [fs:U_FIELD], 0
    je .copy
    mov si, U_TIME
    mov cx, 12
    mov al, 2
.copy:
    mov [fs:U_EDIT], al
.byte:
    mov al, [fs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    ret

setup_parse_pair:
    mov al, [fs:si]
    sub al, '0'
    shl al, 4
    inc si
    mov ah, [fs:si]
    sub ah, '0'
    or al, ah
    inc si
    ret

setup_edit_apply:
    mov si, U_BUFFER
    call setup_parse_pair
    cmp byte [fs:U_EDIT], 1
    jne .time
    mov dh, al
    inc si
    call setup_parse_pair
    mov dl, al
    inc si
    call setup_parse_pair
    mov ch, al
    call setup_parse_pair
    mov cl, al
    mov ah, 5
    int 0x1A
    jc .done
    mov di, U_DATE
    mov cx, 11
    or byte [fs:U_CONFIRMED], 2
    jmp .copy
.time:
    mov ch, al
    cmp byte [fs:U_CLOCK24], 1
    je .minutes
    cmp al, 1
    jb .invalid
    cmp al, 0x12
    ja .invalid
    cmp al, 0x12
    jne .period
    xor al, al
.period:
    cmp byte [fs:U_BUFFER + 9], 'P'
    jne .converted
    add al, 0x12
    daa
.converted:
    mov ch, al
.minutes:
    inc si
    call setup_parse_pair
    mov cl, al
    inc si
    call setup_parse_pair
    mov dh, al
    mov dl, [fs:U_DST]
    push cx
    push dx
    mov ah, 3
    int 0x1A
    pop dx
    pop cx
    jc .done
    mov [fs:U_HOUR], ch
    mov [fs:U_MINUTE], cl
    mov [fs:U_SECOND], dh
    or byte [fs:U_CONFIRMED], 1
    call setup_format_time
    clc
    ret
.copy:
    ; A valid setter can succeed before the other power-lost domain is repaired.
    ; Keep its confirmed display without relaxing the shared RTC getter policy.
    mov si, U_BUFFER
.byte:
    mov al, [fs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    clc
.done:
    ret
.invalid:
    stc
    ret

setup_confirm:
    call setup_modal_footer
    mov di, 21 * 160 + 23 * 2
    mov bh, 0x1E
    call setup_text
.wait:
    call setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait
.key:
    xor ah, ah
    int 0x16
    cmp al, 13
    je .yes
    cmp al, 'y'
    je .yes
    cmp al, 'Y'
    je .yes
    cmp al, 27
    je .no
    cmp al, 'n'
    je .no
    cmp al, 'N'
    jne .wait
.no:
    stc
    ret
.yes:
    clc
    ret

u_title db 'bAIos Setup',0
u_summary db 'bAIos',0
u_cpu_unknown db 'CPU family/model/speed: Unknown',0
u_fpu db 'Numeric processor',0
u_detected db 'Detected',0
u_capacity_unknown db 'Capacity: Unknown',0
u_rom_disks db 'Option ROM disks',0
u_effective db '(effective)',0
u_warnings db 'POST warnings:',0
u_clock_warning db 'Clock',0
u_floppy_warning db 'Floppy',0
u_settings_warning db 'Settings',0
u_keyboard_warning db 'Keyboard',0
u_rom_warning db 'ROM',0
u_active db 'ACTIVE SETTINGS',0
u_saved db 'CMOS settings',0
u_saved_values dw u_fallback,u_valid
u_fallback db 'Defaults',0
u_valid db 'Valid',0
u_l1 db 'CPU L1 cache',0
u_l2 db 'L2 cache',0
u_l2_missing db 'Not detected',0
u_ram_recovered db 'RAM test failed; chipset defaults loaded.',0
u_clock_unset db 'WARNING: CMOS date/time not set.',13,10,0
u_clock_save_error db 'Clock defaults failed. Entering Setup.',13,10,0
u_cmos_invalid db 'WARNING: CMOS settings invalid.',13,10,0
u_cmos_clock_invalid db 'WARNING: CMOS settings invalid; date/time not set.',13,10,0
u_cmos_recover db 'Enter/D: Load defaults and continue.  Delete: Setup.',13,10,0
u_platform db BOARD_DISPLAY_NAME,0
u_build db 'ROM build:',0
u_menu db 'SETUP MENU',0
u_standard db 'Standard Setup',0
u_drives db 'Drives',0
u_boot db 'Boot',0
u_exit db 'Exit Setup',0
u_standard_title db 'bAIos Setup > Standard Setup',0
u_drives_title db 'bAIos Setup > Drives',0
u_boot_title db 'bAIos Setup > Boot',0
u_exit_title db 'bAIos Setup > Exit Setup',0
u_footer db 'F1 Help   F4/F5 Theme   F9 Defaults   F10 Save',0
u_edit_footer db 'F1 Help   F4/F5 Theme',0
u_time_footer db 'A/P AM/PM   F1 Help   F4/F5 Theme',0
u_version db 'Version:',0
u_clock_format db 'Time Format',0
u_clock_formats dw u_clock12,u_clock24
u_clock12 db '12 Hour',0
u_clock24 db '24 Hour',0
u_choices db 'SELECT VALUE',0
u_choices_keys db 'Arrows Select   Enter Apply   Esc Cancel',0
u_date db 'System Date',0
u_time db 'System Time',0
u_total db 'Total Memory',0
u_base db 'Base Memory',0
u_extended db 'Extended Memory',0
u_mb db 'MB',0
u_kb db 'KB',0
u_slash db '/',0
u_invalid db 'Invalid date or time.',0
u_drive_a db 'Floppy Drive A',0
u_drive_b db 'Floppy Drive B',0
u_hdd_policy db 'Primary IDE Master',0
u_slave_policy db 'Primary IDE Slave',0
u_geometry db 'BIOS C / H / S',0
u_absent db 'Not detected',0
u_boot_order db 'First Boot Device',0
u_boot_second db 'Second Boot Device',0
u_boot_third db 'Third Boot Device',0
u_boot_fourth db 'Fourth Boot Device',0
u_numlock db 'Boot Num Lock',0
u_swap db 'Swap Floppy Drives',0
u_halt db 'Halt On',0
u_keyboard_absent db 'WARNING: Keyboard not detected.',13,10,0
u_seek db 'Floppy Seek',0
u_save db 'Save and Exit',0
u_discard db 'Discard and Exit',0
u_save_error db 'CMOS verification failed. Settings not applied.',0
u_save_trace db 'CMOS reg/expected/read:',0
u_save_confirm db 'Save and restart? Enter/Y = Yes   Esc/N = Cancel',0
u_discard_confirm db 'Discard settings? Enter/Y = Yes   Esc/N = Cancel',0
u_defaults_confirm db 'Load defaults? Enter/Y = Yes   Esc/N = Cancel',0
u_seek_error_a db 'Floppy A seek error.',13,10,0
u_seek_error_b db 'Floppy B seek error.',13,10,0
u_post_continue db 'Press any key to continue or Delete for Setup.',13,10,0
u_help_topics:
    dw u_standard,u_help_standard1,u_help_standard2
    dw u_date,u_help_date1,u_help_date2
    dw u_time,u_help_time1,u_help_time2
    dw u_drives,u_help_drives1,u_help_drives2
    dw u_boot,u_help_boot1,u_help_boot2
    dw u_exit,u_help_exit1,u_help_exit2
    dw u_drive_a,u_help_floppy1,u_help_floppy2
    dw u_drive_b,u_help_floppy1,u_help_floppy2
    dw u_hdd_policy,u_help_hdd1,u_help_hdd2
    dw u_boot_order,u_help_boot1,u_help_boot2
    dw u_seek,u_help_seek1,u_help_seek2
    dw u_save,u_help_save1,u_help_save2
    dw u_discard,u_help_discard1,u_help_discard2
    dw u_slave_policy,u_help_hdd1,u_help_hdd2
    dw u_ide_enabled,u_help_ide_enabled1,u_help_ide_enabled2
    dw u_ide_type,u_help_ide_type1,u_help_ide_type2
    dw u_ide_cyl,u_help_ide_cyl1,u_help_ide_cyl2
    dw u_ide_heads,u_help_ide_heads1,u_help_ide_heads2
    dw u_ide_sectors,u_help_ide_sectors1,u_help_ide_sectors2
    dw u_ide_precomp,u_help_ide_precomp1,u_help_ide_precomp2
    dw u_ide_landing,u_help_ide_landing1,u_help_ide_landing2
    dw u_ide_translation,u_help_ide_translation1,u_help_ide_translation2
    dw u_ide_block,u_help_ide_block1,u_help_ide_block2
    dw u_ide_edd,u_help_ide_edd1,u_help_ide_edd2
    dw u_ide_controller,u_help_ide_controller1,u_help_ide_controller2
    dw u_devices,u_help_devices1,u_help_devices2
    dw u_uart_a,u_help_uart1,u_help_uart2
    dw u_uart_b,u_help_uart1,u_help_uart2
    dw u_uart_pair,u_help_pair1,u_help_pair2
    dw u_parallel,u_help_parallel1,u_help_parallel2
    dw u_parallel_mode,u_help_mode1,u_help_mode2
    dw u_fdc,u_help_fdc1,u_help_fdc2
%ifdef BOARD_MOUSE_HELP1
    dw u_mouse,BOARD_MOUSE_HELP1,BOARD_MOUSE_HELP2
%else
    dw u_mouse,u_help_mouse1,u_help_mouse2
%endif
    dw u_isa,u_help_isa1,u_help_isa2
    dw u_numlock,u_help_num1,u_help_num2
    dw u_swap,u_help_swap1,u_help_swap2
    dw u_halt,u_help_halt1,u_help_halt2
    dw u_clock_format,u_help_format1,u_help_format2
    dw u_time,u_help_time24,u_help_time2
%ifdef BOARD_IDE_32BIT_POLICY
IDE_DWORD_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_ide_dword,u_help_ide_dword1,u_help_ide_dword2
%endif
%ifdef BOARD_ATA_PIO_POLICY
IDE_PIO_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_ide_pio,u_help_ide_pio1,u_help_ide_pio2
%endif
%ifdef BOARD_FAST_BOOT_SETTING
FAST_BOOT_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_fast_boot,u_help_fast1,u_help_fast2
u_fast_boot db 'Fast Boot',0
u_help_fast1 db 'Skip the startup RAM test above 1 MB.',0
u_help_fast2 db 'Off runs the full test and is the default.',0
%endif
%ifdef BOARD_IDE_32BIT_POLICY
u_ide_dword db '32-bit ATA Transfers',0
u_help_ide_dword1 db 'Uses 32-bit data transfers on supported IDE.',0
u_help_ide_dword2 db 'Disabled uses the compatible 16-bit default.',0
%endif
%ifdef BOARD_ATA_PIO_POLICY
u_ide_pio db 'PIO Mode Limit',0
u_help_ide_pio1 db 'Limits IDE speed. Auto selects the fastest safe mode.',0
u_help_ide_pio2 db 'Faster modes need the actual 33 MHz timing clock.',0
u_ide_pio_values dw u_auto,u_ide_pio0,u_ide_pio1,u_ide_pio2,u_ide_pio3,u_ide_pio4
u_ide_pio_choices dw u_ide_pio0,u_ide_pio1,u_ide_pio2,u_ide_pio3,u_ide_pio4,u_auto
u_ide_pio0 db '0',0
u_ide_pio1 db '1',0
u_ide_pio2 db '2',0
u_ide_pio3 db '3',0
u_ide_pio4 db '4',0
ide_ui_pio_value:
    mov cl,[fs:U_IDE_DEVICE]
    shl cl,1
    mov al,[fs:U_CHIP+(BOARD_ATA_PIO_POLICY-C_CHIP)]
    shr al,cl
    and al,3
    shr cl,1
    mov ah,[fs:U_CHIP+(BOARD_ATA_PIO_POLICY_HIGH-C_CHIP)]
    shr ah,cl
    and ah,1
    shl ah,2
    or al,ah
    ret
%endif
u_help_standard1 db 'System date, time, and detected memory.',0
u_help_standard2 db 'Select a clock field to edit it.',0
u_help_date1 db 'Calendar date: 1980-2099.',0
u_help_date2 db 'MM/DD/YYYY. Enter applies the date.',0
u_help_time1 db '12-hour clock. Press A for AM or P for PM.',0
u_help_time2 db 'Enter applies the time; Esc cancels the edit.',0
u_help_time24 db '24-hour clock: 00:00:00 to 23:59:59.',0
u_help_format1 db 'Choose a 12-hour or 24-hour clock display.',0
u_help_format2 db 'This changes how the time appears in Setup.',0
u_help_drives1 db 'Choose the installed drives and their settings.',0
u_help_drives2 db 'Enter opens all choices. Arrows change values.',0
u_help_exit1 db 'Save settings and restart, or discard edits.',0
u_help_exit2 db 'Confirmed clock changes are retained.',0
u_help_floppy1 db 'Select the installed drive type, or None.',0
u_help_floppy2 db 'The type sets drive capacity, not disk capacity.',0
u_help_hdd1 db 'Auto detects hard disks and CD drives at startup.',0
u_help_hdd2 db 'Disabled stops the BIOS from using this drive.',0
u_help_boot1 db 'Choose which device to try at each boot step.',0
u_help_boot2 db 'Other tries boot support on expansion cards.',0
u_help_seek1 db 'Check drives during POST. Default Enabled.',0
u_help_seek2 db 'No disk is needed. Halt On sets error behavior.',0
u_help_save1 db 'Save your settings and restart the computer.',0
u_help_save2 db 'The BIOS checks that your settings were saved.',0
u_help_discard1 db 'Return without saving your setting changes.',0
u_help_discard2 db 'Confirmed clock changes are retained.',0
u_hdd_values dw u_disabled,u_auto
u_boot_values dw u_disabled,u_boot_floppy,u_boot_hdd,u_boot_cd,u_boot_other
u_boot_other db 'Other',0
u_boot_floppy db 'Floppy',0
u_boot_hdd db 'Hard Disk',0
u_boot_cd db 'CD-ROM',0
u_halt_values dw u_halt_all,u_halt_none,u_halt_keyboard
u_halt_all db 'All Errors',0
u_halt_none db 'No Errors',0
u_halt_keyboard db 'All Except Keyboard',0
u_help_num1 db 'Choose whether Num Lock starts enabled.',0
u_help_num2 db 'The keypad and keyboard lamp use this value.',0
u_help_swap1 db 'Swap the names of floppy drives A and B.',0
u_help_swap2 db 'Set each drive type for its original connector.',0
u_help_halt1 db 'Choose which errors pause startup.',0
u_help_halt2 db 'Serious hardware faults always stop startup.',0
u_seek_values dw u_off,u_on
u_off:
u_disabled db 'Disabled',0
u_auto db 'Auto',0
u_a_first db 'A, then HDD',0
u_hdd_first db 'HDD, then A',0
u_hdd_only db 'HDD only',0
u_on db 'Enabled',0
u_floppies dw u_none,u_360,u_1200,u_720,u_1440,u_2880
u_none db 'Not installed',0
u_360 db '360 KB, 5.25 in',0
u_1200 db '1.2 MB, 5.25 in',0
u_720 db '720 KB, 3.5 in',0
u_1440 db '1.44 MB, 3.5 in',0
u_2880 db '2.88 MB, 3.5 in',0

; SI/BX resolve the current physical position's draft, never active state.
ide_ui_record:
    movzx bx, byte [fs:U_IDE_DEVICE]
    imul bx, IDE_RECORD_SIZE
    add bx, U_IDE + 1
    mov si, bx
    ret
ide_ui_enable_pointer:
    push ax
    mov al,[fs:U_IDE_DEVICE]
    call ide_ui_enable_index
    pop ax
    ret
ide_ui_enable_index:
    movzx bx,al
%if BOARD_ATA_DEVICE_COUNT = 4
    cmp bx,2
    jb .base
    add bx,U_IDE+IDE_ENABLE_EXTRA-2
    ret
.base:
%endif
    test bx,bx
    mov bx,U_HDD
    jz .done
    mov bx,U_SLAVE
.done:
    ret

; None is UI-only value49. CMOS keeps the existing enable flag and type0..48.
ide_ui_type_value:
    push bx
    call ide_ui_record
    mov al, [fs:bx + IDE_TYPE]
    call ide_ui_enable_pointer
    cmp byte [fs:bx], 0
    jne .done
    mov al, 49
.done:
    pop bx
    ret

; Enum parameters share the existing popup. Numeric/type forms are bounded.
ide_ui_parameters:
    call ide_ui_record
    mov al, [fs:U_FIELD]
    test al, al
    jz .enabled
    cmp al, 7
    je .translation
    cmp al, 8
    je .block
%ifdef BOARD_ATA_PIO_POLICY
    cmp al,11
    je .pio
%endif
%ifdef BOARD_IDE_32BIT_POLICY
    cmp al,10
    je .dword
%endif
    add bx, IDE_EDD_OFF
    mov al,[fs:bx]
    xor al,1
    mov si, u_seek_values
    mov cx, 2
    jmp .ready
.enabled:
    call ide_ui_enable_pointer
    mov al,[fs:bx]
    mov si, u_seek_values
    mov cx, 2
    jmp .ready
.translation:
    add bx, IDE_TRANSLATION
    movzx bx,byte [fs:bx]
    mov al,[cs:ide_translation_to_display+bx]
    mov si, u_ide_translation_choices
    mov cx, 4
    jmp .ready
.block:
    add bx, IDE_BLOCK
    mov al,[fs:bx]
    cmp al,2
    jb .block_special
    sub al,2
    jmp .block_ready
.block_special:
    add al,7
.block_ready:
    mov si, u_ide_block_choices
    mov cx, 9
    jmp .ready
%ifdef BOARD_IDE_32BIT_POLICY
.dword:
    mov cl,[fs:U_IDE_DEVICE]
    mov al,[fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)]
    shr al,cl
    and al,1
    mov si,u_seek_values
    mov cx,2
    jmp .ready
%endif
%ifdef BOARD_ATA_PIO_POLICY
.pio:
    call ide_ui_pio_value
    test al,al
    jnz .pio_position
    mov al,6
.pio_position:
    dec al
    mov si,u_ide_pio_choices
    mov cx,6
%endif
.ready:
    mov bx,U_CHIP_VALUE
    mov [fs:bx],al
    ret

; AL is a display position. The saved record retains its existing encodings.
ide_ui_store:
    pushf
    pushad
    mov dl,al
    call ide_ui_record
    cmp byte [fs:U_FIELD],0
    je .enabled
    cmp byte [fs:U_FIELD],7
    je .translation
    cmp byte [fs:U_FIELD],8
    je .block
%ifdef BOARD_ATA_PIO_POLICY
    cmp byte [fs:U_FIELD],11
    je .pio
%endif
%ifdef BOARD_IDE_32BIT_POLICY
    cmp byte [fs:U_FIELD],10
    je .dword
%endif
    xor al,1
    mov [fs:bx+IDE_EDD_OFF],al
    jmp .done
.enabled:
    call ide_ui_enable_pointer
    mov [fs:bx],al
    jmp .done
.translation:
    movzx di,al
    mov al,[cs:ide_translation_from_display+di]
    mov [fs:bx+IDE_TRANSLATION],al
    jmp .done
.block:
    cmp al,7
    jae .block_special
    add al,2
    jmp .block_ready
.block_special:
    sub al,7
.block_ready:
    mov [fs:bx+IDE_BLOCK],al
    jmp .done
%ifdef BOARD_IDE_32BIT_POLICY
.dword:
    mov cl,[fs:U_IDE_DEVICE]
    mov al,1
    shl al,cl
    not al
    and [fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)],al
    mov al,dl
    shl al,cl
    or [fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)],al
    jmp .done
%endif
%ifdef BOARD_ATA_PIO_POLICY
.pio:
    mov cl,[fs:U_IDE_DEVICE]
    shl cl,1
    mov al,3
    shl al,cl
    not al
    and [fs:U_CHIP+(BOARD_ATA_PIO_POLICY-C_CHIP)],al
    mov al,dl
    inc al
    cmp al,6
    jb .pio_encoded
    xor al,al
.pio_encoded:
    mov ah,al
    and al,3
    shl al,cl
    or [fs:U_CHIP+(BOARD_ATA_PIO_POLICY-C_CHIP)],al
    shr cl,1
    mov al,1
    shl al,cl
    not al
    and [fs:U_CHIP+(BOARD_ATA_PIO_POLICY_HIGH-C_CHIP)],al
    shr ah,2
    shl ah,cl
    or [fs:U_CHIP+(BOARD_ATA_PIO_POLICY_HIGH-C_CHIP)],ah
%endif
.done:
    popad
    popf
    ret

ide_ui_select:
    cmp byte [fs:U_FIELD], 1
    je ide_ui_types
    cmp byte [fs:U_FIELD], 2
    jb .enum
    cmp byte [fs:U_FIELD], 6
    jbe ide_ui_number
.enum:
    pushad
    call ide_ui_parameters
    movzx bp, byte [fs:bx]
    mov dl, 2
    jmp setup_choices.draw ; Same popup/input/commit owner and stack contract.

ide_ui_change:
    pushad
    mov dl, 1
    cmp ah, 0x4B
    jne .field
    mov dl, -1
.field:
    cmp byte [fs:U_FIELD], 1
    je .type
    cmp byte [fs:U_FIELD], 2
    jb .enum
    cmp byte [fs:U_FIELD], 6
    jbe .number
.enum:
    push dx
    call ide_ui_parameters
    pop dx
    mov al, [fs:bx]
    add al, dl
    cmp al, 0xFF
    jne .upper
    mov al, cl
    dec al
.upper:
    cmp al, cl
    jb .store
    xor al, al
.store:
    call ide_ui_store
    jmp .done
.type:
    call ide_ui_record
    call ide_ui_type_value
.cycle:
    add al, dl
    cmp al, 0xFF
    jne .type_upper
    mov al, 49
.type_upper:
    cmp al, 49
    jbe .type_valid
    xor al, al
.type_valid:
    cmp al, 49
    je .type_apply
    call ide_type_valid
    jc .cycle
.type_apply:
    call ide_ui_set_type
    jmp .done
.number:
    ; Numeric fields use the same validated editor, not unchecked +/- writes.
.done:
    popad
    ret

; AL=selected type. Preserve its numeric identity even for equal geometries.
ide_ui_set_type:
    push bx
    call ide_ui_enable_pointer
    cmp al, 49
    jne .enabled
    mov byte [fs:bx], 0
    pop bx
    ret
.enabled:
    mov byte [fs:bx], 1
    pop bx
    mov [fs:bx + IDE_TYPE], al
    test al, al
    jz .done
    cmp al, 48
    je .done
    movzx si, al
    dec si
    shl si, 3
    add si, ide_type_table
    lea di, [bx + IDE_CYLINDERS]
    mov cx, 8
.byte:
    mov al, [cs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
.done:
    ret

ide_ui_draw:
    pushad
    movzx bx,byte [fs:U_IDE_DEVICE]
    shl bx,1
    mov si,[cs:u_ide_policy_labels+bx]
    mov di, 3 * 160 + 23 * 2
    mov bh, 0x0B
    call setup_text
    ui_text 4, UI_LABEL_COL, u_ide_disk_group, 0x0B
    ui_text 13, UI_LABEL_COL, u_ide_transfer_group, 0x0B
    xor bp, bp
.field:
    mov bx, bp
    shl bx, 1
    mov si, [u_ide_labels + bx]
    call .field_position
    add di, UI_LABEL_COL * 2
    mov bh, 7
    mov cx, bp
    call setup_field_available
    jnc .label
    mov bh, 8
.label:
    call setup_text
    call .field_position
    add di, UI_VALUE_COL * 2
    mov cx, bp
    call setup_field_color
    push bx
    call ide_ui_record
    cmp bp, 0
    je .enable
    cmp bp, 1
    je .type
    cmp bp, 7
    je .translation
    cmp bp, 8
    je .block
    cmp bp, 9
    je .edd
%ifdef BOARD_ATA_PIO_POLICY
    cmp bp,11
    je .pio
%endif
%ifdef BOARD_IDE_32BIT_POLICY
    cmp bp,10
    je .dword
%endif
    mov bx, bp
    sub bx, 2
    shl bx, 1
    mov bx, [u_ide_number_offsets + bx]
    movzx eax, word [fs:si + bx]
    cmp bp, 3
    je .byte_number
    cmp bp, 4
    jne .number
.byte_number:
    and eax, 255
.number:
    pop bx
    call setup_colored_number
    jmp .next
.enable:
    call ide_ui_enable_pointer
    movzx bx, byte [fs:bx]
    mov si, u_seek_values
    jmp .enum
.type:
    call ide_ui_type_value
    pop bx
    call ide_ui_type_text
    jmp .next
.translation:
    movzx bx, byte [fs:si + IDE_TRANSLATION]
    mov si, u_ide_translation_values
    jmp .enum
.block:
    movzx bx, byte [fs:si + IDE_BLOCK]
    mov si, u_ide_block_values
    jmp .enum
.edd:
    movzx bx, byte [fs:si + IDE_EDD_OFF]
    mov si, u_ide_edd_values
    jmp .enum
%ifdef BOARD_IDE_32BIT_POLICY
.dword:
    mov cl,[fs:U_IDE_DEVICE]
    mov bl,[fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)]
    shr bl,cl
    and bx,1
    mov si,u_seek_values
    jmp .enum
%endif
%ifdef BOARD_ATA_PIO_POLICY
.pio:
    call ide_ui_pio_value
    movzx bx,al
    mov si,u_ide_pio_values
%endif
.enum:
    shl bx, 1
    mov si, [si + bx]
    pop bx
    call setup_text
.next:
    inc bp
    cmp bp, IDE_FIELD_COUNT
    jb .field
    popad
    ret
.field_position:
    mov di, bp
    movzx di, byte [cs:u_ide_rows + di]
    imul di, 160
    ret

setup_colored_number:
    pushad
    call setup_number
    mov cx, 5
.color:
    mov ah, bh
    mov al, ' '
    call setup_color
    mov [es:di + 1], ah
    add di, 2
    loop .color
    popad
    ret

ide_ui_type_text:
    pushad
    mov si, u_ide_none
    cmp al, 49
    je .text
    mov si, u_auto
    test al, al
    jz .text
    mov si, u_ide_user
    cmp al, 48
    je .text
    mov si, u_ide_type_prefix
    call setup_text
    movzx eax, al
    add di, 5 * 2
    call setup_colored_number
    jmp .done
.text:
    call setup_text
.done:
    popad
    ret

;12-row paged list. Arrow/Page keys can reach every valid numbered type.
ide_ui_types:
    pushad
    call ide_ui_type_value
    movzx bp, al
.draw:
    call setup_draw
    call setup_modal_footer
    mov di, 5 * 160 + UI_POPUP_COL * 2
    mov ax, 0x1E20
    mov dx, 17
.clear:
    mov cx, UI_POPUP_WIDTH
    push ax
    call setup_color
    rep stosw
    pop ax
    add di, (80 - UI_POPUP_WIDTH) * 2
    dec dx
    jnz .clear
    ui_text 5, UI_POPUP_TEXT, u_ide_type_menu, 0x1B
    ui_text 6, UI_POPUP_TEXT, u_ide_type_columns, 0x1B
    mov ax, bp
    xor dx, dx
    mov cx, 12
    div cx
    imul dx, ax, 12
    mov si, dx
    xor cx, cx
.item:
    mov ax, si
    add ax, cx
    cmp ax, 49
    ja .items_done
    push si
    mov bx, cx
    imul di, bx, 160
    add di, 7 * 160 + UI_POPUP_TEXT * 2
    mov bh, 0x17
    cmp ax, bp
    jne .color
    mov bh, 0x70
.color:
    call setup_choice_highlight
    cmp al, 49
    je .valid
    call ide_type_valid
    jnc .valid
    mov si, u_ide_reserved
    call setup_text
    jmp .row_done
.valid:
    call ide_ui_type_text
    test al, al
    jz .row_done
    cmp al, 48
    jae .row_done
    mov dx, bx ; Keep the selected-row color while resolving the type table.
    movzx bx, al
    dec bx
    shl bx, 3
    add bx, ide_type_table
    mov si, bx
    mov bx, dx
    add di, UI_TYPE_WIDTH * 2
    movzx eax, word [cs:si]
    call setup_colored_number
    add di, UI_GEOMETRY_WIDTH * 2
    movzx eax, byte [cs:si + 2]
    call setup_colored_number
    add di, UI_GEOMETRY_WIDTH * 2
    movzx eax, byte [cs:si + 3]
    call setup_colored_number
.row_done:
    pop si
    inc cx
    cmp cx, 12
    jb .item
.items_done:
    ui_text 20, UI_POPUP_TEXT, u_choices_keys, 0x1B
    ui_text 21, UI_POPUP_TEXT, u_ide_page_keys, 0x1B
.wait:
    call setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait
.key:
    xor ah, ah
    int 0x16
    cmp al, 27
    je .done
    cmp al, 13
    je .apply
    mov dl, 1
    cmp ah, 0x50
    je .move
    cmp ah, 0x4D
    je .move
    cmp ah, 0x48
    je .previous
    cmp ah, 0x4B
    je .previous
    cmp ah, 0x51
    je .page_down
    cmp ah, 0x49
    jne .wait
    sub bp, 12
    jnc .bounded
    xor bp, bp
    jmp .bounded
.page_down:
    add bp, 12
    cmp bp, 49
    jbe .bounded
    mov bp, 49
.bounded:
    mov dl, 1
    jmp .validate
.previous:
    mov dl, -1
.move:
    movsx ax, dl
    add bp, ax
    cmp bp, 0xFFFF
    jne .upper
    mov bp, 49
.upper:
    cmp bp, 49
    jbe .validate
    xor bp, bp
.validate:
    mov ax, bp
    cmp al, 49
    je .draw
    call ide_type_valid
    jc .move
    jmp .draw
.apply:
    call ide_ui_record
    mov ax, bp
    call ide_ui_set_type
.done:
    popad
    ret

; Decimal editor for User geometry/metadata. Esc or invalid input writes nothing.
ide_ui_number:
    pushad
    call ide_ui_record
    cmp byte [fs:bx + IDE_TYPE], 48
    jne .done
    movzx bp, byte [fs:U_FIELD]
    sub bp, 2
    shl bp, 1
    mov di, [cs:u_ide_number_offsets + bp]
    add bx, di
    mov byte [fs:U_POSITION], 0
    mov byte [fs:U_BUFFER], 0
    push bx
    call setup_draw
    call setup_modal_footer
    ui_text 22, UI_LABEL_COL, u_ide_number_prompt, 0x1B
    pop bx
.draw:
    mov di, 22 * 160 + UI_VALUE_COL * 2
    mov ax, 0x1E20
    mov cx, 6
    push ax
    call setup_color
    rep stosw
    pop ax
    mov di, 22 * 160 + UI_VALUE_COL * 2
    mov si, U_BUFFER
    push bx
    mov bh, 0x1F
    call setup_value
    pop bx
.wait:
    call setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait
.key:
    xor ah, ah
    int 0x16
    cmp al, 27
    je .done
    cmp al, 13
    je .apply
    cmp al, 8
    je .back
    cmp al, '0'
    jb .wait
    cmp al, '9'
    ja .wait
    movzx si, byte [fs:U_POSITION]
    cmp si, 5
    jae .wait
    mov [fs:U_BUFFER + si], al
    inc si
    mov ax, si
    mov [fs:U_POSITION], al
    mov byte [fs:U_BUFFER + si], 0
    jmp .draw
.back:
    cmp byte [fs:U_POSITION], 0
    je .wait
    dec byte [fs:U_POSITION]
    movzx si, byte [fs:U_POSITION]
    mov byte [fs:U_BUFFER + si], 0
    jmp .draw
.apply:
    xor eax, eax
    xor si, si
    cmp byte [fs:U_POSITION], 0
    je .done
.digit:
    movzx edx, byte [fs:U_BUFFER + si]
    sub edx, '0'
    imul eax, 10
    add eax, edx
    inc si
    movzx dx, byte [fs:U_POSITION]
    cmp si, dx
    jb .digit
    movzx edx, word [cs:u_ide_number_max + bp]
    cmp eax, edx
    ja .bad
    cmp bp, 6
    jae .store
    test eax, eax
    jz .bad
.store:
    cmp bp, 2
    je .byte_store
    cmp bp, 4
    je .byte_store
    mov [fs:bx], ax
    jmp .done
.byte_store:
    mov [fs:bx], al
    jmp .done
.bad:
    push bx
    ui_text 21, UI_LABEL_COL, u_ide_invalid, 0x0C
    pop bx
    jmp .wait
.done:
    popad
    ret

u_ide_labels dw u_ide_enabled,u_ide_type,u_ide_cyl,u_ide_heads,u_ide_sectors
    dw u_ide_precomp,u_ide_landing,u_ide_translation,u_ide_block,u_ide_edd
%ifdef BOARD_IDE_32BIT_POLICY
    dw u_ide_dword
%endif
%ifdef BOARD_ATA_PIO_POLICY
    dw u_ide_pio
%endif
IDE_FIELD_COUNT equ ($-u_ide_labels)/2
u_ide_number_offsets dw IDE_CYLINDERS,IDE_HEADS,IDE_SECTORS,IDE_PRECOMP,IDE_LANDING
u_ide_number_max dw 65535,16,63,65535,65535
u_ide_translation_values dw u_auto,u_ide_normal,u_ide_large,u_ide_lba
u_ide_translation_choices dw u_auto,u_ide_large,u_ide_lba,u_ide_normal
ide_translation_to_display db 0,3,1,2
ide_translation_from_display db 0,2,3,1
u_ide_block_values dw u_auto,u_off,u_ide_block2,u_ide_block4,u_ide_block8
    dw u_ide_block16,u_ide_block32,u_ide_block64,u_ide_block128
u_ide_block_choices dw u_ide_block2,u_ide_block4,u_ide_block8,u_ide_block16
    dw u_ide_block32,u_ide_block64,u_ide_block128,u_auto,u_off
u_ide_edd_values dw u_on,u_off
%if BOARD_ATA_DEVICE_COUNT = 4
u_ide_controller db 'Onboard IDE Controller',0
%else
u_ide_controller db 'Primary IDE Controller',0
%endif
u_ide_disk_group db 'DISK CONFIGURATION',0
u_ide_transfer_group db 'TRANSFER OPTIONS',0
u_ide_enabled db 'Device',0
u_ide_type db 'Disk Type',0
u_ide_none db 'None',0
u_ide_translation db 'Translation',0
u_ide_block db 'Block Mode',0
u_ide_cyl db 'Cylinders',0
u_ide_heads db 'Heads',0
u_ide_sectors db 'Sectors per Track',0
u_ide_precomp db 'Write Precompensation',0
u_ide_landing db 'Landing Zone',0
u_ide_edd db 'INT13 Extensions',0
u_ide_user db 'User (48)',0
u_ide_type_prefix db 'Type ',0
u_ide_type_menu db 'PHOENIX DISK TYPE',0
u_ide_type_columns db 'Type            Cyls    Heads   Sectors',0
u_ide_reserved db 'Reserved',0
u_ide_page_keys db 'PgUp/PgDn Page',0
u_ide_number_prompt db 'Enter value',0
u_ide_invalid db 'Invalid value.',0
u_ide_normal db 'Normal',0
u_ide_large db 'Large',0
u_ide_lba db 'LBA',0
u_ide_block2 db '2 sectors',0
u_ide_block4 db '4 sectors',0
u_ide_block8 db '8 sectors',0
u_ide_block16 db '16 sectors',0
u_ide_block32 db '32 sectors',0
u_ide_block64 db '64 sectors',0
u_ide_block128 db '128 sectors',0
u_help_ide_enabled1 db 'Disabled stops the BIOS from using this drive.',0
u_help_ide_enabled2 db 'Other drives keep their own settings.',0
u_help_ide_type1 db 'Auto detects. None leaves it to an expansion card.',0
u_help_ide_type2 db 'Choose User to enter the drive details yourself.',0
u_help_ide_translation1 db 'Choose how the BIOS addresses this hard disk.',0
u_help_ide_translation2 db 'Keep the mode used when the disk was formatted.',0
u_help_ide_block1 db 'Transfer several disk sectors together.',0
u_help_ide_block2 db 'Auto selects a size supported by the drive.',0
u_help_ide_cyl1 db 'For User type, enter the cylinder count: 1-65535.',0
u_help_ide_cyl2 db 'Use the value printed on the drive or its manual.',0
u_help_ide_heads1 db 'For User type, enter the head count: 1-16.',0
u_help_ide_heads2 db 'Use the value printed on the drive or its manual.',0
u_help_ide_sectors1 db 'For User type, enter sectors per track: 1-63.',0
u_help_ide_sectors2 db 'Use the value printed on the drive or its manual.',0
u_help_ide_precomp1 db 'An older drive setting. 65535 means None.',0
u_help_ide_precomp2 db 'IDE drives manage this themselves.',0
u_help_ide_landing1 db 'An older head parking setting: 0-65535.',0
u_help_ide_landing2 db 'IDE drives park their heads themselves.',0
u_help_ide_edd1 db 'Enable extended BIOS support for larger disks.',0
u_help_ide_edd2 db 'Disable only for software that needs older access.',0
u_help_ide_controller1 db 'Enable the motherboard hard disk controller.',0
u_help_ide_controller2 db 'Disabled turns off its hard disk and CD drives.',0

ports_ui_parameters:
    movzx bx, byte [fs:U_FIELD]
%ifdef BOARD_PORTS_SETUP_PARAMETERS
    jmp BOARD_PORTS_SETUP_PARAMETERS
%else
    mov cx, bx
    movzx cx, byte [cs:ports_limits+bx]
    inc cx
    shl bx, 1
    mov si, [cs:u_ports_values+bx]
    shr bx, 1
    add bx, U_PORTS
    ret
%endif

; AL=candidate. The same sibling rule governs arrows and popup navigation.
ports_ui_choice_valid:
    push bx
    movzx bx, byte [fs:U_FIELD]
    call ports_ui_candidate
    jc .bad
    cmp bx, 1
    ja .good
    test al, al
    jz .good
    xor bx, 1
    cmp al, [fs:U_PORTS+bx]
    je .bad
.good:
    pop bx
    clc
    ret
.bad:
    pop bx
    stc
    ret

ports_ui_choices:
    pushad
    call ports_ui_parameters
    movzx bp, byte [fs:bx]
    mov dl, 2
    jmp setup_choices.draw

ports_ui_change:
    pushad
    mov dl, 1
    cmp ah, 0x4B
    jne .parameters
    mov dl, -1
.parameters:
    call ports_ui_parameters
    mov al, [fs:bx]
.cycle:
    add al, dl
    cmp al, 0xFF
    jne .upper
    mov al, cl
    dec al
.upper:
    cmp al, cl
    jb .valid
    xor al, al
.valid:
    call ports_ui_choice_valid
    jc .cycle
%ifdef BOARD_PORTS_SETUP_COMMIT
    call setup_enum_store
%else
    mov [fs:bx], al
%endif
    popad
    ret

ports_ui_draw:
    pushad
    ui_text 3, 23, u_devices_title, 0x0B
    xor bp, bp
.field:
    mov cx,bp
    call ports_ui_visible
    jc .next
    mov bx, bp
    shl bx, 1
    mov si, [cs:u_ports_labels+bx]
    movzx di, byte [cs:u_ports_rows+bp]
    imul di, 160
    add di, UI_LABEL_COL*2
    mov cx, bp
    call setup_field_color
    and bh, 15
    call setup_text
%ifdef BOARD_PORTS_SETUP_PARAMETERS
    mov bx,bp
    call BOARD_PORTS_SETUP_PARAMETERS
    movzx bx,byte [fs:bx]
%else
    mov bx, bp
    shl bx, 1
    mov si, [cs:u_ports_values+bx]
    movzx bx, byte [fs:U_PORTS+bp]
%endif
    shl bx, 1
    mov si, [cs:si+bx]
    add di, (UI_VALUE_COL-UI_LABEL_COL)*2
    mov cx, bp
    call setup_field_color
    call setup_text
.next:
    inc bp
%ifdef BOARD_PORTS_SETUP_COUNT
    cmp bp, BOARD_PORTS_SETUP_COUNT
%else
    cmp bp, 8
%endif
    jb .field
    popad
    ret

u_devices db 'Devices',0
u_devices_title db 'bAIos Setup > Devices',0
u_uart_a db 'Serial Port',0
u_uart_b db 'Serial Port B',0
u_uart_pair db 'COM3 / COM4 Addresses',0
u_parallel db 'Parallel Port',0
u_parallel_mode db 'Parallel Port Mode',0
u_fdc db 'Floppy Controller',0
u_mouse db 'PS/2 Mouse',0
u_isa db 'ISA Serial Discovery',0
u_ports_rows db BOARD_PORTS_ROWS
%ifdef BOARD_PORTS_SETUP_LABELS
u_ports_labels dw BOARD_PORTS_SETUP_LABELS
%else
u_ports_labels dw u_uart_a,u_uart_b,u_uart_pair,u_parallel,u_parallel_mode,u_fdc,u_mouse,u_isa
%endif
u_ports_values dw BOARD_PORTS_VALUES
u_uart_values dw u_disabled,u_com1,u_com2,u_com3,u_com4
u_pair_values dw u_pair0,u_pair1,u_pair2,u_pair3
u_parallel_values dw u_disabled,u_lpt0,u_lpt1,u_lpt2
u_mode_values dw BOARD_PORTS_MODES
u_com1 db '3F8h / IRQ4',0
u_com2 db '2F8h / IRQ3',0
u_com3 db '3E8h / IRQ4',0
u_com4 db '2E8h / IRQ3',0
u_pair0 db '338h / 238h',0
u_pair1 db '3E8h / 2E8h',0
u_pair2 db '2E8h / 2E0h',0
u_pair3 db '220h / 228h',0
u_lpt0 db '3BCh',0
u_lpt1 db '378h',0
u_lpt2 db '278h',0
u_printer db 'Printer',0
u_bidirectional db 'PS/2 Bidirectional',0
u_help_devices1 db 'Configure onboard ports and devices.',0
u_help_devices2 db 'Save applies settings after restart.',0
u_help_uart1 db 'Choose a COM port number for this serial port.',0
u_help_uart2 db 'Disabled turns off the onboard serial port.',0
u_help_pair1 db 'Choose the address pair for COM3 and COM4.',0
u_help_pair2 db 'Match the addresses required by your software.',0
u_help_parallel1 db 'Choose the printer port address or Disabled.',0
u_help_parallel2 db 'Printer ports on expansion cards are also found.',0
u_help_mode1 db BOARD_PORTS_MODE_HELP,0
u_help_mode2 db 'Available when the parallel port is enabled.',0
u_help_fdc1 db 'Enable or disable both motherboard floppy drives.',0
u_help_fdc2 db 'Saved drive types remain available when enabled.',0
u_help_mouse1 db 'Enable or disable the PS/2 mouse port.',0
u_help_mouse2 db 'Keyboard operation remains enabled.',0
u_help_isa1 db 'Find serial ports on ISA expansion cards.',0
u_help_isa2 db 'Set each card with its jumpers or setup program.',0

ports_summary:
    pushad
    push ds
    ui_text 6, 40, u_summary_com, 0x0B
    mov di, 6*160+58*2
    xor ax, ax
    mov ds, ax
    mov si, 0x400
    mov cx, 4
    call .bases
    push cs
    pop ds
    ui_text 7, 40, u_summary_lpt, 0x0B
    mov di, 7*160+58*2
    xor ax, ax
    mov ds, ax
    mov si, 0x408
    mov cx, 3
    call .bases
    pop ds
    popad
    ret
.bases:
    lodsw
    test ax, ax
    jz .next
    push ax
    mov al, ah
    call setup_hex8
    pop ax
    call setup_hex8
    mov ax, 0x0720
    push ax
    call setup_color
    stosw
    pop ax
 .next:
    loop .bases
    ret
u_summary_com db 'COM Ports',0
u_summary_lpt db 'LPT Ports',0

%include BOARD_PORTS_SETUP_STRINGS

u_ide_policy_labels:
%if BOARD_ATA_DEVICE_COUNT = 4
    dw u_hdd_policy,u_slave_policy,u_ide_policy3,u_ide_policy4
u_ide_policy3 db 'Secondary IDE Master',0
u_ide_policy4 db 'Secondary IDE Slave',0
%else
    dw u_hdd_policy,u_slave_policy
%endif
