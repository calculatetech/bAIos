; ACC3221 data sheet configuration pp18-20, OEM4E1D/5053..51D4.
init_superio:
    pushad
    mov si,acc_sio_baseline
.next:
    cs lodsb
    cmp al,0xFF
    je .done
    mov bl,al
    call acc_read
    and al,[cs:si]
    inc si
    or al,[cs:si]
    inc si
    mov ah,al
    mov al,bl
    call acc_write
    jmp .next
.done:
    popad
    ret
acc_sio_baseline db 0xBE,7,0xD0,0xDB,4,0xD2,0xFB,0xF4,2,0xFE,0xF8,3,0xBF,0,0xDE,0xDC,0,0xFF,0xDD,1,0xBE,0xFF
ports_record_valid:
    ; IRQ3/4 have one source selector each, even for different same-IRQ bases.
    mov al,[fs:si]
    mov ah,[fs:si+1]
    test al,al
    jz .good
    test ah,ah
    jz .good
    xor al,ah
    test al,1
    jz .bad
.good:
    clc
    ret
.bad:
    stc
    ret
ports_ui_candidate:
    push ax
    push edx
    cmp bx,1
    ja .good
    movzx edx,bx
    xor edx,1
    cmp byte [fs:U_PORTS+edx],0
    je .good
    test al,al
    jz .good
    xor al,[fs:U_PORTS+edx]
    test al,1
    jz .bad
.good:
    pop edx
    pop ax
    clc
    ret
.bad:
    pop edx
    pop ax
    stc
    ret
ports_ui_available:
    cmp cl,4
    jne ports_ui_visible
    cmp byte [fs:U_PORTS+3],0
    je .bad
    clc
    ret
.bad:
    stc
    ret
ports_ui_visible:
    cmp cl,5 ; Floppy controller belongs to the Drives page.
    je ports_ui_available.bad
    cmp cl,7 ; Legacy always-on field; real IDE enable is on Drives.
    je ports_ui_available.bad
    clc
    ret
ports_apply:
    pushf
    cli
    pushad
    call load_bios_state
    ; Disable each UART before moving its address and IRQ source.
    mov al,0xDB
    call acc_read
    or al,0x1B
    mov ah,al
    mov al,0xDB
    call acc_write
    mov al,0xDC
    call acc_read
    and al,1
    mov bl,al
    mov al,[fs:C_PORTS]
    call ports_uart_base
    shr ax,2
    and al,0xFE
    or al,bl
    mov ah,al
    mov al,0xDC
    call acc_write
    mov al,0xDD
    call acc_read
    and al,1
    mov bl,al
    mov al,[fs:C_PORTS+1]
    call ports_uart_base
    shr ax,2
    and al,0xFE
    or al,bl
    mov ah,al
    mov al,0xDD
    call acc_write
    mov al,0xDE
    call acc_read
    and al,0x0C ; SP-reserved bits3:2 remain untouched.
    mov bl,al
    cmp byte [fs:C_PORTS],0
    je .irq_b
    mov al,0x20 ; Primary source is2, not the86Box macro1.
    test byte [fs:C_PORTS],1
    jnz .irq_a
    shl al,2
.irq_a:
    or bl,al
.irq_b:
    cmp byte [fs:C_PORTS+1],0
    je .irq_lpt
    mov al,0x30
    test byte [fs:C_PORTS+1],1
    jnz .irq_b_write
    shl al,2
.irq_b_write:
    or bl,al
.irq_lpt:
    cmp byte [fs:C_PORTS+3],0
    je .irqs
    or bl,2
.irqs:
    mov ah,bl
    mov al,0xDE
    call acc_write
    mov al,0xDB
    call acc_read
    and al,0xC4 ; Preserve polarities and the reserved bit; enable the clock.
    cmp byte [fs:C_PORTS],0
    jne .enable_b
    or al,0x18
.enable_b:
    cmp byte [fs:C_PORTS+1],0
    jne .enable_uarts
    or al,3
.enable_uarts:
    mov ah,al
    mov al,0xDB
    call acc_write
    movzx bx,byte [fs:C_PORTS+3]
    shl bx,1
    mov ax,[cs:ports_parallel+bx]
    shr ax,2
    mov ah,al
    mov al,0xBF
    call acc_write
    mov al,0xBE
    call acc_read
    and al,0xC7
    cmp byte [fs:C_PORTS+3],0
    jne .lpt_mode
    or al,0x18
.lpt_mode:
    cmp byte [fs:C_PORTS+4],0
    je .lpt_write
    or al,0x20
.lpt_write:
    mov ah,al
    mov al,0xBE
    call acc_write
    mov al,0xFB
    call acc_read
    and al,0xF4
    cmp byte [fs:C_PORTS+P_FLOPPY],0
    jne .fdc
    or al,2
.fdc:
    mov ah,al
    mov al,0xFB
    call acc_write
    popad
    popf
    ret
ide_apply_controller:
    push ax
    mov al,0xFE
    call acc_read
    and al,0xF8
    cmp byte [fs:C_IDE],0
    jne .enabled
    or al,2
.enabled:
    mov ah,al
    mov al,0xFE
    call acc_write
    pop ax
    ret
floppy_controller_mode:
    ret
board_floppy_unit:
    cmp byte [fs:C_SWAP],0
    je .done
    xor al,1
.done:
    ret
board_floppy_result:
    pushf
    push dx
    mov dl,al
    and dl,3
    cmp dl,2
    jae .done
    cmp byte [fs:C_SWAP],0
    je .done
    xor al,1
.done:
    pop dx
    popf
    ret
board_floppy_dor:
    cmp byte [fs:C_SWAP],0
    je .done
    push dx
    mov dl,al
    and al,0xCF
    and dl,0x30
    cmp dl,0x10
    jne .second
    mov dl,0x20
    jmp .motors
.second:
    cmp dl,0x20
    jne .motors
    mov dl,0x10
.motors:
    or al,dl
    xor al,1
    pop dx
.done:
    ret
board_mouse_platform_read:
    mov al,0xDB
    jmp acc_read
board_sio_diagnostic_begin:
    mov dx,SUPERIO_INDEX
    ret
board_sio_diagnostic_index:
    push bx
    movzx bx,cl
    mov al,[cs:acc_diag_registers+bx]
    pop bx
    ret
board_sio_diagnostic_end:
    ret
acc_diag_registers db 0xBE,0xDB,0xFB,0xFE
ports_default db 1,2,1,2,0,1,1,1
ports_limits db 4,4,3,3,1,1,1,1
