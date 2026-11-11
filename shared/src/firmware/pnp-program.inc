; Commit only completely replayed and selected LDNs. All resource fields are
; written while inactive, documented range check is disabled, Activate is last.
pnp_program:
    pushad
    push gs
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov edi,[gs:si+PNP_ROOT_LDNS]
    mov dx,[gs:si+PNP_ROOT_READ_PORT]
    call pnp_isa_key
.ldn:
    test edi,edi
    jz .done
    mov eax,edi
    call pnp_pointer
    test byte [gs:si+PNP_LDN_STATUS],1
    jz .next
    mov eax,[gs:si+PNP_LDN_CARD]
    call pnp_pointer
    mov ah,[gs:si+PNP_CARD_CSN]
    mov al,3
    call pnp_isa_write
    mov eax,edi
    call pnp_pointer
    mov ah,[gs:si+PNP_LDN_INDEX]
    mov al,7
    call pnp_isa_write
    mov ax,0x0030
    call pnp_isa_write
    test byte [gs:si+PNP_LDN_BOOT],2
    jz .domains
    inc al
    call pnp_isa_write
.domains:
    movzx ebp,byte [gs:si+PNP_LDN_NDOM]
    lea esi,[edi+PNP_LDN_DOMAINS]
.resource:
    test ebp,ebp
    jz .activate
    push esi
    mov eax,esi
    call pnp_pointer
    movzx bx,byte [gs:si+1]
    cmp byte [gs:si],1
    je .memory
    mov al,bl
    mov ebx,[gs:si+20]
    cmp byte [gs:si],4
    je .dma
    shl al,1
    cmp byte [gs:si],3
    je .irq
    add al,0x60
    shl ebx,16
    mov cx,2
    call pnp_write_field
    jmp .advance
.irq:
    add al,0x70
    mov ah,bl
    call pnp_isa_write
    inc al
    mov ah,2                ; High-true edge.
    test byte [gs:si+3],0x10
    jz .write
    mov ah,1                ; Low-true level, only when host intersection admits.
    jmp .write
.dma:
    add al,0x74
    mov ah,bl
.write:
    call pnp_isa_write
    jmp .advance
.memory:
    shl bl,3
    mov al,bl
    add al,0x40
    mov cx,2
    test byte [gs:si+3],4
    jz .mem24
    movzx bx,byte [gs:si+1]
    mov al,[cs:pnp_memory32_registers+bx]
    mov cx,4
.mem24:
    push ax
    push cx
    add al,cl
    call pnp_isa_read
    and al,1
    mov bl,al
    pop cx
    pop ax
    push ax
    add al,cl
    mov ah,bl
    test byte [gs:si+2],0x18
    jz .width
    or ah,2
.width:
    call pnp_isa_write
    pop ax
    push bx
    mov ebx,[gs:si+20]
    cmp cx,2
    jne .base_ready
    shl ebx,8
.base_ready:
    call pnp_write_field
    inc al                  ; Skip the memory control register.
    pop bx
    mov ah,bl
    mov ebx,[gs:si+16]
    test ah,1
    jnz .upper
    neg ebx                 ; ~(length-1), documented range comparator mask.
    jmp .limit
.upper:
    add ebx,[gs:si+20]
.limit:
    test byte [gs:si+3],1
    jz .non_null
    xor ebx,ebx
.non_null:
    cmp cx,2
    jne .limit_ready
    shl ebx,8
.limit_ready:
    call pnp_write_field
.advance:
    pop esi
    add esi,32
    dec ebp
    jmp .resource
.activate:
    mov ax,0x0130
    call pnp_isa_write
.next:
    mov eax,edi
    call pnp_pointer
    mov edi,[gs:si+PNP_LDN_NEXT]
    jmp .ldn
.done:
    call pnp_isa_wait_key
    pop gs
    popad
    ret

; AL=first register, EBX=big-endian field positioned atbits31.., CX=2/4.
; Preserve count for base/control/limit sequencing; AL advances past field.
pnp_write_field:
    push cx
.byte:
    rol ebx,8
    mov ah,bl
    call pnp_isa_write
    inc al
    loop .byte
    pop cx
    ret
pnp_memory32_registers: db 0x76,0x80,0x90,0xA0
pnp_program_code_end:
