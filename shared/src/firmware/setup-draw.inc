post_ui_setup_draw:
    mov di, 0
    mov ax, 0x0720
    mov cx, 2000
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    ; Cyan frame, compact sidebar, and blue masthead follow the concept.
    mov di, 0
    mov ax, 0x1F20
    mov cx, 80 * 2
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    mov bx, 0x0B00
    mov cx, 80
    mov di, 2 * 160
    mov ax, 0x0BCD
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    mov di, 23 * 160
    mov cx, 80
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    mov di, 3 * 160 + 20 * 2
    mov cx, 20
    mov ax, 0x0BB3
.vertical:
    push ax
    call post_ui_setup_color
    mov [es:di], ax
    pop ax
    add di, 160
    loop .vertical
    mov di, 2 * 160 + 20 * 2
    mov ax, 0x0BD1
    call post_ui_setup_color
    mov [es:di], ax
    mov di, 23 * 160 + 20 * 2
    mov ax, 0x0BCF
    call post_ui_setup_color
    mov [es:di], ax
    ui_text 0, 3, u_platform, 0x1B
    ui_text 0, 34, u_title, 0x1F
    call post_ui_post_processor_name
    mov di, 1 * 160 + 3 * 2
    mov bh, 0x1B
    call post_ui_setup_text
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
    call post_ui_setup_color
    stosw
    pop ax
    loop .build_date
    ui_text 3, 2, u_menu, 0x0B
    ui_text 5, 2, u_standard, 0x07
    ui_text 6, 2, u_drives, 0x07
    ui_text 7, 2, u_boot, 0x07
    ui_text 8, 2, u_devices, 0x07
    ui_text 9, 2, u_chip_menu, 0x07
%ifdef BOARD_PNP_SUPPORT
    ui_text 10,2,pnp_menu,0x07
    ui_text 11, 2, u_exit, 0x07
%else
    ui_text 10, 2, u_exit, 0x07
%endif
    movzx bx,byte [fs:U_PAGE]
%ifdef BOARD_PNP_SUPPORT
    movzx ax,byte [POST_UI_DATA:pnp_sidebar_rows+bx]
%else
    movzx ax,byte [POST_UI_DATA:setup_sidebar_rows+bx]
%endif
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
%ifdef BOARD_PNP_SUPPORT
    mov si,pnp_menu
    cmp byte [fs:U_PAGE],6
    je .sidebar
%endif
    mov si, u_chip_menu
.sidebar:
    mov bh, 0x1F
    cmp byte [fs:U_FOCUS], 0
    je .highlight
    mov bh, 0x0B
.highlight:
    call post_ui_setup_text
    cmp byte [fs:U_FOCUS], 0
    jne .footer
    pushad
    sub di, 2
    mov cx, 18
    mov dx, 1
    call post_ui_setup_selection_bar
    popad
.footer:
    cmp byte [fs:U_THEME], 0
    je .footer_ready
    mov di, 24 * 160
    mov ax, 0x0B20
    call post_ui_setup_color
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
    call post_ui_setup_text
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_page
    call post_ui_chipset_ui_draw
    jmp .done
.ordinary_page:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    jne .non_pnp_page
    call post_ui_pnp_ui_draw
    jmp .done
.non_pnp_page:
%endif
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
    call post_ui_setup_text
    ui_text 9, UI_LABEL_COL, u_total, 0x07
    memory_extended_kib eax
    add eax, 1024
    mov di, 9 * 160 + UI_VALUE_COL * 2
    call post_ui_setup_number
    ui_text 9, 59, u_kb, 0x07
    ui_text 10, UI_LABEL_COL, u_base, 0x07
    push es
    xor ax, ax
    mov es, ax
    movzx eax, word [es:0x0413]
    pop es
    mov di, 10 * 160 + UI_VALUE_COL * 2
    call post_ui_setup_number
    ui_text 10, 59, u_kb, 0x07
    ui_text 11, UI_LABEL_COL, u_extended, 0x07
    memory_extended_kib eax
    mov di, 11 * 160 + UI_VALUE_COL * 2
    call post_ui_setup_number
    ui_text 11, 59, u_kb, 0x07
    cmp byte [fs:U_EDIT], 0
    je .done
    mov si, U_BUFFER
    mov di, 19 * 160 + 24 * 2
    mov bh, 0x1E
    call post_ui_setup_value
    movzx bx, byte [fs:U_POSITION]
    shl bx, 1
    push di
    add di, bx
    mov ax, 0x7020
    call post_ui_setup_color
    mov [es:di + 1], ah
    pop di
    jmp .done
.drives:
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .channel
    call post_ui_ide_ui_draw
    jmp .done
.channel:
    ui_text 3, 23, u_drives_title, 0x0B
    ui_text 5, UI_LABEL_COL, u_drive_a, 0x07
    mov al, [fs:U_TYPES]
    shr al, 4
    call .floppy
    mov di, 5 * 160 + UI_VALUE_COL * 2
    xor cl, cl
    call post_ui_setup_field_color
    call post_ui_setup_text
    ui_text 6, UI_LABEL_COL, u_drive_b, 0x07
    mov al, [fs:U_TYPES]
    and al, 15
    call .floppy
    mov di, 6 * 160 + UI_VALUE_COL * 2
    mov cl, 1
    call post_ui_setup_field_color
    call post_ui_setup_text
    xor bp,bp
.ide_policy:
    mov bx,bp
    shl bx,1
    mov si,[POST_UI_DATA:u_ide_policy_labels+bx]
    mov di,bp
    add di,8
    imul di,160
    push di
    add di,UI_LABEL_COL*2
    mov cx,bp
    add cl,2
    call post_ui_setup_field_color
    and bh,0x0F
    call post_ui_setup_text
    pop di
    add di,UI_VALUE_COL*2
    mov cx,bp
    add cl,2
    call post_ui_setup_field_color
    push bx
    mov ax,bp
    call post_ui_ide_ui_enable_index
    cmp byte [fs:bx],0
    je .ide_disabled
    mov bx,bp
    imul bx,IDE_RECORD_SIZE
    mov al,[fs:U_IDE+1+bx+IDE_TYPE]
    pop bx
    call post_ui_ide_ui_type_text
    jmp .ide_arrow
.ide_disabled:
    pop bx
    mov si,u_ide_none
    call post_ui_setup_text
.ide_arrow:
    call post_ui_setup_submenu_arrow
    inc bp
    cmp bp,BOARD_ATA_DEVICE_COUNT
    jb .ide_policy
.controller:
    ui_text BOARD_ATA_DEVICE_COUNT+9, UI_LABEL_COL, u_ide_controller, 0x07
    call post_ui_setup_ide_controller_parameters
    movzx bx, byte [fs:bx]
    shl bx, 1
    mov si, [POST_UI_DATA:si + bx]
    mov di, (BOARD_ATA_DEVICE_COUNT+9) * 160 + UI_VALUE_COL * 2
    mov cl, BOARD_ATA_DEVICE_COUNT+2
    call post_ui_setup_field_color
    call post_ui_setup_text
    ui_text BOARD_ATA_DEVICE_COUNT+10, UI_LABEL_COL, u_fdc, 0x07
    movzx bx, byte [fs:U_PORTS+P_FLOPPY]
    shl bx, 1
    mov si, [u_seek_values + bx]
    mov di, (BOARD_ATA_DEVICE_COUNT+10) * 160 + UI_VALUE_COL * 2
    mov cl, BOARD_ATA_DEVICE_COUNT+3
    call post_ui_setup_field_color
    call post_ui_setup_text
    ui_text BOARD_ATA_DEVICE_COUNT+11, UI_LABEL_COL, u_swap, 0x07
    movzx bx, byte [fs:U_SWAP]
    shl bx, 1
    mov si, [u_seek_values + bx]
    mov di, (BOARD_ATA_DEVICE_COUNT+11) * 160 + UI_VALUE_COL * 2
    mov cl, BOARD_ATA_DEVICE_COUNT+4
    call post_ui_setup_field_color
    call post_ui_setup_text
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
    call post_ui_setup_field_color
    call post_ui_setup_text
    mov si, u_discard
    mov di, 6 * 160 + 24 * 2
    mov cl, 1
    call post_ui_setup_field_color
    call post_ui_setup_text
    jmp .done
.devices:
%ifdef BOARD_PORTS_SETUP_DRAW
    call post_ui_ui_board_ports_draw
%else
%ifdef BOARD_PORTS_NOTE1
    ui_text 5,UI_LABEL_COL,BOARD_PORTS_NOTE1,7
    ui_text 6,UI_LABEL_COL,BOARD_PORTS_NOTE2,7
%endif
    call post_ui_ports_ui_draw
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
    movzx di, byte [POST_UI_DATA:u_boot_rows + di]
    imul di, 160
    add di, UI_LABEL_COL * 2
    mov bh, 7
    call post_ui_setup_text
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
    cmp bp,POST_DELAY_FIELD
    jne .video_order_value
    mov si,[u_post_delay_values+bx]
.video_order_value:
%ifdef BOARD_PCI_VIDEO_ORDER
    cmp bp,VIDEO_ORDER_FIELD
    jne .ordinary_boot_value
    mov si,[u_video_order_values+bx]
.ordinary_boot_value:
%endif
    mov cx, bp
    call post_ui_setup_field_color
    call post_ui_setup_text
    inc bp
    cmp bp, BOOT_FIELD_COUNT
    jb .boot_field
.done:
    call post_ui_setup_field_highlight
    ret

; Color whole cells, including spaces, without changing their characters.
; DI=top-left, CX=width, DX=height, BH=attribute. Preserve every caller register.
