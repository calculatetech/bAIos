; Presario VLSI and FDC37C661 adapters for the maintained generic services.
ide_apply_controller:
    pushf
    cli
    pushad
    mov dx, SUPERIO_INDEX
    mov al, 0x55
    out dx, al
    out dx, al
    xor al, al
    out dx, al
    inc dx
    in al, dx
    and al, 0xFE
    or al, [fs:C_IDE]
    out dx, al
    dec dx
    mov al, 0xAA
    out dx, al
    popad
    popf
    ret


floppy_controller_mode:
    ; OEM F000:8837-883B. Do not inherit reset-default DRATE input mode.
    mov dx, SUPERIO_INDEX
    mov al, 0x55
    out dx, al
    out dx, al
    mov al, 3
    out dx, al
    inc dx
    mov al, SUPERIO_FDC_MODE
    out dx, al
    dec dx
    mov al, 0xAA
    out dx, al
    mov dx, 0x03F3
    mov al, [fs:C_SWAP]      ; Enhanced TDR owns both drive and motor swapping.
    shl al, 5
    out dx, al
    ret

board_floppy_configure:
    ; OEM F000:347A-348B: FIFO on, 13-byte reserve, polling on, no implied seeks.
    ; Request DMA earlier than the old 8-byte reserve (physical ST1 overrun).
    mov al, 0x13
    call fdc_write
    xor al, al
    call fdc_write
    mov al, 0x0C
    call fdc_write
    xor al, al
    call fdc_write
    ret

board_floppy_perpendicular:
    ; Perpendicular recording is required for 2.88M, not for HD/DD.
    mov al, 0x12
    call fdc_write
    mov al, 0x80
    cmp byte [fs:F_RATE], 3
    jne .mode
    mov al, 0xBC
.mode:
    jmp fdc_write

board_sio_diagnostic_begin:
    mov dx, SUPERIO_INDEX
    mov al, 0x55
    out dx, al
    out dx, al
    ret
board_sio_diagnostic_index:
    mov al,cl
    ret
board_sio_diagnostic_end:
    mov al, 0xAA
    out dx, al
    ret

ports_apply:
    pushf
    cli
    pushad
    call load_bios_state
    mov dx, SUPERIO_INDEX
    mov al, 0x55
    out dx, al
    out dx, al
    xor al, al
    out dx, al
    inc dx
    in al, dx
    and al, 0xE7             ; Only floppy power/enable, never IDE or oscillator.
    cmp byte [fs:C_PORTS+5], 0
    je .fdc
    or al, 0x18
.fdc:
    out dx, al
    dec dx
    mov al, 1
    out dx, al
    inc dx
    in al, dx
    and al, 0x90             ; Board IRQ polarity and configuration read-enable.
    mov bl, [fs:C_PORTS+2]
    shl bl, 5
    or al, bl
    mov bl, [fs:C_PORTS+3]
    or al, bl
    test bl, bl
    jz .mode
    or al, 4
.mode:
    cmp byte [fs:C_PORTS+4], 0
    jne .parallel
    or al, 8
.parallel:
    out dx, al
    xor bx, bx
    mov al, [fs:C_PORTS]
    test al, al
    jz .uart_b
    dec al
    or al, 0x0C
    mov bl, al
.uart_b:
    mov al, [fs:C_PORTS+1]
    test al, al
    jz .uarts
    dec al
    or al, 0x0C
    shl al, 4
    or bl, al
.uarts:
    dec dx
    mov al, 2
    out dx, al
    inc dx
    mov al, bl
    out dx, al
    dec dx
    mov al, 0xAA
    out dx, al
    popad
    popf
    ret

ports_default db 1,0,1,2,0,1,1,1
ports_limits db 4,4,3,3,1,1,1,1

board_mouse_platform_read:
    out CHIPSET_CONFIG_ON, al
    mov al, KBC_PLATFORM_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    out CHIPSET_CONFIG_OFF, al
    ret

board_floppy_unit:
board_floppy_result:
board_floppy_dor:
    ret
ports_record_valid:
ports_ui_candidate:
    clc
    ret

ports_load_filter:
    mov byte [fs:C_PORTS+1],0
    ret
ports_save_filter:
    mov byte [fs:U_PORTS+1],0
    ret

ports_ui_available:
    cmp cl,4
    jne ports_ui_visible
    cmp byte [fs:U_PORTS+3],0
    je ports_ui_hidden
ports_ui_visible:
    cmp cl,1
    je ports_ui_hidden
    cmp cl,2
    je ports_ui_hidden
    cmp cl,5
    je ports_ui_hidden
    cmp cl,7
    je ports_ui_hidden
    clc
    ret
ports_ui_hidden:
    stc
    ret

post_memory_banks:
    pushad
    out CHIPSET_CONFIG_ON, al
    mov al, RAMCFG0_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov dl, al
    mov al, RAMCFG1_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov dh, al
    mov al, RAMSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov bl, al
    out CHIPSET_CONFIG_OFF, al
    xor bp, bp
.bank:
    mov ax, dx
    call memory_bank_mib
    test ax, ax
    jz .next
    mov ax, bp
    add al, '0'
    mov ah, 7
    push ax
    call setup_color
    stosw
    pop ax
    mov ax, 0x0720
    push ax
    call setup_color
    stosw
    pop ax
.next:
    shr dx, 4
    inc bp
    cmp bp, 4
    jb .bank
    test bl, 0xE0
    jz .done
    sub di, 2
    mov si, u_summary_interleaved
    mov bh, 7
    call setup_text
.done:
    popad
    ret

post_summary_cache:
    out CHIPSET_CONFIG_ON, al
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 7
    out CHIPSET_CONFIG_OFF, al
    mov si, u_l2_missing
    test al, al
    jz .l2_disabled
    cmp al, 7
    je .l2_disabled
    mov cl, al
    mov eax, 16
    shl eax, cl
    mov di, 4*160+20*2
    call setup_number
    ui_text 4, 25, u_kb, 0x07
    ret
.l2_disabled:
    test byte [fs:C_CHIP+9], 1
    jnz .l2_display
    mov si, u_disabled
.l2_display:
    mov di, 4*160+20*2
    mov bh, 7
    call setup_text
    ret

post_ui_cache:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    ui_text 3, 3, u_post_l1, 0x0B
    mov di, 3*160+24*2
    call post_clear_value
    mov di, 14*160+24*2
    call post_clear_value
    out CHIPSET_CONFIG_ON, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov dl, al
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov cl, al
    out CHIPSET_CONFIG_OFF, al
    mov si, u_disabled
    test dl, PRIMARY_CACHE_EN
    jz .l1
    mov eax, cr0
    test eax, 0x40000000
    jnz .l1
    mov si, u_post_enabled
.l1:
    mov di, 3*160+24*2
    mov bh, 7
    call setup_text
    cmp byte [fs:P_PHASE], 5
    jb .done
    mov si, u_disabled
    and cl, 7
    jz .l2
    cmp cl, 7
    je .l2
    ui_text 14, 24, u_post_cache_on, 7
    mov eax, 16
    shl eax, cl
    mov di, 14*160+33*2
    call setup_number
    ui_text 14, 39, u_kb, 7
    jmp .done
.l2:
    cmp byte [fs:P_PHASE], 5
    jb .l2_text
    test byte [fs:C_CHIP+9], 1
    jz .l2_text
    mov si, u_l2_missing
.l2_text:
    mov di, 14*160+24*2
    call setup_text
.done:
    cmp byte [fs:P_PHASE], 5
    jb .restore
    ui_text 14, 3, u_l2, 0x0B
.restore:
    pop es
    pop ds
    popad
    ret

post_rom_state:
    pushf
    cli
    pushad
    movzx edx, dx
    movzx edi, dx
    movzx eax, bx
    add edi, eax
    mov si, 0x0300
    xor bp, bp
    out CHIPSET_CONFIG_ON, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    test al, 0x80
    jz .primary
    or bp, 4
.primary:
    test al, PRIMARY_CACHE_EN
    jz .secondary
    mov eax, cr0
    test eax, 0x40000000
    jnz .secondary
    or bp, 1
.secondary:
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 7
    jz .block
    cmp al, 7
    je .block
    or bp, 2
.block:
    mov cx, dx
    shr cx, 9
    and cl, 6
    mov ax, dx
    shr ax, 12
    add al, 3
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    shr al, cl
    shr al, 1
    and al, 1
    mov bl, al
    mov ax, dx
    shr ax, 12
    add al, 9
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    shr al, cl
    and al, 1
    mov bh, al
    shl al, 4
    or bl, al                   ; Preserve segment NC separately for L2.
    mov al, 0x20
    call .policy
    mov al, 0x22
    call .policy
    test bp, 2
    jz .l1
    test bp, 4
    jz .cached
    test bl, 0x10
    jz .cached
.l1:
    test bp, 1
    jz .aggregate
    cmp bh, 2
    je .unknown
    test bh, bh
    jnz .aggregate
.cached:
    or bl, 2
    jmp .aggregate
.unknown:
    or bl, 4
.aggregate:
    and bl, 7
    mov ax, si
    or al, bl
    and ah, bl
    mov si, ax
    add edx, 0x80
    cmp edx, edi
    jb .block
    out CHIPSET_CONFIG_OFF, al
    mov bp, sp
    mov [ss:bp+28], si          ; Return AX through saved EAX.
    popad
    popf
    ret

; AL=index of PMRA. Matching enabled subregions use bus mapping and primary NC.
.policy:
    mov ch, al
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov cl, al
    mov al, ch
    inc al
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov ah, al
    mov al, cl
    call .matches
    jnc .policy_done
    shr al, 6
    and al, 1
    test bl, 0x80
    jz .first
    cmp bh, al
    je .mapped
    mov al, 2                  ; Conflicting PMRs: precedence unspecified.
.first:
    mov bh, al
.mapped:
    and bl, 0xFE               ; A PMR selects a bus, not shadow DRAM.
    or bl, 0x80
.policy_done:
    ret

; AL=PMRA, AH=PMRE, DX=sample segment. Carry set only for an enabled match.
.matches:
    pushad
    mov bl, ah
    movzx eax, al
    and eax, 0x3F
    mov cl, 12                 ; 64KiB subregions in a 512KiB parent.
    test al, 0x20
    jz .small
    mov cl, 16                 ; 1MiB subregions in an 8MiB parent.
    test al, 0x10
    jz .large
    and eax, 15
    shl eax, 10
    add eax, 0xC000
    mov cl, 7                  ; 2KiB subregions in a 16KiB parent.
    jmp .member
.large:
    and eax, 15
    shl eax, 19
    jmp .member
.small:
    shl eax, 15
.member:
    movzx edx, dx
    sub edx, eax
    jc .miss
    shr edx, cl
    cmp edx, 8
    jae .miss
    movzx ebx, bl
    bt ebx, edx
    popad
    ret
.miss:
    popad
    clc
    ret

presario_post_complete:
    post_code 0xFF
    jmp rtc_sync_ticks
