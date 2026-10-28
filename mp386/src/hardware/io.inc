; OEM9ECB/9EB8: logical configuration40h..7Fh uses NVRAM0200h..023Fh.
mitsubishi_nvram_read:
    push dx
    mov dl,al
    and dl,0x3F
    mov dh,2
    in al,0x48
    out 0x48,al
    mov al,dh
    out 0x48,al
    mov al,dl
    out 0x48,al
    in al,0x48
    out 0x48,al
    pop dx
    ret
mitsubishi_nvram_write:
    push ax
    push dx
    mov dl,al
    and dl,0x3F
    mov dh,2
    in al,0x48
    out 0x48,al
    mov al,dh
    out 0x48,al
    mov al,dl
    out 0x48,al
    mov al,ah
    out 0x48,al
    pop dx
    pop ax
    mov al,ah
    ret

; OEMC055=54h selects DD90/DD96's board E1 gate, not the8042 fallback.
tiger_a20_read:
    pushf
    cli
    mov al,0xE1
    out 0x5A,al
    jmp short $+2
    jmp short $+2
    jmp short $+2
    in al,0x5B
    jmp short $+2
    jmp short $+2
    jmp short $+2
    shr al,4
    and al,2                    ; Shared A20 token uses bit1.
    popf
    ret
tiger_a20_write:
    pushf
    cli
    push ax
    push bx
    mov bl,al
    and bl,2
    shl bl,4
    mov al,0xE1
    out 0x5A,al
    jmp short $+2
    jmp short $+2
    jmp short $+2
    in al,0x5B
    jmp short $+2
    jmp short $+2
    jmp short $+2
    and al,0xDF
    or al,bl
    push ax
    mov al,0xE1
    out 0x5A,al
    jmp short $+2
    jmp short $+2
    jmp short $+2
    pop ax
    out 0x5B,al
    jmp short $+2
    jmp short $+2
    jmp short $+2
    pop bx
    pop ax
    popf
    ret

mp_boot_handoff:
    ; Leave the OR-connected motherboard gate off so DOS can use KBC A20.
    push ax
    mov al,0
    call tiger_a20_write
    pop ax
    ret

warm_reset:
    cli
    call mp_timing_restore
    call chipset_timing_trial_finish
    xor ax,ax
    mov ds,ax
    mov word [0x472],0x1234
    mov ax,0x008F
    call rtc_write
    call tiger_a20_read
    or al,2
    call tiger_a20_write
    mov al,0xFE
    call kbc_command
    jc .failed
    jmp hard_halt
.failed:
    mov al,0xEE
    jmp keyboard_halt
controlled_defaults_restart:
    mov al,0x36
    call rtc_read
    cmp al,0x1A
    jne warm_reset
    mov ax,0xDA36              ; Carry the current retry across its internal restart.
    call rtc_write
    jmp warm_reset

ide_apply_controller:
    ret                         ; OEM mirrors switches into E2; no proven disable polarity.
ports_apply:
    ; OEM0E73..0EA4: copy disk switch fields without changing cache or speed.
    pushf
    cli
    push ax
    push bx
    in al,0x5F
    mov bl,al
    mov al,0xE2
    out 0x5A,al
    jmp short $+2
    in al,0x5B
    and al,0xF3
    mov bh,bl
    and bh,0x40
    shr bh,4
    or al,bh
    and bl,0x10
    shr bl,1
    or al,bl
    out 0x5B,al
    jmp short $+2
    pop bx
    pop ax
    popf
    ret
ports_record_valid:
ports_ui_candidate:
    clc
    ret
ports_ui_available:
ports_ui_visible:
    stc                         ; No unsupported software routing controls.
    ret
ports_default db 1,2,1,2,0,1,0,1
ports_limits db 4,4,3,3,1,1,1,1

board_keyboard_handoff:
    pushf
    cli
    pushad
    mov al,0xAE
    call kbc_command
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    in al,0x21
    and al,0xFD
    out 0x21,al
    popad
    popf
    ret
.failed:
    mov al,0xE6
    jmp keyboard_halt

board_mouse_platform_read:
    xor al,al
    ret
mp386_mouse_init:
    ret                         ; This AT board has no AUX interface to disable.

mp_fpu_probe_allowed:
    in al,0x5F
    test al,0x20                ; OEM8D32: the board can force coprocessor absent.
    jnz .absent
    clc
    ret
.absent:
    stc
    ret
mp_fpu_configure:
    mov ah,1
    test word [0x0410],2
    jz .commit
    xor ah,ah
.commit:
    mitsubishi_control_write 0x90,ah
    ret

board_sio_diagnostic_begin:
board_sio_diagnostic_index:
board_sio_diagnostic_end:
floppy_controller_mode:
    ret
