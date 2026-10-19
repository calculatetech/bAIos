; Shared descriptor-driven chipset menu. Hardware policy stays in board-selected callbacks.
chipset_ui_count:
    movzx bx, byte [fs:U_CHIP_SCREEN]
    test bx, bx
    jnz .fields
    mov cl, CHIP_GROUP_COUNT
    ret
.fields:
    mov cl, [cs:chipset_group_counts+bx-1]
    ret

chipset_ui_descriptor:
    movzx bx, byte [fs:U_CHIP_SCREEN]
    dec bx
    shl bx, 1
    mov si, [cs:chipset_groups+bx]
    movzx bx, byte [fs:U_FIELD]
    imul bx, CHIP_FIELD_SIZE
    add si, bx
    ret

chipset_ui_available:
    push cx
    call chipset_ui_count
    mov al, cl
    pop cx
    cmp cl, al
    jae .bad
    cmp byte [fs:U_CHIP_SCREEN], 0
    je .good
    call chipset_ui_editable
    jc .bad
    ; L2 options stay editable before detection, so Setup remains reachable.
.good:
    clc
    ret
.bad:
    stc
    ret

chipset_ui_select:
    cmp byte [fs:U_CHIP_SCREEN], 0
    jne chipset_ui_choices
    mov al, [fs:U_FIELD]
    inc al
    mov [fs:U_CHIP_SCREEN], al
    mov byte [fs:U_FIELD], 0
    ret

; Descriptor: label,offset,shift,mask,count,values,help1,help2 (14 bytes).
%include BOARD_CHIPSET_SETUP_POLICY

chipset_ui_choices:
    mov cl, [fs:U_FIELD]
    call chipset_ui_editable
    jnc .open
    ret
.open:
    pushad
    call chipset_ui_parameters
    movzx bp, byte [fs:U_CHIP_VALUE]
    cmp cx, 10
    ja .paged
    mov dl, 2
    jmp setup_choices.draw
.paged:
    call setup_modal_footer
    pushad
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
    call chipset_ui_indicator
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
    call setup_choice_highlight
    call chipset_ui_option_text
    inc dx
    cmp dx, 12
    jb .item
.items_done:
    ui_text 22,UI_POPUP_TEXT,u_ide_page_keys,0x1B
    popad
.wait:
%ifdef EMULATOR_CHIPSET_TEST
    call chipset_test_capture_drain
%endif
    call setup_clock
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
    call setup_help
    pushad
    call setup_draw
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
    call chipset_ui_commit
.done:
    popad
    ret

; View: title,start,count,rows,headers. AX=index, BX=first, DL=page count.
chipset_ui_view:
    movzx bx, byte [fs:U_CHIP_SCREEN]
    dec bx
    movzx ax, byte [cs:chipset_first_view+bx]
    mov dl, [cs:chipset_view_counts+bx]
    mov bx, ax
    mov dh, dl
.next:
    mov si, ax
    shl si, 3
    add si, chipset_views
    dec dh
    jz .done
    mov dh, [cs:si+10]
    cmp [fs:U_FIELD], dh
    jb .done
    inc ax
    mov dh, bl
    add dh, dl
    sub dh, al
    jmp .next
.done:
    xor dh, dh
    ret

; Resolve the selected absolute field to its row; preserve caller registers.
chipset_ui_row:
    push ax
    push bx
    push dx
    push si
    cmp byte [fs:U_CHIP_SCREEN], 0
    jne .field
    movzx di, cl
    add di, 5
    jmp .done
.field:
    call chipset_ui_view
    movzx bx, cl
    sub bl, [cs:si+2]
    mov si, [cs:si+4]
    movzx di, byte [cs:si+bx]
.done:
    pop si
    pop dx
    pop bx
    pop ax
    ret

chipset_ui_page:
    pushad
    cmp byte [fs:U_CHIP_SCREEN], 0
    je .done
    mov bp, ax
    call chipset_ui_view
    cmp bp, 0x4900
    jb .done
    cmp bp, 0x4A00
    jae .next
    cmp ax, bx
    je .done
    sub si, 8
    jmp .select
.next:
    add bx, dx
    dec bx
    cmp ax, bx
    je .done
    add si, 8
.select:
    mov cl, [cs:si+2]
.available:
    call chipset_ui_available
    jnc .selected
    inc cl
    jmp .available
.selected:
    mov [fs:U_FIELD], cl
.done:
    popad
    ret

; EAX=current page, DL=total, DI=start, BH=colour. Existing decimal/text owners.
chipset_ui_indicator:
    pushad
    mov bp, di
    mov si, chip_page_prefix
    call setup_text
    add di, 5*2
    call setup_number
    add di, 2*2
    mov si, chip_page_slash
    call setup_text
    add di, 3*2
    movzx eax, dl
    call setup_number
    mov di, bp
    mov cx, 14
    mov dx, 1
    call setup_selection_bar
    popad
    ret

chipset_ui_draw:
    pushad
    mov di, 24*160+2*2
    mov ax, 0x0B20
    mov cx, 78
    push ax
    call setup_color
    rep stosw
    pop ax
    mov si, chip_page_keys
    cmp byte [fs:U_CHIP_SCREEN], 0
    jne .footer
    mov si, u_footer
.footer:
    mov di, 24*160+2*2
    mov bh, 0x0B
    call setup_text
    cmp byte [fs:U_CHIP_SCREEN], 0
    jne .fields
    ui_text 3,23,u_chip_title,0x0B
    xor bp, bp
.category:
    mov di, bp
    add di, 5
    imul di, 160
    add di, UI_LABEL_COL*2
    mov bx, bp
    shl bx, 1
    mov si, [cs:chipset_group_titles+bx]
    mov cx, bp
    call setup_field_color
    and bh, 15
    call setup_text
    add di, (UI_VALUE_COL-UI_LABEL_COL)*2
    mov si, u_chip_open
    mov cx, bp
    call setup_field_color
    call setup_text
    inc bp
    cmp bp, CHIP_GROUP_COUNT
    jb .category
    jmp .done
.fields:
    call chipset_ui_view
    push si
    sub ax, bx
    inc ax
    movzx eax, ax
    mov di, 3*160+62*2
    mov bh, 0x0B
    call chipset_ui_indicator
    mov di, 3*160+23*2
    mov si, [cs:si]
    call setup_text
    pop si
    push si
    mov si, [cs:si+6]
.header:
    movzx di, byte [cs:si]
    test di, di
    jz .headers_done
    imul di, 160
    add di, UI_LABEL_COL*2
    push si
    mov si, [cs:si+1]
    call setup_text
    pop si
    add si, 3
    jmp .header
.headers_done:
    pop si
    movzx dx, byte [cs:si+2]
    movzx cx, byte [cs:si+3]
    movzx bx, byte [fs:U_CHIP_SCREEN]
    dec bx
    shl bx, 1
    mov bp, [cs:chipset_groups+bx]
    imul bx, dx, CHIP_FIELD_SIZE
    add bp, bx
.field:
    push cx
    mov cx, dx
    call chipset_ui_row
    imul di, 160
    add di, UI_LABEL_COL*2
    mov si, [cs:bp]
    call setup_field_color
    and bh, 15
    call setup_text
    movzx bx, byte [cs:bp+2]
    mov cl, [cs:bp+3]
    mov al, [fs:U_CHIP+bx]
    shr al, cl
    and al, [cs:bp+4]
    movzx ax, al
    mov si, [cs:bp+7]
    add di, (UI_VALUE_COL-UI_LABEL_COL)*2
    mov cx, dx
    call setup_field_color
    call chipset_ui_option_text
    add bp, CHIP_FIELD_SIZE
    inc dx
    pop cx
    loop .field
.done:
    popad
    ret

%include BOARD_CHIPSET_CAS_SETUP

chipset_ui_help:
    pushad
    mov di, 17*160+23*2
    mov dx, 6
    mov ax, 0x1E20
.clear:
    mov cx, 55
    push ax
    call setup_color
    rep stosw
    pop ax
    add di, (80-55)*2
    dec dx
    jnz .clear
    cmp byte [fs:U_FOCUS], 0
    je .page
    cmp byte [fs:U_CHIP_SCREEN], 0
    jne .field
    movzx bx, byte [fs:U_FIELD]
    imul bx, 6
    mov si, chipset_group_help
    add si, bx
    jmp .topic
.field:
    call chipset_ui_descriptor
    mov bp, si
    mov si, [cs:bp]
    mov di, 18*160+25*2
    mov bh, 0x1E
    call setup_text
    mov si, [cs:bp+9]
    mov di, 19*160+25*2
    call setup_text
    mov si, [cs:bp+11]
    mov di, 20*160+25*2
    call setup_text
    jmp .done
.page:
    mov si, u_chip_help
.topic:
    mov bp, si
    mov si, [cs:bp]
    mov di, 18*160+25*2
    mov bh, 0x1E
    call setup_text
    mov si, [cs:bp+2]
    mov di, 19*160+25*2
    call setup_text
    mov si, [cs:bp+4]
    mov di, 20*160+25*2
    call setup_text
.done:
    popad
    ret
