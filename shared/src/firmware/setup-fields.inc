post_ui_setup_selection_bar:
    pushad
    mov bp, cx
.row:
    mov cx, bp
.cell:
    mov ah, bh
    mov al, ' '
    call post_ui_setup_color
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

post_ui_setup_choice_highlight:
    cmp bh, 0x70
    jne .done
    pushad
    sub di, 2
    mov cx, UI_POPUP_WIDTH - 2
    mov dx, 1
    call post_ui_setup_selection_bar
    popad
.done:
    ret

post_ui_setup_field_highlight:
    pushad
    cmp byte [fs:U_FOCUS], 1
    jne .done
    mov cl, [fs:U_FIELD]
    call post_ui_setup_field_available
    jc .done
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_highlight
    call post_ui_chipset_ui_row
    imul di, 160
    add di, (UI_VALUE_COL - 1) * 2
    mov cx, UI_VALUE_WIDTH + 2
    jmp .paint
.ordinary_highlight:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    jne .non_pnp_highlight
    movzx di,cl
    add di,5
    imul di,160
    add di,(UI_VALUE_COL-1)*2
    mov cx,UI_VALUE_WIDTH+2
    jmp .paint
.non_pnp_highlight:
%endif
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
    movzx di, byte [POST_UI_DATA:si + bx]
    imul di, 160
    add di, (UI_LABEL_COL - 1) * 2
    mov cx, UI_POPUP_WIDTH + 1
    jmp .paint
.value:
    movzx di, byte [POST_UI_DATA:si + bx]
    imul di, 160
    add di, (UI_VALUE_COL - 1) * 2
    mov cx, UI_VALUE_WIDTH + 2
.paint:
    mov dx, 1
    mov bh, 0x1F
    call post_ui_setup_selection_bar
.done:
    popad
    ret

