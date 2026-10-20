chipset_ui_parameters:
    call chipset_ui_descriptor
    movzx bx,byte [cs:si+2]
    mov cl,[cs:si+3]
    mov al,[fs:U_CHIP+bx]
    shr al,cl
    and al,[cs:si+4]
    mov [fs:U_CHIP_VALUE],al
    mov cx,[cs:si+5]
    mov si,[cs:si+7]
    cmp si,acc_values_2
    jne .ready
    movzx bx,al
    mov al,[cs:acc_refresh_choice_index+bx]
    mov [fs:U_CHIP_VALUE],al
    mov si,acc_refresh_choices
.ready:
    call chipset_ui_isa_values
    call chipset_ui_isa_parameters
    mov bx,U_CHIP_VALUE
    ret

; Keep these menu helpers beyond the fixed VGA compatibility entry.
%macro pb430_isa_ui 0
chipset_ui_isa_parameters:
    cmp si,acc_isa_values
    je .isa4
    cmp si,acc_isa_values_other
    jne .done
    movzx bx,al
    mov al,[cs:acc_isa_choice_index3+bx]
    mov si,acc_isa_choices3
    jmp .choice
.isa4:
    movzx bx,al
    mov al,[cs:acc_isa_choice_index4+bx]
    mov si,acc_isa_choices4
.choice:
    mov [fs:U_CHIP_VALUE],al
.done:
    ret

chipset_ui_isa_values:
    cmp si,acc_isa_values
    jne .done
    push ax
    in al,0x78
    and al,7
    cmp al,5
    je .restored
    mov si,acc_isa_values_other
.restored:
    pop ax
.done:
    ret

chipset_ui_isa_commit:
    cmp bx,22
    jne .done
    cmp cl,4
    jne .done
    movzx di,al
    mov si,acc_isa_values
    call chipset_ui_isa_values
    cmp si,acc_isa_values
    jne .isa3
    mov al,[cs:acc_isa_choice_code4+di]
    test al,al
    jnz .done
    shr dl,4
    and dl,7
    cmp dl,5
    jne .done
    mov al,dl ; Keep a saved explicit divisor when its shared choice is unchanged.
    ret
.isa3:
    mov al,[cs:acc_isa_choice_code3+di]
    test al,al
    jnz .done
    shr dl,4
    and dl,7
    cmp dl,6
    jne .done
    mov al,dl
.done:
    ret
%endmacro

chipset_ui_editable:
    push ax
    push bx
    push si
    movzx bx,byte [fs:U_CHIP_SCREEN]
    dec bx
    shl bx,1
    mov si,[cs:chipset_groups+bx]
    movzx ax,cl
    imul ax,CHIP_FIELD_SIZE
    add si,ax
    mov al,[cs:si+2]
    cmp al,4
    je .video
    cmp al,12
    jne .ads
.video:
    cmp byte [fs:HW_VGA_REQUIRED],1
    je .bad
.ads:
    cmp al,5
    jne .timing
    cmp byte [fs:U_CHIP],0
    je .bad
.timing:
    cmp al,19
    jne .write_dependency
    cmp byte [cs:si+3],7
    jne .profile
    test byte [fs:U_CHIP+21],8
    jz .bad
.write_dependency:
    cmp al,22
    jne .refresh_dependency
    cmp byte [cs:si+3],2
    jne .profile
    test byte [fs:U_CHIP+22],2
    jz .bad
.refresh_dependency:
    cmp al,20
    jne .profile
    test byte [fs:U_CHIP+19],2
    jz .bad
.profile:
    ; Like Presario, presets show their values; Manual unlocks RAM fields.
    cmp byte [fs:U_CHIP_SCREEN],2
    jne .good
    test cl,cl
    jz .good
    cmp byte [fs:U_CHIP+14],2
    jne .bad
.good:
    pop si
    pop bx
    pop ax
    clc
    ret
.bad:
    pop si
    pop bx
    pop ax
    stc
    ret
chipset_ui_commit:
    pushad
    mov cl,[fs:U_FIELD]
    call chipset_ui_editable
    jc .done
    call chipset_ui_descriptor
    movzx bx,byte [cs:si+2]
    mov cl,[cs:si+3]
    mov dl,[fs:U_CHIP+bx]
    mov al,[cs:si+4]
    shl al,cl
    not al
    and [fs:U_CHIP+bx],al
    mov al,[fs:U_CHIP_VALUE]
    cmp bx,7
    jne .isa
    movzx di,al
    mov al,[cs:acc_refresh_choice_code+di]
    jmp .packed
.isa:
    call chipset_ui_isa_commit
.packed:
    shl al,cl
    or [fs:U_CHIP+bx],al
    cmp bx,14
    jne .changed
    mov si,U_CHIP
    call chipset_profile_apply
    jmp .done
.changed:
    ; Any DRAM/refresh change becomes Manual without discarding other fields.
    cmp bx,7
    je .manual
    cmp bx,9
    je .manual
    cmp bx,15
    je .manual
    cmp bx,16
    je .manual
    cmp bx,20
    je .manual
    cmp bx,18
    jne .refresh
    cmp byte [cs:si+3],4
    jb .manual
.refresh:
    cmp bx,19
    jne .done
    cmp byte [cs:si+3],2
    jae .done
.manual:
    mov byte [fs:U_CHIP+14],2
    mov al,[fs:U_CHIP+15]
    and al,0x13
    sete byte [fs:U_CHIP+8]
.done:
    popad
    ret
chipset_ui_change:
    cmp byte [fs:U_CHIP_SCREEN], 0
    je .done
    mov cl, [fs:U_FIELD]
    call chipset_ui_editable
    jc .done
    pushad
    mov dl, 1
    cmp ah, 0x4B
    jne .parameters
    mov dl, -1
.parameters:
    call chipset_ui_parameters
    movzx ax, byte [fs:U_CHIP_VALUE]
    movsx dx, dl
    add ax, dx
    test ax, ax
    jns .upper
    mov ax, cx
    dec ax
.upper:
    cmp ax, cx
    jb .store
    xor ax, ax
.store:
    mov [fs:U_CHIP_VALUE], al
    call chipset_ui_commit
    popad
.done:
    ret

chipset_ui_choice_draw:
    clc
    ret
chipset_ui_option_text:
    pushad
    ; Value-table identity is shared across groups; resolve the actual field.
    push ax
    push bx
    push si
    movzx bx,byte [fs:U_CHIP_SCREEN]
    dec bx
    shl bx,1
    mov si,[cs:chipset_groups+bx]
    imul bx,cx,CHIP_FIELD_SIZE
    add si,bx
    mov bl,[cs:si+2]
    cmp bl,4
    je .required
    cmp bl,12
    jne .regular
.required:
    cmp byte [fs:HW_VGA_REQUIRED],1
    jne .regular
    pop si
    pop bx
    pop ax
    mov si,acc_video_required
    call setup_text
    jmp .done
.regular:
    pop si
    pop bx
    pop ax
.ordinary:
    call chipset_ui_isa_values
    mov bp,ax
    shl bp,1
    mov si,[cs:si+bp]
    call setup_text
.done:
    popad
    ret
acc_video_required db 'Enabled (required)',0
