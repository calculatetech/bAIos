post_ui_post_debug_summary:
    pushad
    push ds
    push es
    push fs
    call post_ui_load_bios_state
%ifndef BOARD_PNP_SUPPORT
    call post_summary_pause
%endif
%ifdef EMULATOR_CHIPSET_SUMMARY_LONG
    call post_ui_summary_test_prepare_long
%endif
    call post_ui_setup_restore_text
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov ax, 0x0720
    mov cx, 2000
    cld
    push ax
    call post_ui_setup_color
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
    call post_ui_post_header
    ui_text 2, 3, u_summary_processor, 0x0B
    call post_ui_post_processor_name
    mov di, 2*160+(20+BOARD_POST_SUMMARY_SHIFT)*2
    mov bh, 7
    call post_ui_setup_text
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
    mov di, 3*160+(20+BOARD_POST_SUMMARY_SHIFT)*2
    mov bh, 7
    call post_ui_setup_text
    ui_text 4, 3, u_l2, 0x0B
    call post_ui_post_summary_cache
.memory:
    ui_text 2, 40, u_base, 0x0B
    mov di,2*160+(58+BOARD_POST_SUMMARY_SHIFT)*2
    call post_ui_post_summary_base_memory
    ui_text 2, 64+BOARD_POST_SUMMARY_SHIFT, u_kb, 0x07
    ui_text 3, 40, u_extended, 0x0B
    memory_extended_kib eax
    mov di, 3*160+(58+BOARD_POST_SUMMARY_SHIFT)*2
    call post_ui_setup_number
    ui_text 3, 64+BOARD_POST_SUMMARY_SHIFT, u_kb, 0x07
    ui_text 4, 40, u_summary_banks, 0x0B
    mov di, 4*160+(58+BOARD_POST_SUMMARY_SHIFT)*2
    call post_ui_post_memory_banks
    ui_text 6, 3, u_drive_a, 0x0B
    mov al, [fs:F_TYPES]
    mov di, 6*160+(20+BOARD_POST_SUMMARY_SHIFT)*2
    call .floppy
    ui_text 7, 3, u_drive_b, 0x0B
    mov al, [fs:F_TYPES+1]
    mov di, 7*160+(20+BOARD_POST_SUMMARY_SHIFT)*2
    call .floppy
    call post_ui_ports_summary
    push fs
    mov bp,9*160
    mov cx,BOARD_ATA_DEVICE_COUNT
.disk:
    push cx
    call post_ui_post_device_label
    mov di,bp
    add di,3*2
    mov bh,0x0B
    call post_ui_setup_text
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
    call post_ui_rtc_read
    and al, 0xBF
    cmp al, 0x1A
    jne .done
    mov bp, 12+BOARD_ATA_DEVICE_COUNT
    ui_text 11+BOARD_ATA_DEVICE_COUNT, 54, u_summary_recovery, 0x0C
.done:
%ifdef BOARD_FLOPPY_POST_DETAILS
    test byte [fs:C_ERROR],2
    jz .no_floppy_details
    call post_ui_ui_board_floppy_details
    mov bp,13+BOARD_ATA_DEVICE_COUNT
.no_floppy_details:
%endif
    mov dx, bp
    shl dx, 8
    xor bx, bx
    mov ah, 2
    int 0x10                      ; Normal BIOS/OS output continues from here.
%ifdef EMULATOR_POST_SUMMARY_TEST
    call post_ui_summary_test_begin
%endif
%ifdef EMULATOR_TEST
%ifndef EMULATOR_POST_SUMMARY_TEST
%ifndef EMULATOR_CHIPSET_PREVIEW
    call post_ui_summary_test_begin
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
    call post_ui_setup_color
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
    jmp post_ui_setup_text
.device:
    mov di, bp
    add di, (23+BOARD_POST_SUMMARY_SHIFT)*2
    mov si, u_absent
    cmp byte [fs:S_PRESENT], 1
    je .model
    cmp byte [fs:S_ATAPI], 1
    jne .device_done
.model:
    mov si, S_MODEL
    mov cx, 40                     ; Full ATA model, columns23..62 before the port layout shift.
.model_char:
    mov al, [fs:si]
    inc si
    test al, al
    jz .kind
    mov ah, 7
    push ax
    call post_ui_setup_color
    stosw
    pop ax
    loop .model_char
.kind:
    mov di, bp
    add di, (64+BOARD_POST_SUMMARY_SHIFT)*2
    mov ax, 0x0B5B                 ; Teal brackets around compact device details.
    call post_ui_setup_color
    stosw
    mov si, msg_atapi
    cmp byte [fs:S_ATAPI], 1
    je .pio
    mov eax, [fs:S_CAPACITY]
    shr eax, 11
    call post_ui_setup_number
.size_end:
    cmp byte [es:di], ' '          ; Number preserves DI; find its trailing blank.
    je .size_unit
    add di, 2
    jmp .size_end
.size_unit:
    mov si, u_summary_mb
    mov bh, 7
    call post_ui_setup_text
    add di, 3*2
    jmp .pio_label
.pio:
    mov bh, 7
    call post_ui_setup_text
    add di, 5*2
.pio_label:
    mov si, u_summary_pio
    mov bh, 7
    call post_ui_setup_text
    add di, 4*2
%ifdef BOARD_ATA_PIO_MAX
%ifdef BOARD_ATA_PIO_ADAPTER
    mov al,[fs:S_PIO_MODE]
    add al,'0'
    mov ah,7
    call post_ui_setup_color
    stosw
%else
    call post_ui_ide_pio_mode_text
%endif
%endif
    mov ax, 0x0B5D
    call post_ui_setup_color
    stosw
    ret
.device_done:
    mov bh, 7
    jmp post_ui_setup_text

