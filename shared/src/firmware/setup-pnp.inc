%ifdef BOARD_PNP_NV6_LATE
pnp_ui_navigation
%endif
pnp_ui_parameters:
    movzx bx,byte [fs:U_FIELD]
    cmp byte [fs:U_PNP_SCREEN],0
    jne .resource
    sub bx,5
    add bx,U_PNP+PNP_POLICY
    mov si,pnp_policy_values
    cmp byte [fs:U_FIELD],5
    je .enum
    mov si,pnp_clear_values
    jmp .enum
.resource:
    cmp byte [fs:U_PNP_SCREEN],4
    jne .bit
    shl bx,1
    add bx,U_PNP+PNP_IO
    ret
.bit:
    mov cx,bx
    mov bx,U_PNP+PNP_IRQ
    cmp byte [fs:U_PNP_SCREEN],1
    je .extract
    cmp byte [fs:U_PNP_SCREEN],2
    jne .not_high_irq
    add cl,8
    jmp .extract
.not_high_irq:
    mov bx,U_PNP+PNP_DMA
    cmp byte [fs:U_PNP_SCREEN],3
    je .extract
    mov bx,U_PNP+PNP_MEMORY
.extract:
    mov ax,[fs:bx]
    shr ax,cl
    and al,1
    mov [fs:U_CHIP_VALUE],al
    mov bx,U_CHIP_VALUE
    mov si,pnp_reservation_values
.enum:
    mov cx,2
    ret
pnp_ui_commit:
    cmp byte [fs:U_PNP_SCREEN],0
    jne .bit
    mov [fs:bx],al
    ret
.bit:
    pushad
    mov dx,1
    mov cl,[fs:U_FIELD]
    cmp byte [fs:U_PNP_SCREEN],2
    jne .shift
    add cl,8
.shift:
    shl dx,cl
    mov bx,U_PNP+PNP_IRQ
    cmp byte [fs:U_PNP_SCREEN],2
    jbe .store
    mov bx,U_PNP+PNP_DMA
    cmp byte [fs:U_PNP_SCREEN],3
    je .store_dma
    mov bx,U_PNP+PNP_MEMORY
.store:
    test al,al
    jnz .reserve
    not dx
    and [fs:bx],dx
    jmp .done
.reserve:
    or [fs:bx],dx
    jmp .done
.store_dma:
    test al,al
    jnz .reserve_dma
    not dl
    and [fs:bx],dl
    jmp .done
.reserve_dma:
    or [fs:bx],dl
.done:
    popad
    ret
pnp_ui_change:
    cmp byte [fs:U_PNP_SCREEN],4
    je .done
    cmp byte [fs:U_PNP_SCREEN],0
    jne .change
    cmp byte [fs:U_FIELD],5
    jb .done
.change:
    call pnp_ui_parameters
    mov al,[fs:bx]
    xor al,1
    jmp pnp_ui_commit
.done:
    ret
pnp_ui_draw:
    pushad
    ui_text 3,23,pnp_title,0x0B
    xor bp,bp
.row:
    push bp
    mov di,bp
    add di,5
    imul di,160
    add di,UI_LABEL_COL*2
    mov bh,7
    mov al,[fs:U_PNP_SCREEN]
    test al,al
    jz .main_label
    cmp al,4
    je .io_label
    cmp al,5
    je .memory_label
    mov si,pnp_irq_prefix
    cmp al,3
    jne .resource_label
    mov si,pnp_dma_prefix
.resource_label:
    call setup_text
    add di,8
    movzx eax,bp
    cmp byte [fs:U_PNP_SCREEN],2
    jne .resource_number
    add al,8
.resource_number:
    call setup_number
    jmp .label_done
.memory_label:
    mov ax,bp
    shl al,2
    add al,0xC0
    call setup_hex8
    mov si,pnp_memory_suffix
    call setup_text
    jmp .label_done
.io_label:
    mov si,pnp_io_labels
    jmp .label
.main_label:
    mov si,pnp_main_labels
.label:
    mov bx,bp
    shl bx,1
    mov si,[cs:si+bx]
    mov bh,7
    call setup_text
.label_done:
    pop bp
    push bp
    mov al,[fs:U_FIELD]
    push ax
    mov ax,bp
    mov [fs:U_FIELD],al
    cmp byte [fs:U_PNP_SCREEN],0
    jne .value
    cmp bp,5
    jae .value
    mov si,pnp_open
    jmp .text
.value:
    call pnp_ui_parameters
    cmp byte [fs:U_PNP_SCREEN],4
    je .number
    movzx bx,byte [fs:bx]
    shl bx,1
    mov si,[cs:si+bx]
.text:
    mov di,bp
    add di,5
    imul di,160
    add di,UI_VALUE_COL*2
    mov bh,7
    call setup_text
    jmp .next
.number:
    movzx eax,word [fs:bx]
    mov di,bp
    add di,5
    imul di,160
    add di,UI_VALUE_COL*2
    call setup_number
.next:
    pop ax
    mov [fs:U_FIELD],al
    pop bp
    inc bp
    call pnp_ui_count
    xor ch,ch
    cmp bp,cx
    jb .row
    popad
    ret
pnp_ui_help:
    ui_text 18,25,pnp_help1,0x1E
    ui_text 19,25,pnp_help2,0x1E
    ui_text 20,25,pnp_help3,0x1E
    ret
pnp_title db 'bAIos Setup > Plug and Play',0
pnp_menu db 'Plug and Play',0
pnp_open db 'Open',0
pnp_main_labels dw pnp_irqs,pnp_irqs_high,pnp_dmas,pnp_windows,pnp_memory,pnp_config,pnp_clear
pnp_irqs db 'IRQ 0-7',0
pnp_irqs_high db 'IRQ 8-15',0
pnp_dmas db 'DMA Reservations',0
pnp_windows db 'I/O Windows',0
pnp_memory db 'Upper Memory',0
pnp_config db 'Configuration',0
pnp_clear db 'Clear ESCD on Reset',0
pnp_io_labels dw pnp_io1,pnp_len1,pnp_io2,pnp_len2
pnp_io1 db 'Window 1 Base',0
pnp_len1 db 'Window 1 Length',0
pnp_io2 db 'Window 2 Base',0
pnp_len2 db 'Window 2 Length',0
pnp_policy_values dw pnp_bios,pnp_os
pnp_bios db 'BIOS (Default)',0
pnp_os db 'Operating System',0
pnp_clear_values dw pnp_keep,pnp_request
pnp_keep db 'Keep (Default)',0
pnp_request db 'Request',0
pnp_reservation_values dw pnp_available,pnp_reserved
pnp_available db 'Available (Default)',0
pnp_reserved db 'Reserved',0
pnp_irq_prefix db 'IRQ ',0
pnp_dma_prefix db 'DMA ',0
pnp_memory_suffix db '000h (16 KiB)',0
pnp_help1 db 'Reserve resources used by manual cards.',0
pnp_help2 db 'I/O is decimal. Length 0 disables a window.',0
pnp_help3 db 'Use BIOS. Clear keeps manual reservations.',0
