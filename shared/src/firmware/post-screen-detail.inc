post_ui_post_message_cursor:
    pushf
    pushad
    push es
    push fs
    push gs
    mov ax, 0xB800
    mov es, ax
    mov di, 22*160
    mov ax, 0x0720
    mov cx, 160
    cld
    rep stosw               ; A new notice replaces only the two message rows.
    mov dx, 0x1603
    xor bx, bx
    mov ah, 2
    int 0x10
    pop gs
    pop fs
    pop es
    popad
    popf
    ret

; DX is a validated add-in ROM segment. Emit every record; scroll this group.
post_ui_post_ui_rom:
    pushad
    push ds
    push es
    mov ds, dx
    movzx bx, byte [2]
    shl bx, 5
    post_ui_data_segment
    call post_ui_post_rom_state
    push ax
    mov ax, 0xB800
    mov es, ax
    movzx ax, byte [fs:P_ROM_COUNT]
    cmp ax, 3
    jb .row
    push ds
    push es
    pop ds
    mov si, 20*160
    mov di, 19*160
    mov cx, 2*80
    cld
    rep movsw
    mov ax, 0x0720
    mov cx, 80
    rep stosw
    pop ds
    mov ax, 2
.row:
    add ax, 19
    imul ax, 160
    mov di, ax
    add di, 3*2
    mov al, dh
    call post_ui_setup_hex8
    mov al, dl
    call post_ui_setup_hex8
    mov ax, 0x0768
    stosw
    add di, 16 ; State at column16, after the address and spacing.
    pop ax
    call post_ui_post_rom_state_text
    inc byte [fs:P_ROM_COUNT]
    mov di, 18*160+24*2
    call post_ui_post_clear_value
    movzx eax, byte [fs:P_ROM_COUNT]
    call post_ui_setup_number
    ui_text 18, 28, u_post_detected, 7
    pop es
    pop ds
    popad
    ret

; DX=start segment, BX=extent in paragraphs. AL=any state, AH=all state:
; bit0 shadowed, bit1 cache eligible, bit2 uncertain primary policy.
; Read configuration only. Sample every2KiB, including the final short block.
post_ui_post_rom_state_text:
    push ax
    mov si, u_post_unshadowed
    test al, 1
    jz .shadow
    mov si, u_post_partial_shadow
    test ah, 1
    jz .shadow
    mov si, u_post_shadowed
.shadow:
    mov bh, 7
    call .advance
    mov si, u_post_separator
    call .advance
    pop ax
    mov si, u_post_unknown_cache
    test al, 4
    jnz .cache
    mov si, u_post_uncached
    test al, 2
    jz .cache
    mov si, u_post_partial_cache
    test ah, 2
    jz .cache
    mov si, u_post_cached
.cache:
    jmp post_ui_setup_text
.advance:
    call post_ui_setup_text
    push ax
    push si
.length:
    lodsb
    test al, al
    jz .done
    add di, 2
    jmp .length
.done:
    pop si
    pop ax
    ret

%ifdef EMULATOR_CHIPSET_POST_UI
post_ui_post_ui_capture:
%ifdef EMULATOR_CHIPSET_PREVIEW
.hold:
    sti
    hlt
    jmp .hold
%else
    mov dx, 0x03DA
    mov cx, 2
.low:
    in al, dx
    test al, 8
    jnz .low
.high:
    in al, dx
    test al, 8
    jz .high
    loop .low
    call post_ui_setup_test_snapshot
    call post_ui_setup_test_dump
    mov al, 0x67
    call post_ui_emulator_exit
    jmp post_ui_hard_halt
%endif
%endif

