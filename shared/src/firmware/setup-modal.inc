post_ui_setup_modal_footer:
    pushad
    mov di, 24 * 160
    mov ax, 0x0B20
    call post_ui_setup_color
    mov cx, 80
    rep stosw
    popad
    ret

