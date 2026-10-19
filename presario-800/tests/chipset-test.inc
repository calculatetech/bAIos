; External IRQ1 keyboard stimulus and real retained-VGA capture.
; The preview ROM uses exactly the production chipset/setup owners.
%include "../tests/setup-test.inc"
%define CT_STEP 0x0630
%define CT_WAIT 0x0631
%define CT_CAPTURE 0x0632
%define CT_SETTLE 0x0633
chipset_test_begin:
    mov dword [CT_STEP], 0
%ifdef EMULATOR_CHIPSET_SUMMARY
    ret
%else
%ifdef EMULATOR_CHIPSET_POST_UI
    ret
%endif
    set_vector 0x1C, chipset_test_tick
.request:
    sti
    hlt
    cmp byte [CT_STEP], 2
    jb .request
    call post_keyboard_wait
    ret

chipset_test_tick:
    pushad
    push ds
    push es
    push fs
    xor ax, ax
    mov ds, ax
    mov es, ax
    call load_bios_state
    cmp byte [CT_CAPTURE], 0
    jne .done
    inc byte [CT_WAIT]
    cmp byte [CT_WAIT], 220
    jae .fail
    movzx bx, byte [CT_STEP]
    cmp bx, 2
    jb .send
    cmp byte [0x484], 24
    jne .done
    cmp word [0x485], 16
    jne .done
    mov ax, 0xB800
    mov es, ax
    cmp byte [es:0*160+34*2], 0x62
    jne .done
    cmp bx, chipset_test_keys_end-chipset_test_keys
    jb .send
%ifdef EMULATOR_CHIPSET_THEME
    cmp byte [fs:U_THEME], EMULATOR_CHIPSET_THEME
    jne .fail
    ; Actual VGA mode control: bright backgrounds must remain steady.
    mov dx, 0x3DA
    in al, dx
    mov dx, 0x3C0
    mov al, 0x30
    out dx, al
    inc dx
    in al, dx
    test al, 8
    jnz .fail
%endif
%ifdef EMULATOR_CHIPSET_STANDARD
    cmp byte [fs:U_PAGE], 0
%else
    cmp byte [fs:U_PAGE], 5
%endif
    jne .done
    cmp byte [fs:U_CHIP_SCREEN], EMULATOR_CHIPSET_SCREEN
    jne .done
%ifdef EMULATOR_CHIPSET_CLOCK24
    cmp byte [fs:C_CLOCK24], 1
    jne .fail
    cmp byte [fs:U_CLOCK24], 1
    jne .fail
%endif
%ifdef EMULATOR_CHIPSET_L2_REQUEST
    mov al, [fs:C_CHIP+9]
    and al, 1
    cmp al, EMULATOR_CHIPSET_L2_REQUEST
    jne .fail
    mov al, [fs:U_CHIP+9]
    and al, 1
    cmp al, EMULATOR_CHIPSET_L2_REQUEST
    jne .fail
%endif
%ifdef EMULATOR_CHIPSET_FIELD
    cmp byte [fs:U_FIELD], EMULATOR_CHIPSET_FIELD
    jne .done
%endif
    ; Setup must be available with L2 still disabled.
    out CHIPSET_CONFIG_ON, al
    mov al, 0x19
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    test al, 7
    jnz .fail
    out CHIPSET_CONFIG_OFF, al
    inc byte [CT_SETTLE]
    cmp byte [CT_SETTLE], 3
    jb .done
    call setup_test_snapshot
%ifdef EMULATOR_CHIPSET_THEME
%ifndef EMULATOR_CHIPSET_PREVIEW
    ; Pixels are already captured. Prove actual VGA state on Setup return.
    push ds
    push es
    call setup_restore_text
    cmp byte [fs:U_THEME_ACTIVE], 0
    jne .fail
    mov dx, 0x3DA
    in al, dx
    mov dx, 0x3C0
    mov al, 0x30
    out dx, al
    inc dx
    in al, dx
    test al, 8
    jz .fail
    pop es
    pop ds
%endif
%endif
    mov byte [CT_CAPTURE], 1
    set_vector 0x1C, default_iret
    jmp .done
.send:
    mov al, [cs:chipset_test_keys+bx]
    inc byte [CT_STEP]
    push ax
    mov al, 0xD2
    call kbc_command
    pop ax
    jc .fail
    call kbc_write_data
    jc .fail
.done:
    pop fs
    pop es
    pop ds
    popad
    iret
.fail:
    mov al, 0x75
    call emulator_exit
    jmp hard_halt

chipset_test_keys:
    db 0xE0,0x53
%ifdef EMULATOR_CHIPSET_THEME
    times EMULATOR_CHIPSET_THEME db 0x3F
%endif
%ifdef EMULATOR_CHIPSET_STANDARD
%else
    db 0x50,0x50,0x50,0x50,28
%if EMULATOR_CHIPSET_SCREEN > 0
    times EMULATOR_CHIPSET_SCREEN-1 db 0x50
    db 28
%endif
%ifdef EMULATOR_CHIPSET_FIELD
%if EMULATOR_CHIPSET_SCREEN = 1 && (EMULATOR_CHIPSET_FIELD = 11 || EMULATOR_CHIPSET_FIELD = 12)
    db 0x51 ; Page to Refresh, then select the requested configuration row.
    times EMULATOR_CHIPSET_FIELD-8 db 0x50
%else
    times EMULATOR_CHIPSET_FIELD db 0x50
%endif
%endif
%ifdef EMULATOR_CHIPSET_POPUP
    db 28
%endif
%ifdef EMULATOR_CHIPSET_HELP
    db 0x3B
%endif
%endif
chipset_test_keys_end:
%endif ; Summary captures do not use Setup stimulus or tick observers.

chipset_test_recovery_capture:
    call ata_detect_primary    ; Private capture disk is needed before normal disk POST.
    call setup_test_snapshot
    mov byte [CT_CAPTURE], 1
    jmp chipset_test_capture_drain

chipset_test_capture_drain:
    pushad
    push ds
    xor ax, ax
    mov ds, ax
    cmp byte [CT_CAPTURE], 1
    jne .done
    mov al, [fs:P_PHASE]
    push ax
    mov byte [fs:P_PHASE], 0 ; Private export must not draw POST disk lines over Setup.
    call ata_detect_primary    ; Early Setup has not run disk POST; export to the private disk.
    pop ax
    mov [fs:P_PHASE], al
    call setup_test_dump
    mov byte [CT_CAPTURE], 2
%ifndef EMULATOR_CHIPSET_PREVIEW
    mov al, 0x67
    call emulator_exit
    jmp hard_halt
%endif
.done:
    pop ds
    popad
    ret
