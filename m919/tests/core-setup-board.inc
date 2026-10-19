setup_test_board_saved:
    cmp byte [fs:C_CHIP],0x40
    jne .not_saved
    pushad
    mov al,0x69
    call rtc_read
    mov byte [0xB63],65
    cmp al,0x56
    jne .fail
    mov byte [0xB63],66
    cmp byte [fs:C_VALID],1
    jne .fail
    mov byte [0xB63],67
    cmp byte [fs:C_TYPES],0x30
    jne .fail
    mov byte [0xB63],68
    cmp byte [fs:C_HALT],1
    jne .fail
    mov byte [0xB63],69
    cmp word [fs:C_IDE+1+IDE_TRANSLATION],0x0101
    jne .fail
    mov byte [0xB63],70
    cmp dword [fs:C_PORTS],0x03010403
    jne .fail
    mov byte [0xB63],71
    cmp byte [fs:C_PORTS+4],1
    jne .fail
%ifdef EMULATOR_SETUP_AUX_POLICY
    mov byte [0xB63],72
    cmp byte [fs:C_PORTS+P_MOUSE],0
    jne .fail
    mov al,0x66             ; Actual saved P1 record retains Disabled after restart.
    call rtc_read
    mov byte [0xB63],73
    test al,al
    jnz .fail
%endif
    mov byte [0xB63],74
    cmp word [0x400],0x3E8
    jne .fail
    mov byte [0xB63],75
    cmp word [0x402],0x2E8
    jne .fail
    mov byte [0xB63],76
    cmp word [0x408],0x278
    jne .fail
    mov byte [0xB63],77
    cmp byte [fs:P_RAM_FLAGS],4
    jne .fail
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    and ah,0xF0
    mov byte [0xB63],78
    cmp ah,0x40               ; Read=2 waits, write=3 waits reached HB51.
    jne .fail
    mov byte [0xB63],79
    test al,0x80             ; External cache remains disabled after save/reset.
    jnz .fail
    mov dx,CFG_PLATFORM_SIO_INDEX
    mov al,0xAA
    out dx,al
    mov al,0xC1
    out dx,al
    inc dx
    in al,dx
    and al,0xCF
    mov byte [0xB63],80
    cmp al,0x41               ; Real SIO address/mode bits reached hardware.
    jne .fail
    dec dx
    mov al,0x55
    out dx,al
    popad
    clc
    ret
.not_saved:
    stc
    ret
.fail:
    mov al,[0xB63]
    call emulator_exit
    jmp hard_halt

setup_test_board_key:
    cmp bx,11
    jne .ports
    cmp byte [fs:U_PAGE],5
    jne .key_fail
    cmp byte [fs:U_CHIP_SCREEN],1
    jne .key_fail
    cmp byte [fs:U_FIELD],3
    jne .key_fail
.ports:
    cmp bx,16
    jne .floppy
    cmp byte [fs:U_PAGE],3
    jne .key_fail
    cmp byte [fs:U_FIELD],0
    jne .key_fail
.floppy:
%ifdef EMULATOR_SETUP_AUX_POLICY
    cmp bx,23
    jne .aux_navigation
    cmp byte [fs:U_PORTS+P_MOUSE],0
    jne .key_fail
    ; No unsupported mouse label or value remains on the Devices page.
    push cx
    push di
    mov cx,54
    mov di,10*160+UI_LABEL_COL*2
.mouse_hidden:
    cmp byte [es:di],' '
    jne .key_fail
    add di,2
    loop .mouse_hidden
    pop di
    pop cx
.aux_navigation:
    cmp bx,24
    jne .aux_wrap
    cmp byte [fs:U_FIELD],5
    jne .key_fail
.aux_wrap:
    cmp bx,25
    jne .aux_return
    cmp byte [fs:U_FIELD],5 ; Down cannot leave FDC for unavailable Mouse6.
    jne .key_fail
.aux_return:
.aux_finished:
    cmp bx,30
%else
    cmp bx,27
%endif
    jne .done
    cmp byte [fs:U_PAGE],1
    jne .key_fail
    cmp byte [fs:U_FIELD],0
    jne .key_fail
.done:
    ret

.key_fail:
    mov al,bl
    add al,0x20
    call emulator_exit
    jmp hard_halt
