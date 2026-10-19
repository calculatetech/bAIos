; Ordinary descriptor choices. Board callbacks own profile policy and editability.
chipset_ui_enum_parameters:
    call chipset_ui_descriptor
    movzx bx,byte [cs:si+2]
    mov cl,[cs:si+3]
    mov al,[fs:U_CHIP+bx]
    shr al,cl
    and al,[cs:si+4]
    mov [fs:U_CHIP_VALUE],al
    mov cx,[cs:si+5]
    mov si,[cs:si+7]
    mov bx,U_CHIP_VALUE
    ret
chipset_ui_enum_commit:
    pushad
    call chipset_ui_descriptor
    movzx bx,byte [cs:si+2]
    mov cl,[cs:si+3]
    mov al,[cs:si+4]
    shl al,cl
    not al
    and [fs:U_CHIP+bx],al
    mov al,[fs:U_CHIP_VALUE]
    shl al,cl
    or [fs:U_CHIP+bx],al
    popad
    ret
chipset_ui_change:
    cmp byte [fs:U_CHIP_SCREEN],0
    je .done
    mov cl,[fs:U_FIELD]
    call chipset_ui_editable
    jc .done
    pushad
    mov dl,1
    cmp ah,0x4B
    jne .parameters
    mov dl,-1
.parameters:
    call chipset_ui_parameters
    movzx ax,byte [fs:U_CHIP_VALUE]
    movsx dx,dl
    add ax,dx
    test ax,ax
    jns .upper
    mov ax,cx
    dec ax
.upper:
    cmp ax,cx
    jb .store
    xor ax,ax
.store:
    mov [fs:U_CHIP_VALUE],al
    call chipset_ui_commit
    popad
.done:
    ret
chipset_ui_choice_draw:
    clc
    ret
chipset_ui_option_text:
    pushad
    mov bp,ax
    shl bp,1
    mov si,[cs:si+bp]
    call setup_text
    popad
    ret
