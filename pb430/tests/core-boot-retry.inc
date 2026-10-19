; Existing retry observation hook: real keys through8042/IRQ1 only.
core_boot_retry_observe:
    inc byte [0x630]
    cmp byte [fs:B_CURSOR],4
    jne .failed
    cmp byte [0x400+KB_POST_STATE],2
    jne .failed
    cmp byte [fs:S_SETUP_REQUEST],0
    jne .failed
%ifdef EMULATOR_BOOT_STALE
    cmp word [0x7DFE],0 ; The selected missing drive must execute the real read path.
    jne .failed
    cmp byte [0x441],0 ; Installed INT13 reported the actual failed read.
    je .failed
%endif
    pushad
    push es
    mov ax,0xB800
    mov es,ax
    movzx ax,byte [0x630]
    dec ax
    shl ax,1
    add ax,13
    cmp ax,22
    jbe .row
    mov ax,22
.row:
    mov bx,160
    mul bx
    mov di,ax
    mov si,.line1
    call .line
    movzx ax,byte [0x630]
    dec ax
    shl ax,1
    add ax,14
    cmp ax,23
    jbe .row2
    mov ax,23
.row2:
    mov bx,160
    mul bx
    mov di,ax
    mov si,.line2
    call .line
    pop es
    popad
    cmp byte [0x630],9
    je .pass
    mov byte [0x632],0
    xor ax,ax
    mov es,ax
    set_vector 0x1C,core_retry_tick
    ret
.line:
    cs lodsb
    test al,al
    jz .done
    mov ah,7
    scasw
    jne .failed
    jmp .line
.done:
    ret
.line1 db 'No boot device available',0
.line2 db 'Press any key to retry',0
.failed:
    mov al,0x72
    call emulator_exit
    jmp hard_halt
.pass:
    mov al,0x71
    call emulator_exit
    jmp hard_halt
core_retry_tick:
    pushad
    push ds
    push es
    xor ax,ax
    mov ds,ax
    mov es,ax
    inc byte [0x632]
    cmp byte [0x632],2
    jb .done
    mov ax,[0x41A]
    cmp ax,[0x41C]
    jne core_boot_retry_observe.failed
    mov al,0xD2
    call kbc_command
    jc core_boot_retry_observe.failed
    mov al,0x1E
    call kbc_write_data
    jc core_boot_retry_observe.failed
    set_vector 0x1C,default_iret
.done:
    pop es
    pop ds
    popad
    iret
