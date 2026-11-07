post_ui_ide_ui_record:
    movzx bx, byte [fs:U_IDE_DEVICE]
    imul bx, IDE_RECORD_SIZE
    add bx, U_IDE + 1
    mov si, bx
    ret
post_ui_ide_ui_enable_pointer:
    push ax
    mov al,[fs:U_IDE_DEVICE]
    call post_ui_ide_ui_enable_index
    pop ax
    ret
post_ui_ide_ui_enable_index:
    movzx bx,al
%if BOARD_ATA_DEVICE_COUNT = 4
    cmp bx,2
    jb .base
    add bx,U_IDE+IDE_ENABLE_EXTRA-2
    ret
.base:
%endif
    test bx,bx
    mov bx,U_HDD
    jz .done
    mov bx,U_SLAVE
.done:
    ret

; None is UI-only value49. CMOS keeps the existing enable flag and type0..48.
post_ui_ide_ui_type_value:
    push bx
    call post_ui_ide_ui_record
    mov al, [fs:bx + IDE_TYPE]
    call post_ui_ide_ui_enable_pointer
    cmp byte [fs:bx], 0
    jne .done
    mov al, 49
.done:
    pop bx
    ret

; Enum parameters share the existing popup. Numeric/type forms are bounded.
post_ui_ide_ui_parameters:
    call post_ui_ide_ui_record
    mov al, [fs:U_FIELD]
    test al, al
    jz .enabled
    cmp al, 7
    je .translation
    cmp al, 8
    je .block
%ifdef BOARD_ATA_PIO_POLICY
    cmp al,11
    je .pio
%endif
%ifdef BOARD_IDE_32BIT_POLICY
    cmp al,10
    je .dword
%endif
    add bx, IDE_EDD_OFF
    mov al,[fs:bx]
    xor al,1
    mov si, u_seek_values
    mov cx, 2
    jmp .ready
.enabled:
    call post_ui_ide_ui_enable_pointer
    mov al,[fs:bx]
    mov si, u_seek_values
    mov cx, 2
    jmp .ready
.translation:
    add bx, IDE_TRANSLATION
    movzx bx,byte [fs:bx]
    mov al,[POST_UI_DATA:ide_translation_to_display+bx]
    mov si, u_ide_translation_choices
    mov cx, 4
    jmp .ready
.block:
    add bx, IDE_BLOCK
    mov al,[fs:bx]
    cmp al,2
    jb .block_special
    sub al,2
    jmp .block_ready
.block_special:
    add al,7
.block_ready:
    mov si, u_ide_block_choices
    mov cx, 9
    jmp .ready
%ifdef BOARD_IDE_32BIT_POLICY
.dword:
    mov cl,[fs:U_IDE_DEVICE]
    mov al,[fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)]
    shr al,cl
    and al,1
    mov si,u_seek_values
    mov cx,2
    jmp .ready
%endif
%ifdef BOARD_ATA_PIO_POLICY
.pio:
    call post_ui_ide_ui_pio_value
    test al,al
    jnz .pio_position
    mov al,6
.pio_position:
    dec al
    mov si,u_ide_pio_choices
    mov cx,6
%endif
.ready:
    mov bx,U_CHIP_VALUE
    mov [fs:bx],al
    ret

; AL is a display position. The saved record retains its existing encodings.
post_ui_ide_ui_store:
    pushf
    pushad
    mov dl,al
    call post_ui_ide_ui_record
    cmp byte [fs:U_FIELD],0
    je .enabled
    cmp byte [fs:U_FIELD],7
    je .translation
    cmp byte [fs:U_FIELD],8
    je .block
%ifdef BOARD_ATA_PIO_POLICY
    cmp byte [fs:U_FIELD],11
    je .pio
%endif
%ifdef BOARD_IDE_32BIT_POLICY
    cmp byte [fs:U_FIELD],10
    je .dword
%endif
    xor al,1
    mov [fs:bx+IDE_EDD_OFF],al
    jmp .done
.enabled:
    call post_ui_ide_ui_enable_pointer
    mov [fs:bx],al
    jmp .done
.translation:
    movzx di,al
    mov al,[POST_UI_DATA:ide_translation_from_display+di]
    mov [fs:bx+IDE_TRANSLATION],al
    jmp .done
.block:
    cmp al,7
    jae .block_special
    add al,2
    jmp .block_ready
.block_special:
    sub al,7
.block_ready:
    mov [fs:bx+IDE_BLOCK],al
    jmp .done
%ifdef BOARD_IDE_32BIT_POLICY
.dword:
    mov cl,[fs:U_IDE_DEVICE]
    mov al,1
    shl al,cl
    not al
    and [fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)],al
    mov al,dl
    shl al,cl
    or [fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)],al
    jmp .done
%endif
%ifdef BOARD_ATA_PIO_POLICY
.pio:
    mov cl,[fs:U_IDE_DEVICE]
    shl cl,1
    mov al,3
    shl al,cl
    not al
    and [fs:U_CHIP+(BOARD_ATA_PIO_POLICY-C_CHIP)],al
    mov al,dl
    inc al
    cmp al,6
    jb .pio_encoded
    xor al,al
.pio_encoded:
    mov ah,al
    and al,3
    shl al,cl
    or [fs:U_CHIP+(BOARD_ATA_PIO_POLICY-C_CHIP)],al
    shr cl,1
    mov al,1
    shl al,cl
    not al
    and [fs:U_CHIP+(BOARD_ATA_PIO_POLICY_HIGH-C_CHIP)],al
    shr ah,2
    shl ah,cl
    or [fs:U_CHIP+(BOARD_ATA_PIO_POLICY_HIGH-C_CHIP)],ah
%endif
.done:
    popad
    popf
    ret

post_ui_ide_ui_select:
    cmp byte [fs:U_FIELD], 1
    je post_ui_ide_ui_types
    cmp byte [fs:U_FIELD], 2
    jb .enum
    cmp byte [fs:U_FIELD], 6
    jbe post_ui_ide_ui_number
.enum:
    pushad
    call post_ui_ide_ui_parameters
    movzx bp, byte [fs:bx]
    mov dl, 2
    jmp post_ui_setup_choices.draw ; Same popup/input/commit owner and stack contract.

post_ui_ide_ui_change:
    pushad
    mov dl, 1
    cmp ah, 0x4B
    jne .field
    mov dl, -1
.field:
    cmp byte [fs:U_FIELD], 1
    je .type
    cmp byte [fs:U_FIELD], 2
    jb .enum
    cmp byte [fs:U_FIELD], 6
    jbe .number
.enum:
    push dx
    call post_ui_ide_ui_parameters
    pop dx
    mov al, [fs:bx]
    add al, dl
    cmp al, 0xFF
    jne .upper
    mov al, cl
    dec al
.upper:
    cmp al, cl
    jb .store
    xor al, al
.store:
    call post_ui_ide_ui_store
    jmp .done
.type:
    call post_ui_ide_ui_record
    call post_ui_ide_ui_type_value
.cycle:
    add al, dl
    cmp al, 0xFF
    jne .type_upper
    mov al, 49
.type_upper:
    cmp al, 49
    jbe .type_valid
    xor al, al
.type_valid:
    cmp al, 49
    je .type_apply
    call post_ui_ide_type_valid
    jc .cycle
.type_apply:
    call post_ui_ide_ui_set_type
    jmp .done
.number:
    ; Numeric fields use the same validated editor, not unchecked +/- writes.
.done:
    popad
    ret

; AL=selected type. Preserve its numeric identity even for equal geometries.
post_ui_ide_ui_set_type:
    push bx
    call post_ui_ide_ui_enable_pointer
    cmp al, 49
    jne .enabled
    mov byte [fs:bx], 0
    pop bx
    ret
.enabled:
    mov byte [fs:bx], 1
    pop bx
    mov [fs:bx + IDE_TYPE], al
    test al, al
    jz .done
    cmp al, 48
    je .done
    movzx si, al
    dec si
    shl si, 3
    add si, ide_type_table
    lea di, [bx + IDE_CYLINDERS]
    mov cx, 8
.byte:
    mov al, [POST_UI_DATA:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
.done:
    ret

post_ui_ide_ui_draw:
    pushad
    movzx bx,byte [fs:U_IDE_DEVICE]
    shl bx,1
    mov si,[POST_UI_DATA:u_ide_policy_labels+bx]
    mov di, 3 * 160 + 23 * 2
    mov bh, 0x0B
    call post_ui_setup_text
    ui_text 4, UI_LABEL_COL, u_ide_disk_group, 0x0B
    ui_text 13, UI_LABEL_COL, u_ide_transfer_group, 0x0B
    xor bp, bp
.field:
    mov bx, bp
    shl bx, 1
    mov si, [u_ide_labels + bx]
    call .field_position
    add di, UI_LABEL_COL * 2
    mov bh, 7
    mov cx, bp
    call post_ui_setup_field_available
    jnc .label
    mov bh, 8
.label:
    call post_ui_setup_text
    call .field_position
    add di, UI_VALUE_COL * 2
    mov cx, bp
    call post_ui_setup_field_color
    push bx
    call post_ui_ide_ui_record
    cmp bp, 0
    je .enable
    cmp bp, 1
    je .type
    cmp bp, 7
    je .translation
    cmp bp, 8
    je .block
    cmp bp, 9
    je .edd
%ifdef BOARD_ATA_PIO_POLICY
    cmp bp,11
    je .pio
%endif
%ifdef BOARD_IDE_32BIT_POLICY
    cmp bp,10
    je .dword
%endif
    mov bx, bp
    sub bx, 2
    shl bx, 1
    mov bx, [u_ide_number_offsets + bx]
    movzx eax, word [fs:si + bx]
    cmp bp, 3
    je .byte_number
    cmp bp, 4
    jne .number
.byte_number:
    and eax, 255
.number:
    pop bx
    call post_ui_setup_colored_number
    jmp .next
.enable:
    call post_ui_ide_ui_enable_pointer
    movzx bx, byte [fs:bx]
    mov si, u_seek_values
    jmp .enum
.type:
    call post_ui_ide_ui_type_value
    pop bx
    call post_ui_ide_ui_type_text
    jmp .next
.translation:
    movzx bx, byte [fs:si + IDE_TRANSLATION]
    mov si, u_ide_translation_values
    jmp .enum
.block:
    movzx bx, byte [fs:si + IDE_BLOCK]
    mov si, u_ide_block_values
    jmp .enum
.edd:
    movzx bx, byte [fs:si + IDE_EDD_OFF]
    mov si, u_ide_edd_values
    jmp .enum
%ifdef BOARD_IDE_32BIT_POLICY
.dword:
    mov cl,[fs:U_IDE_DEVICE]
    mov bl,[fs:U_CHIP+(BOARD_IDE_32BIT_POLICY-C_CHIP)]
    shr bl,cl
    and bx,1
    mov si,u_seek_values
    jmp .enum
%endif
%ifdef BOARD_ATA_PIO_POLICY
.pio:
    call post_ui_ide_ui_pio_value
    movzx bx,al
    mov si,u_ide_pio_values
%endif
.enum:
    shl bx, 1
    mov si, [si + bx]
    pop bx
    call post_ui_setup_text
.next:
    inc bp
    cmp bp, IDE_FIELD_COUNT
    jb .field
    popad
    ret
.field_position:
    mov di, bp
    movzx di, byte [POST_UI_DATA:u_ide_rows + di]
    imul di, 160
    ret

post_ui_setup_colored_number:
    pushad
    call post_ui_setup_number
    mov cx, 5
.color:
    mov ah, bh
    mov al, ' '
    call post_ui_setup_color
    mov [es:di + 1], ah
    add di, 2
    loop .color
    popad
    ret

post_ui_ide_ui_type_text:
    pushad
    mov si, u_ide_none
    cmp al, 49
    je .text
    mov si, u_auto
    test al, al
    jz .text
    mov si, u_ide_user
    cmp al, 48
    je .text
    mov si, u_ide_type_prefix
    call post_ui_setup_text
    movzx eax, al
    add di, 5 * 2
    call post_ui_setup_colored_number
    jmp .done
.text:
    call post_ui_setup_text
.done:
    popad
    ret

;12-row paged list. Arrow/Page keys can reach every valid numbered type.
post_ui_ide_ui_types:
    pushad
    call post_ui_ide_ui_type_value
    movzx bp, al
.draw:
    call post_ui_setup_draw
    call post_ui_setup_modal_footer
    mov di, 5 * 160 + UI_POPUP_COL * 2
    mov ax, 0x1E20
    mov dx, 17
.clear:
    mov cx, UI_POPUP_WIDTH
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    add di, (80 - UI_POPUP_WIDTH) * 2
    dec dx
    jnz .clear
    ui_text 5, UI_POPUP_TEXT, u_ide_type_menu, 0x1B
    ui_text 6, UI_POPUP_TEXT, u_ide_type_columns, 0x1B
    mov ax, bp
    xor dx, dx
    mov cx, 12
    div cx
    imul dx, ax, 12
    mov si, dx
    xor cx, cx
.item:
    mov ax, si
    add ax, cx
    cmp ax, 49
    ja .items_done
    push si
    mov bx, cx
    imul di, bx, 160
    add di, 7 * 160 + UI_POPUP_TEXT * 2
    mov bh, 0x17
    cmp ax, bp
    jne .color
    mov bh, 0x70
.color:
    call post_ui_setup_choice_highlight
    cmp al, 49
    je .valid
    call post_ui_ide_type_valid
    jnc .valid
    mov si, u_ide_reserved
    call post_ui_setup_text
    jmp .row_done
.valid:
    call post_ui_ide_ui_type_text
    test al, al
    jz .row_done
    cmp al, 48
    jae .row_done
    mov dx, bx ; Keep the selected-row color while resolving the type table.
    movzx bx, al
    dec bx
    shl bx, 3
    add bx, ide_type_table
    mov si, bx
    mov bx, dx
    add di, UI_TYPE_WIDTH * 2
    movzx eax, word [POST_UI_DATA:si]
    call post_ui_setup_colored_number
    add di, UI_GEOMETRY_WIDTH * 2
    movzx eax, byte [POST_UI_DATA:si + 2]
    call post_ui_setup_colored_number
    add di, UI_GEOMETRY_WIDTH * 2
    movzx eax, byte [POST_UI_DATA:si + 3]
    call post_ui_setup_colored_number
.row_done:
    pop si
    inc cx
    cmp cx, 12
    jb .item
.items_done:
    ui_text 20, UI_POPUP_TEXT, u_choices_keys, 0x1B
    ui_text 21, UI_POPUP_TEXT, u_ide_page_keys, 0x1B
.wait:
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
    mov dl, 1
    cmp ah, 0x50
    je .move
    cmp ah, 0x4D
    je .move
    cmp ah, 0x48
    je .previous
    cmp ah, 0x4B
    je .previous
    cmp ah, 0x51
    je .page_down
    cmp ah, 0x49
    jne .wait
    sub bp, 12
    jnc .bounded
    xor bp, bp
    jmp .bounded
.page_down:
    add bp, 12
    cmp bp, 49
    jbe .bounded
    mov bp, 49
.bounded:
    mov dl, 1
    jmp .validate
.previous:
    mov dl, -1
.move:
    movsx ax, dl
    add bp, ax
    cmp bp, 0xFFFF
    jne .upper
    mov bp, 49
.upper:
    cmp bp, 49
    jbe .validate
    xor bp, bp
.validate:
    mov ax, bp
    cmp al, 49
    je .draw
    call post_ui_ide_type_valid
    jc .move
    jmp .draw
.apply:
    call post_ui_ide_ui_record
    mov ax, bp
    call post_ui_ide_ui_set_type
.done:
    popad
    ret

; Decimal editor for User geometry/metadata. Esc or invalid input writes nothing.
post_ui_ide_ui_number:
    pushad
    call post_ui_ide_ui_record
    cmp byte [fs:bx + IDE_TYPE], 48
    jne post_ui_setup_number_editor.done
    movzx bp, byte [fs:U_FIELD]
    sub bp, 2
    shl bp, 1
    mov di, [POST_UI_DATA:u_ide_number_offsets + bp]
    add bx, di
    jmp post_ui_setup_number_editor
%ifdef BOARD_PNP_SUPPORT
post_ui_pnp_ui_number:
    pushad
    call post_ui_pnp_ui_parameters
    mov bp,10
    test byte [fs:U_FIELD],1
    jnz post_ui_setup_number_editor
    mov bp,12
%endif
post_ui_setup_number_editor:
    mov byte [fs:U_POSITION], 0
    mov byte [fs:U_BUFFER], 0
    push bx
    call post_ui_setup_draw
    call post_ui_setup_modal_footer
    ui_text 22, UI_LABEL_COL, u_ide_number_prompt, 0x1B
    pop bx
.draw:
    mov di, 22 * 160 + UI_VALUE_COL * 2
    mov ax, 0x1E20
    mov cx, 6
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    mov di, 22 * 160 + UI_VALUE_COL * 2
    mov si, U_BUFFER
    push bx
    mov bh, 0x1F
    call post_ui_setup_value
    pop bx
.wait:
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
    cmp al, 8
    je .back
    cmp al, '0'
    jb .wait
    cmp al, '9'
%ifdef BOARD_PNP_SUPPORT
    jbe .accepted_digit
    cmp bp,12
    jne .wait
    and al,0xDF
    cmp al,'A'
    jb .wait
    cmp al,'F'
%endif
    ja .wait
.accepted_digit:
    movzx si, byte [fs:U_POSITION]
    cmp si, 5
    jae .wait
    mov [fs:U_BUFFER + si], al
    inc si
    mov ax, si
    mov [fs:U_POSITION], al
    mov byte [fs:U_BUFFER + si], 0
    jmp .draw
.back:
    cmp byte [fs:U_POSITION], 0
    je .wait
    dec byte [fs:U_POSITION]
    movzx si, byte [fs:U_POSITION]
    mov byte [fs:U_BUFFER + si], 0
    jmp .draw
.apply:
    xor eax, eax
    xor si, si
    cmp byte [fs:U_POSITION], 0
    je .done
.digit:
    movzx edx, byte [fs:U_BUFFER + si]
    sub edx, '0'
%ifdef BOARD_PNP_SUPPORT
    cmp bp,12
    jne .decimal_digit
    cmp dl,9
    jbe .hex_digit
    sub dl,7
.hex_digit:
    shl eax,4
    jmp .add_digit
.decimal_digit:
%endif
    imul eax, 10
.add_digit:
    add eax, edx
    inc si
    movzx dx, byte [fs:U_POSITION]
    cmp si, dx
    jb .digit
    movzx edx, word [POST_UI_DATA:u_ide_number_max + bp]
    cmp eax, edx
    ja .bad
    cmp bp, 6
    jae .store
    test eax, eax
    jz .bad
.store:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    jne .ide_store
    mov dx,[fs:bx]
    mov [fs:bx],ax
    mov si,U_PNP
    call post_ui_pnp_settings_valid
    jnc .done
    mov [fs:bx],dx
    jmp .bad
.ide_store:
%endif
    cmp bp, 2
    je .byte_store
    cmp bp, 4
    je .byte_store
    mov [fs:bx], ax
    jmp .done
.byte_store:
    mov [fs:bx], al
    jmp .done
.bad:
    push bx
    ui_text 21, UI_LABEL_COL, u_ide_invalid, 0x0C
    pop bx
    jmp .wait
.done:
    popad
    ret

