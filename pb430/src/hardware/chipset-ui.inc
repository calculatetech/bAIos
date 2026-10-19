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
    mov bx,U_CHIP_VALUE
    ret
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
    mov al,[cs:si+4]
    shl al,cl
    not al
    and [fs:U_CHIP+bx],al
    mov al,[fs:U_CHIP_VALUE]
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
    mov bp,ax
    shl bp,1
    mov si,[cs:si+bp]
    call setup_text
.done:
    popad
    ret
acc_video_required db 'Enabled (required)',0
