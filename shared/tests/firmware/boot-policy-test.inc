; External scan-code stimuli during detection: cancel -> Save A-first -> warm POST.
%ifdef EMULATOR_BOOT_SETTINGS_RECOVERY
boot_settings_alert_begin:
    push fs
    call load_bios_state
    cmp byte [fs:C_VALID], 0
    pop fs
    jne .done                  ; Verified defaults already entered a fresh POST.
    mov byte [0x0603], 0
    set_vector 0x1C, boot_settings_alert_tick
.done:
    ret

boot_settings_alert_tick:
    pushad
    push ds
    push es
    push fs
    xor ax, ax
    mov ds, ax
    mov es, ax
    inc byte [0x0603]
    cmp byte [0x0603], 240
    jae .fail
    cmp byte [0x0603], 8
    jb .done
    call load_bios_state
    cmp byte [fs:C_VALID], 0
    jne .fail
    test byte [fs:C_ERROR], 4
    jz .done                 ; Visible RAM now services IRQ0 before this gate.
    test byte [fs:C_ERROR], 1 ; The valid clock must not cause this notice.
    jnz .fail
    mov al, 0xD2
    call kbc_command
    jc .fail
    mov al, 28               ; Fresh Enter accepts production settings defaults.
    call kbc_write_data
    jc .fail
    set_vector 0x1C, default_iret
.done:
    pop fs
    pop es
    pop ds
    popad
    iret
.fail:
    mov al, 0x7B
    call emulator_exit
    jmp hard_halt
%endif

boot_policy_begin:
    cmp byte [fs:C_BOOT], 2
    jne .done
    mov dword [0x0600], 0      ; ready, phase, script index, watchdog
    mov byte [0x0600], 1
    set_vector 0x1C, boot_policy_tick
.done:
    ret

boot_policy_ready:
    cmp byte [fs:C_BOOT], 2
    jne .done
    mov byte [0x0600], 1
.done:
    ret

boot_policy_tick:
    pushad
    push ds
    push es
    xor ax, ax
    mov ds, ax
    inc byte [0x0603]
    cmp byte [0x0603], 240
    jae .fail
    cmp byte [0x0600], 1
    jne .done
    cmp byte [0x0601], 2
    je .script
    cmp byte [0x0601], 1
    je .delete
    cmp byte [0x0484], 24
    jne .done
    cmp byte [0x0400 + KB_POST_STATE], 1 ; Detection only, never boot failure.
    jne .done
    inc byte [0x0601]
    mov al, 0xE0
    jmp .send
.delete:
    inc byte [0x0601]
    mov byte [0x0602], 0
    mov al, 0x53
    jmp .send
.script:
    movzx bx, byte [0x0602]
    mov si, boot_policy_save
    cmp bx, 13                 ; Save was canceled: schema1 input is unchanged.
    jne .key
    mov al, 0x3C
    call rtc_read
    cmp al, 2
    jne .fail
    mov al, 0x3E
    call rtc_read
    cmp al, 0x5A
    jne .fail
.key:
    mov al, [cs:si + bx]
    test al, al
    jnz .visible
    inc byte [0x0601]
    jmp .done
.visible:
    cmp byte [0x0484], 24
    jne .done
    cmp word [0x0485], 16
    jne .done
    push word 0xB800
    pop es                    ; Preserve AL: the pending scan code.
    cmp word [es:34*2], 0x1F62 ; Actual Setup header, distinct from80x25 POST.
    jne .done
.advance:
    inc byte [0x0602]
.send:
    push ax
    mov al, 0xD2
    call kbc_command
    pop ax
    jc .fail
    call kbc_write_data
    jc .fail
.done:
    pop es
    pop ds
    popad
    iret
.fail:
    mov al, [0x0601]
    add al, 0x70
    call emulator_exit
    jmp hard_halt

; Cancel discard; select A-first/Seek Off; cancel Save once then confirm.
boot_policy_save db 1,1,0x50,0x50,15,0x4B,0x50,0x50,0x50,0x50,0x4B,0x44,1,0x44,28,0
