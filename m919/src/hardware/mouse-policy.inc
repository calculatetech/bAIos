; The configured physical board has no PS/2 mouse connector.
; Do not assert an AT-only controller; board capability owns the AUX policy.
; Keep only this selector disabled; retain valid CMOS and all other settings.
board_ports_no_aux_default:
    mov byte [fs:di+P_MOUSE],0
    ret
board_ports_no_aux_load:
    mov byte [fs:C_PORTS+P_MOUSE],0
    ret
board_ports_no_aux_save:
    mov byte [fs:U_PORTS+P_MOUSE],0
    ret
board_mouse_no_aux:
    pushf
    cli
    pushad
    push ds
    push fs
    call load_bios_state
    call board_ports_no_aux_load
    mov dword [fs:M_HANDLER],0
    mov word [fs:M_ENABLED],0
    mov byte [fs:M_PACKET],0
    mov word [fs:M_PACKET+1],0
    mov byte [fs:M_COMMAND],(KBC_INITIAL_COMMAND_BYTE | CFG_PLATFORM_KBC_RUNTIME_SET_BITS) & ~CFG_PLATFORM_KBC_RUNTIME_CLEAR_BITS
    xor ax,ax
    mov ds,ax
    and word [0x410],0xFFFB
    in al,0xA1
    or al,0x10                 ; No AUX IRQ owner on the configured board.
    out 0xA1,al
    ; No A7/A8/D4/keyboard reset or drain: preserve the established keyboard.
    pop fs
    pop ds
    popad
    popf
    ret
