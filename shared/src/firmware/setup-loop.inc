post_ui_setup_main:
    pushad
    push ds
    push es
    push fs
    cld
    call post_ui_load_bios_state
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
    mov al,[fs:C_POST_DELAY]
    mov [fs:U_POST_DELAY],al
%ifdef BOARD_PCI_VIDEO_ORDER
    mov al,[fs:C_VIDEO_ORDER]
    mov [fs:U_VIDEO_ORDER],al
%endif
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
    call post_ui_ide_copy_bytes
    mov si, C_PORTS
    mov di, U_PORTS
    mov cx, 8
    call post_ui_ide_copy_bytes
    mov si, C_CHIP
    mov di, U_CHIP
    mov cx, CHIP_SIZE
    call post_ui_ide_copy_bytes
%ifdef BOARD_PNP_SUPPORT
    mov si,C_PNP
    mov di,U_PNP
    mov cx,PNP_SIZE
    call post_ui_ide_copy_bytes
    mov byte [fs:U_PNP_SCREEN],0
%endif
    mov byte [fs:U_CHIP_SCREEN], 0
    mov byte [fs:U_IDE_DEVICE], 0xFF
    call post_ui_setup_video_mode
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
.redraw:
    mov cl, [fs:U_FIELD]
.normalize_field:
    call post_ui_setup_field_available
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
    call post_ui_setup_draw
.input:
%ifdef EMULATOR_CHIPSET_TEST
    call post_ui_chipset_test_capture_drain
%endif
%ifdef EMULATOR_PORTS_TEST
    call post_ui_ports_test_capture_drain
%endif
    call post_ui_setup_clock
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
    call post_ui_setup_field_available
    jc .input
    cmp byte [fs:U_PAGE], 0
    jne .non_clock_enter
    cmp byte [fs:U_FIELD], 2
    jb .start_edit
    jmp .choices
.non_clock_enter:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    jne .non_pnp_enter
    call post_ui_pnp_ui_select
    jmp .redraw
.non_pnp_enter:
%endif
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
    call post_ui_ide_ui_select
    jmp .redraw
.choices:
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_choices
    call post_ui_chipset_ui_select
    jmp .redraw
.ordinary_choices:
    call post_ui_setup_choices
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
    call post_ui_setup_edit_begin
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
    call post_ui_chipset_ui_page
    jmp .redraw
.up:
    cmp byte [fs:U_FOCUS], 0
    jne .field
    movzx bx,byte [fs:U_PAGE]
%ifdef BOARD_PNP_SUPPORT
    mov al,[POST_UI_DATA:pnp_sidebar_up+bx]
%else
    mov al,[POST_UI_DATA:setup_sidebar_up+bx]
%endif
    jmp .sidebar_selected
.sidebar_selected:
    mov [fs:U_PAGE], al
    mov byte [fs:U_FIELD], 0
    jmp .redraw
.down:
    cmp byte [fs:U_FOCUS], 0
    jne .field
    movzx bx,byte [fs:U_PAGE]
%ifdef BOARD_PNP_SUPPORT
    mov al,[POST_UI_DATA:pnp_sidebar_down+bx]
%else
    mov al,[POST_UI_DATA:setup_sidebar_down+bx]
%endif
    jmp .sidebar_selected
.field:
    mov bl, 1
    cmp byte [fs:U_PAGE], 0
    jne .field_count
    mov bl, 2
.field_count:
    cmp byte [fs:U_PAGE], 5
    jne .non_chip_field
    call post_ui_chipset_ui_count
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
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    jne .field_count_ready
    call post_ui_pnp_ui_count
    mov bl,cl
    dec bl
.field_count_ready:
%endif
    mov cl, [fs:U_FIELD]
    cmp ah, 0x48
    jne .field_down
.field_up:
    test cl, cl
    je .input
    dec cl
    call post_ui_setup_field_available
    jc .field_up
    jmp .field_selected
.field_down:
    cmp cl, bl
    jae .input
    inc cl
    call post_ui_setup_field_available
    jc .field_down
.field_selected:
    mov [fs:U_FIELD], cl
    jmp .redraw
.change:
    cmp byte [fs:U_FOCUS], 1
    jne .input
    mov cl, [fs:U_FIELD]
    call post_ui_setup_field_available
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
    call post_ui_ide_ui_change
    jmp .redraw
.old_change:
    call post_ui_setup_change
    jmp .redraw
.escape:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    jne .non_pnp_escape
    cmp byte [fs:U_PNP_SCREEN],0
    je .non_pnp_escape
    mov al,[fs:U_PNP_SCREEN]
    dec al
    mov [fs:U_FIELD],al
    mov byte [fs:U_PNP_SCREEN],0
    jmp .redraw
.non_pnp_escape:
%endif
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
    call post_ui_setup_help
    jmp .redraw
.exit_action:
    cmp byte [fs:U_FIELD], 0
    je .save
.discard:
    mov si, u_discard_confirm
    call post_ui_setup_confirm
    jc .redraw
    call post_ui_setup_restore_text
    pop fs
    pop es
    pop ds
    popad
    ret
.defaults:
    mov si, u_defaults_confirm
    call post_ui_setup_confirm
    jc .redraw
    call post_ui_setup_defaults
    jmp .redraw
.save:
    mov si, u_save_confirm
    call post_ui_setup_confirm
    jc .redraw
    call post_ui_settings_save
    jc .save_error
    call post_ui_setup_restore_text
    mov ax, 0x0040
    mov ds, ax
    jmp post_ui_warm_reset
.save_error:
    ui_text 19, 23, u_save_error, 0x0C
    ui_text 20, 23, u_save_trace, 0x07
    mov di, 20 * 160 + 49 * 2
    mov bx, U_SAVE_TRACE
    mov cx, 3
.save_byte:
    mov al, [fs:bx]
    call post_ui_setup_hex8
    mov ax, 0x0720
    push ax
    call post_ui_setup_color
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
    call post_ui_setup_edit_apply
    jc .invalid
.cancel_edit:
    mov byte [fs:U_EDIT], 0
    jmp .redraw
.invalid:
    ui_text 20, 23, u_invalid, 0x0C
    jmp .input

post_ui_setup_video_mode:
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

