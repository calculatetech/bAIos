post_ui_pnp_ui_parameters:
    movzx bx,byte [fs:U_FIELD]
    cmp byte [fs:U_PNP_SCREEN],0
    jne .resource
    sub bx,4
    add bx,U_PNP+PNP_POLICY
    mov si,pnp_policy_values
    cmp byte [fs:U_FIELD],4
    je .enum
    mov si,pnp_clear_values
    jmp .enum
.resource:
    cmp byte [fs:U_PNP_SCREEN],3
    jne .bit
    shl bx,1
    add bx,U_PNP+PNP_IO
    ret
.bit:
    call post_ui_pnp_ui_bit
    mov ax,[fs:bx]
    ; IRQ2 is a saved alias of IRQ9. Fold only the displayed value.
    cmp bx,U_PNP+PNP_IRQ
    jne .extract
    test al,4
    jz .extract
    or ah,2
.extract:
    shr ax,cl
    and al,1
    mov [fs:U_CHIP_VALUE],al
    mov bx,U_CHIP_VALUE
    mov si,pnp_reservation_values
.enum:
    mov cx,2
    ret
; Shared field mapping for display and edits; DMA changes only its low bits.
post_ui_pnp_ui_bit:
    movzx cx,byte [fs:U_FIELD]
    mov bx,U_PNP+PNP_IRQ
    cmp byte [fs:U_PNP_SCREEN],1
    jne .not_irq
    movzx si,cl
    mov cl,[POST_UI_DATA:pnp_irq_numbers+si]
    ret
.not_irq:
    add bx,PNP_DMA-PNP_IRQ
    cmp byte [fs:U_PNP_SCREEN],2
    je .done
    add bx,PNP_MEMORY-PNP_DMA
.done:
    ret
post_ui_pnp_ui_commit:
    cmp byte [fs:U_PNP_SCREEN],0
    jne .bit
    mov [fs:bx],al
    ret
.bit:
    pushad
    call post_ui_pnp_ui_bit
    test al,al
    jnz .reserve
    btr [fs:bx],cx
    cmp bx,U_PNP+PNP_IRQ
    jne .done
    cmp cl,9
    jne .done
    and byte [fs:bx],0xFB          ; Explicit Available releases both aliases.
    jmp .done
.reserve:
    bts [fs:bx],cx
.done:
    popad
    ret
post_ui_pnp_ui_change:
    cmp byte [fs:U_PNP_SCREEN],3
    je .done
    cmp byte [fs:U_PNP_SCREEN],0
    jne .change
    cmp byte [fs:U_FIELD],4
    jb .done
.change:
    call post_ui_pnp_ui_parameters
    mov al,[fs:bx]
    xor al,1
    jmp post_ui_pnp_ui_commit
.done:
    ret
post_ui_pnp_ui_draw:
    pushad
    ui_text 3,23,pnp_title,0x0B
    xor bp,bp
.row:
    mov di,bp
    add di,5
    imul di,160
    add di,UI_LABEL_COL*2
    mov bh,7
    mov al,[fs:U_PNP_SCREEN]
    test al,al
    jz .main_label
    cmp al,3
    je .io_label
    cmp al,4
    je .memory_label
    mov si,pnp_irq_prefix
    cmp al,2
    jne .resource_label
    mov si,pnp_dma_prefix
.resource_label:
    call post_ui_setup_text
    add di,8
    movzx eax,bp
    cmp byte [fs:U_PNP_SCREEN],1
    jne .resource_number
    mov al,[POST_UI_DATA:pnp_irq_numbers+bp]
.resource_number:
    call post_ui_setup_number
    jmp .label_done
.memory_label:
    mov ax,bp
    shl al,2
    add al,0xC0
    call post_ui_setup_hex8
    mov si,pnp_memory_suffix
    call post_ui_setup_text
    jmp .label_done
.io_label:
    mov si,pnp_io_labels
    jmp .label
.main_label:
    mov si,pnp_main_labels
.label:
    mov bx,bp
    shl bx,1
    mov si,[POST_UI_DATA:si+bx]
    mov bh,7
    call post_ui_setup_text
.label_done:
    mov di,bp
    add di,5
    imul di,160
    add di,UI_VALUE_COL*2
    mov al,[fs:U_FIELD]
    push ax
    mov ax,bp
    mov [fs:U_FIELD],al
    cmp byte [fs:U_PNP_SCREEN],0
    jne .value
    cmp bp,4
    jae .value
    mov si,pnp_open
    jmp .text
.value:
    call post_ui_pnp_ui_parameters
    cmp byte [fs:U_PNP_SCREEN],3
    je .number
    movzx bx,byte [fs:bx]
    shl bx,1
    mov si,[POST_UI_DATA:si+bx]
.text:
    mov bh,7
    call post_ui_setup_text
    jmp .arrow
.number:
    movzx eax,word [fs:bx]
    mov bh,7
    test bp,1
    jnz .decimal
    mov cl,4
    call post_ui_setup_hex_number
    mov byte [es:di+8],'h'
    jmp .arrow
.decimal:
    call post_ui_setup_number
.arrow:
    cmp byte [fs:U_PNP_SCREEN],0
    jne .next
    cmp bp,4
    jae .next
    call post_ui_setup_submenu_arrow
.next:
    pop ax
    mov [fs:U_FIELD],al
    inc bp
    call post_ui_pnp_ui_count
    xor ch,ch
    cmp bp,cx
    jb .row
    popad
    ret
post_ui_pnp_ui_help:
    ui_text 18,25,pnp_help1,0x1E
    ui_text 19,25,pnp_help2,0x1E
    ui_text 20,25,pnp_help3,0x1E
    ret
