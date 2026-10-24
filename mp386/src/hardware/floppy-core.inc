; Conventional765 commands only; enhanced-density modes remain unsupported.
board_floppy_configure:
    mov byte [fs:HW_FDC_ENHANCED],0
    clc
    ret
board_floppy_perpendicular:
    cmp byte [fs:F_RATE],3
    je .unsupported
    clc
    ret
.unsupported:
    mov byte [fs:F_STATUS],1
    stc
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
