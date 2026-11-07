    pushf
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    mov cx, 32
.poll:
    sti
    nop
    call post_keyboard_wait
    in al, KBC_STATUS
    and al, 0x21
    cmp al, 1
    jne .request
    loop .poll
.request:
    cmp byte [fs:S_SETUP_REQUEST], 1
    jne .done
    call post_entering_setup
    call setup_main
    xor ax, ax
    mov ds, ax
    mov byte [0x0400+KB_POST_STATE], 1
    call post_ui_begin
.done:
    pop fs
    pop es
    pop ds
    popad
    popf
    ret
