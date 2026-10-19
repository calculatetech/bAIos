; Observers only: no active/draft state or hardware writes.
setup_test_board_key:
%ifdef EMULATOR_RAM_PROOF_DELETE
    cmp byte [0xB8C],1
    je .done
    mov byte [0xB8C],1
    call 0xF000:core_ram_restore_check
    jc .bad
.done:
    ret
.bad:
    mov al,0x7B
    call emulator_exit
    jmp hard_halt
%else
    ret
%endif
setup_test_board_saved:
%ifndef EMULATOR_SETUP_SAVE_FIELDS
    cmp byte [0x600],4
    jne .pending
    cmp byte [0x602],setup_test_keys_end-setup_test_keys-1
    jne .pending
    clc
    ret
%else
    cmp byte [fs:C_CHIP],1
    jne .pending
    pushad
    mov al,0x69
    call rtc_read
    cmp al,0xC2
    jne .failed
    mov al,0x1A
    call acc_read
    test al,0x80
    jz .failed
    cmp byte [fs:C_CHIP+5],1
    jne .failed
    cmp byte [fs:HW_VGA_REQUIRED],1
    jne .failed
    popad
    clc
    ret
%endif
.pending:
    stc
    ret
.failed:
    mov al,0x6A
    call emulator_exit
    jmp hard_halt
