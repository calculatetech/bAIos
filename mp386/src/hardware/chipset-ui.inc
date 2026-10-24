chipset_ui_parameters:
    push dx
    call chipset_ui_descriptor
    mov dl,[cs:si+13]
    call chipset_ui_enum_parameters
    xor [fs:U_CHIP_VALUE],dl
    test dl,dl
    jz .done
    add si,4                    ; Reversed binary encodings have a sorted popup table.
.done:
    pop dx
    ret
chipset_ui_commit:
    push ax
    call chipset_ui_descriptor
    mov al,[fs:U_CHIP_VALUE]
    xor al,[cs:si+13]
    xchg al,[fs:U_CHIP_VALUE]
    push ax
    call chipset_ui_enum_commit
    pop ax
    mov [fs:U_CHIP_VALUE],al
    pop ax
    ret
chipset_ui_editable:
    push ax
    push bx
    push cx
    push si
    movzx bx,byte [fs:U_CHIP_SCREEN]
    test bx,bx
    jz .good
    dec bx
    shl bx,1
    mov si,[cs:chipset_groups+bx]
    movzx bx,cl
    imul bx,CHIP_FIELD_SIZE
    add si,bx
    movzx bx,byte [cs:si+2]
    cmp bx,7
    jb .good
    sub bx,7
    shr bx,1
    shl bx,1
    cmp word [fs:HW_BANK_COUNTS+bx],0
    je .bad
.good:
    pop si
    pop cx
    pop bx
    pop ax
    clc
    ret
.bad:
    pop si
    pop cx
    pop bx
    pop ax
    stc
    ret
