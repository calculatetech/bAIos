post_ui_ports_ui_parameters:
    movzx bx, byte [fs:U_FIELD]
%ifdef BOARD_PORTS_SETUP_PARAMETERS
    jmp post_ui_ui_board_ports_setup_parameters
%else
    mov cx, bx
    movzx cx, byte [POST_UI_DATA:ports_limits+bx]
    inc cx
    shl bx, 1
    mov si, [POST_UI_DATA:u_ports_values+bx]
    shr bx, 1
    add bx, U_PORTS
    ret
%endif

; AL=candidate. The same sibling rule governs arrows and popup navigation.
post_ui_ports_ui_choice_valid:
%ifdef BOARD_PORTS_SETUP_CHOICE_VALID
    jmp post_ui_ui_board_ports_setup_choice_valid
%else
    push bx
    movzx bx, byte [fs:U_FIELD]
    call post_ui_ports_ui_candidate
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
%endif

post_ui_ports_ui_choices:
    pushad
    call post_ui_ports_ui_parameters
    movzx bp, byte [fs:bx]
    mov dl, 2
    jmp post_ui_setup_choices.draw

post_ui_ports_ui_change:
    pushad
    mov dl, 1
    cmp ah, 0x4B
    jne .parameters
    mov dl, -1
.parameters:
    call post_ui_ports_ui_parameters
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
    call post_ui_ports_ui_choice_valid
    jc .cycle
%ifdef BOARD_PORTS_SETUP_COMMIT
    call post_ui_setup_enum_store
%else
    mov [fs:bx], al
%endif
    popad
    ret

post_ui_ports_ui_draw:
    pushad
    ui_text 3, 23, u_devices_title, 0x0B
    xor bp, bp
.field:
    mov cx,bp
    call post_ui_ports_ui_visible
    jc .next
    mov bx, bp
    shl bx, 1
    mov si, [POST_UI_DATA:u_ports_labels+bx]
    movzx di, byte [POST_UI_DATA:u_ports_rows+bp]
    imul di, 160
    add di, UI_LABEL_COL*2
    mov cx, bp
    call post_ui_setup_field_color
    and bh, 15
    call post_ui_setup_text
%ifdef BOARD_PORTS_SETUP_PARAMETERS
    mov bx,bp
    call post_ui_ui_board_ports_setup_parameters
    movzx bx,byte [fs:bx]
%else
    mov bx, bp
    shl bx, 1
    mov si, [POST_UI_DATA:u_ports_values+bx]
    movzx bx, byte [fs:U_PORTS+bp]
%endif
    shl bx, 1
    mov si, [POST_UI_DATA:si+bx]
    add di, (UI_VALUE_COL-UI_LABEL_COL)*2
    mov cx, bp
    call post_ui_setup_field_color
    call post_ui_setup_text
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

