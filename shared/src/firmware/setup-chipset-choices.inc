post_ui_chipset_ui_choices:
    mov cl, [fs:U_FIELD]
    call post_ui_chipset_ui_editable
    jnc .open
    ret
.open:
    pushad
    call post_ui_chipset_ui_parameters
    movzx bp, byte [fs:U_CHIP_VALUE]
    cmp cx, 10
    ja .paged
    mov dl, 2
    jmp post_ui_setup_choices.draw
.paged:
    call post_ui_setup_modal_footer
    pushad
    mov di, 8*160+UI_POPUP_COL*2
    mov ax, 0x1E20
    mov dx, 15
.clear:
    mov cx, UI_POPUP_WIDTH
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    add di, (80-UI_POPUP_WIDTH)*2
    dec dx
    jnz .clear
    ui_text 8,UI_POPUP_TEXT,u_choices,0x1B
    popad
    pushad
    mov ax, bp
    xor dx, dx
    mov bx, 12
    div bx
    inc ax
    push ax
    mov ax, cx
    add ax, 11
    xor dx, dx
    div bx
    mov dx, ax
    pop ax
    movzx eax, ax
    mov di, 8*160+62*2
    mov bh, 0x1B
    call post_ui_chipset_ui_indicator
    mov ax, bp
    xor dx, dx
    mov bx, 12
    div bx
    imul bp, ax, 12
    xor dx, dx
.item:
    mov bx, bp
    add bx, dx
    cmp bx, cx
    jae .items_done
    mov di, dx
    add di, 10
    imul di, 160
    add di, UI_POPUP_TEXT*2
    mov bh, 0x17
    mov ax, bp
    add ax, dx
    cmp al, [fs:U_CHIP_VALUE]
    jne .color
    mov bh, 0x70
.color:
    call post_ui_setup_choice_highlight
    call post_ui_chipset_ui_option_text
    inc dx
    cmp dx, 12
    jb .item
.items_done:
    ui_text 22,UI_POPUP_TEXT,u_ide_page_keys,0x1B
    popad
.wait:
%ifdef EMULATOR_CHIPSET_TEST
    call post_ui_chipset_test_capture_drain
%endif
    call post_ui_setup_clock
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
    call post_ui_setup_help
    pushad
    call post_ui_setup_draw
    popad
    jmp .paged
.arrows:
    mov dx, 1
    cmp ah, 0x50
    je .move
    cmp ah, 0x4D
    je .move
    mov dx, -1
    cmp ah, 0x48
    je .move
    cmp ah, 0x4B
    je .move
    mov dx, 12
    cmp ah, 0x51
    je .move
    mov dx, -12
    cmp ah, 0x49
    jne .wait
.move:
    add bp, dx
    test bp, bp
    jns .limit
    xor bp, bp
.limit:
    cmp bp, cx
    jb .selected
    mov bp, cx
    dec bp
.selected:
    mov ax, bp
    mov [fs:U_CHIP_VALUE], al
    jmp .paged
.apply:
    call post_ui_chipset_ui_commit
.done:
    popad
    ret

