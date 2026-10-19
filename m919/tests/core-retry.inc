; Observe empty-media terminals and provide one fresh external scan.
; Never set the production boot cursor, state, or keyboard queue directly.
core_boot_retry_observe:
%ifdef EMULATOR_BOOT_FAILURE_INT18
    cmp byte [0xB0D],1
    jne .fail
    cmp byte [0xB0C],1
    jne .fail
    cmp byte [fs:B_ACTIVE],0xA5
    jne .fail
    cmp byte [fs:B_CURSOR],4  ; Continued at the next candidate and exhausted.
    jne .fail
    mov al,EMULATOR_BOOT_RETRY_EXIT
    call emulator_exit
%else
    cmp byte [0xB05],1
    je .second
    mov byte [0xB05],1
    mov byte [0xB04],0
    mov byte [0xB06],0
    mov eax,[0x19*4]
    mov [0xB00],eax
    mov word [0x19*4],core_retry_int19
    mov word [0x19*4+2],0xF000
    mov word [0x1C*4],core_retry_tick
    mov word [0x1C*4+2],0xF000
    ret
.second:
    cmp byte [0xB04],1       ; The installed INT19 vector really ran after input.
    jne .fail
    cmp byte [0xB06],1
    jne .fail
    mov al,EMULATOR_BOOT_RETRY_EXIT
    call emulator_exit
%endif
.fail:
    mov al,0x72
    call emulator_exit
    jmp hard_halt
core_retry_int19:
    inc byte [0xB04]
    jmp far [0xB00]
core_retry_tick:
    pushad
    push ds
    xor ax,ax
    mov ds,ax
    mov byte [0xB06],1
    mov word [0x1C*4],default_iret
    mov word [0x1C*4+2],0xF000
    mov al,0xD2
    call kbc_command
    jc .failed
    mov al,0x1C             ; Fresh Enter arrives through the real IRQ1 owner.
    call kbc_write_data
    jc .failed
    pop ds
    popad
    iret
.failed:
    mov al,0x73
    call emulator_exit
    jmp hard_halt
