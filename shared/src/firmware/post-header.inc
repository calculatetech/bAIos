post_ui_post_header:
    pushad
    push ds
    push es
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov ax, 0x1F20
    mov cx, 80
    push ax
    call post_ui_setup_color
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
    call post_ui_setup_color
    stosw
    pop ax
    loop .date
    pop es
    pop ds
    popad
    ret

; Intel AP-485 reset signature, retained across software warm POST.
; Report the model, without deriving a core clock from a timing profile.
