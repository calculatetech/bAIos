chipset_ui_cas_draw:
    pushad
    call setup_modal_footer
    mov di, 8*160+UI_POPUP_COL*2
    mov ax, 0x1E20
    mov dx, 15
.clear:
    mov cx, UI_POPUP_WIDTH
    push ax
    call setup_color
    rep stosw
    pop ax
    add di, (80-UI_POPUP_WIDTH)*2
    dec dx
    jnz .clear
    ui_text 8,UI_POPUP_TEXT,chip_cas_title,0x1B
    ui_text 10,26,chip_cas_left,0x1B
    ui_text 10,38,chip_cas_separator,0x1B
    ui_text 10,40,chip_cas_right,0x1B
    xor dx, dx
.item:
    mov di, dx
    add di, 12
    imul di, 160
    add di, 26*2
    mov bh, 0x17
    cmp dx, bp
    jne .colour
    mov bh, 0x70
.colour:
    call setup_choice_highlight
    mov bx, dx
    shl bx, 1
    mov si, [cs:chip_cas_disabled+bx]
    ; The offset occupies BL only; restore the selected row attribute.
    mov bh, 0x17
    cmp dx, bp
    jne .left
    mov bh, 0x70
.left:
    call setup_text
    add di, (38-26)*2
    mov si, chip_cas_separator
    call setup_text
    add di, (40-38)*2
    push bx
    mov bx, dx
    shl bx, 1
    mov si, [cs:chip_cas_enabled+bx]
    pop bx
    call setup_text
    inc dx
    cmp dx, 4
    jb .item
    ui_text 22,UI_POPUP_TEXT,u_choices_keys,0x1B
    popad
    ret
