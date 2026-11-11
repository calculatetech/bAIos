post_ui_setup_restore_text:
    push fs
    push gs
    mov byte [fs:U_THEME_ACTIVE], 0
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ax, 0x1202
    mov bl, 0x30
    int 0x10
    mov ax, 0x0003           ; Restore retained 80x25 / 8x16 font before boot.
    int 0x10
    mov ax, 0x1114
    xor bx, bx
    int 0x10
    mov ax, 0x1003
    mov bx, 1              ; Restore normal POST/OS text blink behavior.
    int 0x10
    mov ax,0x0500
    int 0x10
    pop gs
    pop fs
    cld
    ret

; AH selects Left/Right. Non-clock edits stay in the draft, not active state.
post_ui_setup_change:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    je post_ui_pnp_ui_change
%endif
    cmp byte [fs:U_PAGE], 0
    jne .non_clock
    xor byte [fs:U_CLOCK24], 1
    ret
.non_clock:
    cmp byte [fs:U_PAGE], 5
    je post_ui_chipset_ui_change
    cmp byte [fs:U_PAGE], 3
    je post_ui_ports_ui_change
    mov dl, 1
    cmp ah, 0x4B
    jne .field
    mov dl, -1
.field:
    mov bx, U_TYPES
    mov cl, [fs:U_FIELD]
    mov ch, 5
    cmp byte [fs:U_PAGE], 1
    jne .boot
    cmp cl, 2
    jae .hdd
    mov al, [fs:bx]
    test cl, cl
    jnz .low
    shr al, 4
.low:
    and al, 15
    call .cycle
    test cl, cl
    jnz .b
    shl al, 4
    and byte [fs:bx], 15
    or [fs:bx], al
    ret
.b:
    and byte [fs:bx], 0xF0
    or [fs:bx], al
    ret
.hdd:
    cmp cl, BOARD_ATA_DEVICE_COUNT+4
    jne .fdc
    mov bx, U_SWAP
    mov ch, 1
    jmp .enum
.fdc:
    cmp cl, BOARD_ATA_DEVICE_COUNT+3
    jne .ide
    mov bx, U_PORTS+P_FLOPPY
    mov ch, 1
    jmp .enum
.ide:
    cmp cl, BOARD_ATA_DEVICE_COUNT+2
    jne .device_policy
    call post_ui_setup_ide_controller_parameters
    mov ch,cl
    dec ch
    jmp .enum
.device_policy:
    mov al,cl
    sub al,2
    call post_ui_ide_ui_enable_index
.hdd_limit:
    mov ch, 1
    jmp .enum
.boot:
    push dx
    call post_ui_setup_boot_parameters
    pop dx
    mov ch, cl
    dec ch
.enum:
    mov al, [fs:bx]
.candidate:
    call .cycle

    call post_ui_setup_enum_store
    ret
.cycle:
    add al, dl
    cmp al, 0xFF
    jne .upper
    mov al, ch
.upper:
    cmp al, ch
    jbe .done
    xor al, al
.done:
    ret

post_ui_setup_enum_store:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    je post_ui_pnp_ui_commit
%endif
    pushf
    pushad
    cmp byte [fs:U_PAGE],1
    jne .boot
    cmp byte [fs:U_IDE_DEVICE],BOARD_ATA_DEVICE_COUNT-1
    ja .controller
    popad
    popf
    jmp post_ui_ide_ui_store
.controller:
%ifdef BOARD_IDE_SECONDARY_DISABLE_POLICY
    cmp byte [fs:U_FIELD],BOARD_ATA_DEVICE_COUNT+2
    jne .boot
    popad
    popf
    jmp post_ui_setup_ide_controller_store
%endif
.boot:
%ifdef BOARD_PORTS_SETUP_COMMIT
    cmp byte [fs:U_PAGE],3
    jne .ordinary_store
    popad
    popf
    jmp post_ui_ui_board_ports_setup_commit
.ordinary_store:
%endif
    cmp byte [fs:U_PAGE], 2
    jne .store
    cmp byte [fs:U_FIELD], 4
    jae .store
    test al, al
    jz .store
    movzx dx, byte [fs:U_FIELD]
    xor di, di
.find:
    mov si, di
    shl si, 1
    mov si, [POST_UI_DATA:u_boot_pointers+si]
    cmp al, [fs:si]
    je .move
    inc di
    cmp di, 4
    jb .find
    jmp .store
.move:
    mov si, di
    shl si, 1
    mov si, [POST_UI_DATA:u_boot_pointers+si]
    cmp di, dx
    je .store
    jb .left
    dec di
    jmp .copy
.left:
    inc di
.copy:
    mov bx, di
    shl bx, 1
    mov bx, [POST_UI_DATA:u_boot_pointers+bx]
    mov ah, [fs:bx]
    mov [fs:si], ah
    jmp .move
.store:
    popad
    popf
    mov [fs:bx], al
    ret

; All saved boot targets share the existing enum popup and quick-change path.
post_ui_setup_boot_parameters:
    movzx bx, byte [fs:U_FIELD]
    shl bx, 1
    mov bx, [POST_UI_DATA:u_boot_pointers + bx]
    mov si,u_post_delay_values
    mov cx,3
    cmp byte [fs:U_FIELD],POST_DELAY_FIELD
    je .done
%ifdef BOARD_PCI_VIDEO_ORDER
    mov si,u_video_order_values
    mov cx,2
    cmp byte [fs:U_FIELD],VIDEO_ORDER_FIELD
    je .done
%endif
    mov si, u_boot_values
    mov cx, 5
    cmp byte [fs:U_FIELD], 4
    jb .done
    mov si, u_seek_values
    mov cx, 2
    cmp byte [fs:U_FIELD], 6
    jne .done
    mov si, u_halt_values
    mov cx, 3
.done:
    ret

; Allocated targets remain selectable; post_ui_setup_enum_store moves their slots.
post_ui_setup_boot_choice_valid:
    clc
    ret

; Shared presentation; the board declares storage and owns channel hardware.
post_ui_setup_ide_controller_parameters:
    mov bx,U_IDE
    mov si,u_seek_values
    mov cx,2
%ifdef BOARD_IDE_SECONDARY_DISABLE_POLICY
    xor al,al
    cmp byte [fs:bx],0
    jne .enabled
    inc al
    jmp .selected
.enabled:
    test byte [fs:U_CHIP+(BOARD_IDE_SECONDARY_DISABLE_POLICY-C_CHIP)],BOARD_IDE_SECONDARY_DISABLE_MASK
    jz .selected
    mov al,2
.selected:
    mov bx,U_CHIP_VALUE
    mov [fs:bx],al
    mov si,u_ide_controller_choices
    mov cx,3
%endif
    ret
%ifdef BOARD_IDE_SECONDARY_DISABLE_POLICY
post_ui_setup_ide_controller_store:
    pushf
    pushad
    cmp al,2
    ja .done
    and byte [fs:U_CHIP+(BOARD_IDE_SECONDARY_DISABLE_POLICY-C_CHIP)],~BOARD_IDE_SECONDARY_DISABLE_MASK
    mov byte [fs:U_IDE],0
    cmp al,1
    je .done
    mov byte [fs:U_IDE],1
    cmp al,2
    jne .done
    or byte [fs:U_CHIP+(BOARD_IDE_SECONDARY_DISABLE_POLICY-C_CHIP)],BOARD_IDE_SECONDARY_DISABLE_MASK
.done:
    popad
    popf
    ret
%endif

; Enter opens the complete enum. Arrows still offer the normal quick change.
post_ui_setup_choices:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    je post_ui_pnp_ui_choices
%endif
    cmp byte [fs:U_PAGE], 5
    je post_ui_chipset_ui_choices
    cmp byte [fs:U_PAGE], 3
    je post_ui_ports_ui_choices
    pushad
    cmp byte [fs:U_PAGE], 0
    jne .non_clock
    mov bx, U_CLOCK24
    mov si, u_clock_formats
    mov cx, 2
    jmp .enum
.non_clock:
    mov bx, U_TYPES
    mov si, u_floppies
    mov cx, 6
    mov dl, [fs:U_FIELD]
    cmp byte [fs:U_PAGE], 1
    jne .boot
    cmp dl, 2
    jb .value
    cmp dl, BOARD_ATA_DEVICE_COUNT+4
    jne .fdc
    mov bx, U_SWAP
    mov si, u_seek_values
    mov cx, 2
    jmp .enum
.fdc:
    cmp dl, BOARD_ATA_DEVICE_COUNT+3
    jne .ide
    mov bx, U_PORTS+P_FLOPPY
    mov si, u_seek_values
    mov cx, 2
    jmp .enum
.ide:
    cmp dl, BOARD_ATA_DEVICE_COUNT+2
    jne .device_policy
    call post_ui_setup_ide_controller_parameters
    jmp .enum
.device_policy:
    mov al,dl
    sub al,2
    call post_ui_ide_ui_enable_index
.hdd:
    mov si, u_hdd_values
    mov cx, 2
    jmp .enum
.boot:
    call post_ui_setup_boot_parameters
.enum:
    mov dl, 2
.value:
    mov al, [fs:bx]
    cmp dl, 2
    je .selected
    test dl, dl
    jnz .low
    shr al, 4
.low:
    and al, 15
.selected:
    movzx bp, al
.draw:
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_draw
    call post_ui_chipset_ui_choice_draw
    jc .wait
.ordinary_draw:
    call post_ui_setup_modal_footer
    pushad
    mov di, 8 * 160 + UI_POPUP_COL * 2
    mov ax, 0x1E20
    mov dx, 15
.clear:
    mov cx, UI_POPUP_WIDTH
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    add di, (80 - UI_POPUP_WIDTH) * 2
    dec dx
    jnz .clear
    ui_text 8, UI_POPUP_TEXT, u_choices, 0x1B
    popad
    pushad
    xor dx, dx
.item:
    mov di, dx
    add di, 10
    imul di, di, 160
    add di, UI_POPUP_TEXT * 2
    push bx
    mov bx, dx
    shl bx, 1
    push si
    mov si, [si + bx]
    mov bh, 0x17
    cmp dx, bp
    jne .text
    mov bh, 0x70
.text:
    call post_ui_setup_choice_highlight
    call post_ui_setup_text
    pop si
    pop bx
    inc dx
    cmp dx, cx
    jb .item
    ui_text 22, UI_POPUP_TEXT, u_choices_keys, 0x1B
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
    jmp .draw
.arrows:
    cmp ah, 0x48
    je .previous
    cmp ah, 0x4B
    je .previous
    cmp ah, 0x50
    je .next
    cmp ah, 0x4D
    jne .wait
.next:
    inc bp
    cmp bp, cx
    jb .choice_check
    xor bp, bp
    jmp .choice_check
.previous:
    test bp, bp
    jnz .decrement
    mov bp, cx
.decrement:
    dec bp
.choice_check:
    cmp byte [fs:U_PAGE], 3
    jne .draw
    push ax
    mov ax, bp
    call post_ui_ports_ui_choice_valid
    pop ax
    jnc .draw
.skip_choice:
    cmp ah, 0x48
    je .previous
    cmp ah, 0x4B
    je .previous
    jmp .next
.apply:
    mov ax, bp

    cmp dl, 2
    je .store
    test dl, dl
    jnz .b
    shl al, 4
    and byte [fs:bx], 15
    or [fs:bx], al
    jmp .done
.b:
    and byte [fs:bx], 0xF0
    or [fs:bx], al
    jmp .done
.store:
    call post_ui_setup_enum_store
    cmp byte [fs:U_PAGE], 5
    jne .done
    call post_ui_chipset_ui_commit
.done:
    popad
    ret

