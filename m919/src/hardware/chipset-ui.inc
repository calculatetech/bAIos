%include "setup/enum-ui.inc"
chipset_ui_parameters:
    call chipset_ui_enum_parameters
    call chipset_ui_choice_order
    mov [fs:U_CHIP_VALUE],al
    cmp byte [fs:U_CHIP_SCREEN],1
    jne .done
    cmp byte [fs:U_FIELD],2
    jne .done
    mov si,U_CHIP
    call chipset_fast_available
    mov si,chip_mode_choices
    jc .normal_choices
    inc al
    and al,3
    mov [fs:U_CHIP_VALUE],al
    jmp .done
.normal_choices:
    add si,2
    mov cx,3
.done:
    ret
chipset_ui_editable:
    cmp byte [fs:U_CHIP_SCREEN],1
    jne .good
    cmp cl,3
    jb .good
    cmp cl,5
    je .good
    cmp cl,6
    ja .good
    push ax
    mov al,[fs:U_CHIP+8]
    and al,0xC0
    cmp al,0x80
    pop ax
    jne .bad
    cmp cl,6
    jne .good
    test byte [fs:U_CHIP+5],1
    jz .bad
.good:
    clc
    ret
.bad:
    stc
    ret
chipset_ui_commit:
    pushad
    mov cl,[fs:U_FIELD]
    call chipset_ui_editable
    jc .done
    cmp byte [fs:U_CHIP_SCREEN],1
    jne .commit
    cmp cl,2
    jne .commit
    mov si,U_CHIP
    call chipset_fast_available
    jc .commit
    dec byte [fs:U_CHIP_VALUE]
    and byte [fs:U_CHIP_VALUE],3
.commit:
    call chipset_ui_descriptor
    mov si,[cs:si+7]
    mov al,[fs:U_CHIP_VALUE]
    call chipset_ui_choice_order
    mov [fs:U_CHIP_VALUE],al
    call chipset_ui_enum_commit
    cmp byte [fs:U_CHIP_SCREEN],1
    jne .cache
    cmp byte [fs:U_FIELD],2
    jbe .profile
    cmp byte [fs:U_FIELD],5
    je .profile
    cmp byte [fs:U_FIELD],6
    jbe .manual
    jmp .done
.cache:
    cmp byte [fs:U_CHIP_SCREEN],2
    jne .done
    cmp byte [fs:U_FIELD],3
    je .manual
    cmp byte [fs:U_FIELD],1
    je .profile
    cmp byte [fs:U_FIELD],2
    jne .done
.profile:
    mov si,U_CHIP
    call chipset_profile_apply
    jmp .done
.manual:
    and byte [fs:U_CHIP+8],0x3F
    or byte [fs:U_CHIP+8],0x80
.done:
    popad
    ret

; Order choices without changing the saved hardware encodings.
chipset_ui_choice_order:
    cmp si,chip_enable_values
    jne .waits
    xor al,1
    mov si,chip_enable_choices
    ret
.waits:
    cmp si,chip_wait_values
    jne .done
    xor al,3
    mov si,chip_wait_choices
.done:
    ret
