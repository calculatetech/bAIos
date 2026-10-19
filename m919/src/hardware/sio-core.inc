; UM8663: independent fixed UART pairs and real controller enable bits.
init_superio:
    pushf
    cli
    mov dx,CFG_PLATFORM_SIO_INDEX
    mov al,0xAA
    out dx,al
    mov al,0xC2
    out dx,al
    inc dx
    in al,dx
    and al,0xDF
    or al,0x81
    out dx,al
    dec dx
    mov al,0xC0
    out dx,al
    inc dx
    mov al,CFG_PLATFORM_SIO_CR0
    out dx,al
    dec dx
    mov al,0xC1
    out dx,al
    inc dx
    mov al,CFG_PLATFORM_SIO_CR1
    out dx,al
    dec dx
    mov al,0x55
    out dx,al
    popf
    ret
init_at_prerequisites:
    xor al,al
    out 0x0D,al
    out 0xDA,al
    mov dx,FDC_DOR
    out dx,al
    mov al,0x0C
    out 0x61,al
    mov al,0x54
    out 0x43,al
    mov al,0x12
    out 0x41,al
    ret

; The donor SMC used enhanced TDR swapping. UM8663 routing is handled here.
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
    xor al,1                  ; Restore donor logical ST0 unit identity.
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

%ifdef MOUSE_DIAGNOSTIC
board_mouse_platform_read:
    pushf
    cli
    push dx
    mov dx,CFG_PLATFORM_SIO_INDEX
    mov al,0xAA
    out dx,al
    mov al,0xC2
    out dx,al
    inc dx
    in al,dx
    push ax
    dec dx
    mov al,0x55
    out dx,al
    pop ax
    pop dx
    popf
    ret
%endif
%ifdef FLOPPY_DIAGNOSTIC
board_sio_diagnostic_begin:
    mov dx,CFG_PLATFORM_SIO_INDEX
    mov al,0xAA
    out dx,al
    ret
board_sio_diagnostic_index:
    mov al,cl
    add al,0xC0
    ret
board_sio_diagnostic_end:
    mov al,0x55
    out dx,al
    ret
%endif

ports_record_valid:
    push ax
    mov al,[fs:si]
    cmp al,0
    je .b
    cmp al,1
    je .b
    cmp al,3
    jne .bad
.b:
    mov al,[fs:si+1]
    test al,al
    jz .lpt
    cmp al,2
    je .lpt
    cmp al,4
    jne .bad
.lpt:
    cmp byte [fs:si+3],1
    je .bad
    pop ax
    clc
    ret
.bad:
    pop ax
    stc
    ret
ports_ui_candidate:
    test bx,bx
    jnz .b
    cmp al,2
    je .bad
    cmp al,4
    je .bad
    jmp .good
.b:
    cmp bx,1
    jne .lpt
    cmp al,1
    je .bad
    cmp al,3
    je .bad
    jmp .good
.lpt:
    cmp bx,3
    jne .good
    cmp al,1
    je .bad
.good:
    clc
    ret
.bad:
    stc
    ret
ports_ui_available:
%if !BOARD_AUX_POLICY_ENABLED
    cmp cl,P_MOUSE
    je .bad
%endif
    cmp cl,2
    je .bad
    cmp cl,7
    je .bad
    cmp cl,4
    jne .good
    cmp byte [fs:U_PORTS+3],0
    je .bad
.good:
    clc
    ret
.bad:
    stc
    ret
ports_ui_visible:
%if !BOARD_AUX_POLICY_ENABLED
    cmp cl,P_MOUSE
    je .bad
%endif
    cmp cl,2
    je .bad
    cmp cl,7
    je .bad
    clc
    ret
.bad:
    stc
    ret

ports_apply:
    pushf
    cli
    pushad
    mov dx,CFG_PLATFORM_SIO_INDEX
    mov al,0xAA
    out dx,al
    mov al,0xC0
    out dx,al
    inc dx
    in al,dx
    and al,0xF0               ; PCI IDE is independent: retain the SIO IDE bit.
    mov bl,al
    cmp byte [fs:C_PORTS+P_FLOPPY],0
    je .a
    or bl,1
.a:
    cmp byte [fs:C_PORTS],0
    je .b
    or bl,2
.b:
    cmp byte [fs:C_PORTS+1],0
    je .lpt
    or bl,4
.lpt:
    cmp byte [fs:C_PORTS+3],0
    je .ide
    or bl,8
.ide:
.write:
    mov al,bl
    out dx,al
    dec dx
    mov al,0xC1
    out dx,al
    inc dx
    in al,dx
    and al,0x30               ; Unknown timing bits remain unchanged.
    mov bl,al
    or bl,1                   ; Generic AT FDC owns the primary3F0 decode.
    cmp byte [fs:C_PORTS],1
    jne .base_b
    or bl,2
.base_b:
    cmp byte [fs:C_PORTS+1],2
    jne .base_lpt
    or bl,4
.base_lpt:
    cmp byte [fs:C_PORTS+3],2
    jne .mode
    or bl,8
.mode:
    movzx si,byte [fs:C_PORTS+4]
    or bl,[cs:umc_lpt_modes+si]
    mov al,bl
    out dx,al
    dec dx
    mov al,0x55
    out dx,al
    popad
    popf
    ret
umc_lpt_modes db 0x80,0x40,0xC0
ports_default db 1,2,1,2,0,1,1,1
ports_limits db 4,4,1,3,2,1,1,1

ide_apply_controller:
    call ports_apply
    pushad
    cmp word [fs:HW_IDE_BDF],0xFFFF
    jne .pci
    call umc_legacy_ide_apply
    jmp .done
.pci:
    movzx eax,word [fs:HW_IDE_BDF]
    shl eax,8
    or eax,0x80000004
    push eax
    call pci_read
    mov ecx,eax
    and cx,0xFFFE
    cmp byte [fs:C_IDE],0
    je .write
    cmp byte [fs:HW_IDE_USABLE],1
    jne .write
    or cl,1
.write:
    pop eax
    call pci_command_write
.done:
    popad
    ret
umc_legacy_ide_apply:
    ; The measured AF legacy window uses both channels and conservative PIO0.
    mov dx,0x108
    mov al,0x4A
    out dx,al
    mov al,0x6C
    out dx,al
    mov al,0xB0
    out dx,al
    inc dx
    xor al,al
    cmp byte [fs:C_IDE],0
    je .enable
    mov al,0xC0
.enable:
    out dx,al
    dec dx
    mov si,umc_legacy_ide_timing
.register:
    cs lodsb
    cmp al,0xFF
    je .lock
    out dx,al
    inc dx
    cs lodsb
    out dx,al
    dec dx
    jmp .register
.lock:
    mov al,0x34
    out dx,al
    ret
umc_legacy_ide_timing db 0xB2,0x44,0xB3,0x44,0xB4,0xCC,0xB5,0xCC,0xB6,0xCC,0xB7,0xCC,0xB8,0xCC,0xFF
floppy_controller_mode:
    ; Native AT controller, with software drive swapping in generic dispatch.
    ; Reestablish wake/init even after retained BIOS or power management state.
    push dx
    push ax
    mov dx,CFG_PLATFORM_SIO_INDEX
    mov al,0xAA
    out dx,al
    mov al,0xC2
    out dx,al
    inc dx
    in al,dx
    and al,0xDF
    or al,0x81
    out dx,al
    dec dx
    mov al,0x55
    out dx,al
    pop ax
    pop dx
    ret
