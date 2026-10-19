; Included inside protected_chunk: no chipset writes, no cache transitions.
; 1024 dependent loads per IRQ window, identical for both address orders.
    mov edi,[address]
    mov eax,edi
    sub eax,0x100000
    cmp eax,0x3FC000
    ja .order_address_bad
    test eax,0x3FFF
    jnz .order_address_bad
    mov ecx,1024
    cmp byte [operation],2
    je .order_read
.order_link:
    mov eax,edi
    cmp byte [order_column],0
    jne .order_column_link
    add eax,16
    cmp eax,0x500000
    jb .order_link_ready
    mov eax,0x100000
    jmp .order_link_ready
.order_column_link:
    add eax,0x1000
    cmp eax,0x500000
    jb .order_link_ready
    mov eax,edi
    and eax,0xFFF
    add eax,16
    and eax,0xFFF
    add eax,0x100000
.order_link_ready:
    cmp byte [operation],0
    jne .order_verify
    mov [es:edi],eax
    jmp .order_next
.order_verify:
    mov ebx,[es:edi]
    cmp ebx,eax
    jne .memory_bad
.order_next:
    add edi,16
    loop .order_link,ecx
    jmp .return
.order_read:
    mov esi,[order_pointer]
    pit_sample
    mov dx,ax
.order_load:
    cmp esi,0x100000
    jb .order_pointer_bad
    cmp esi,0x500000
    jae .order_pointer_bad
    test esi,15
    jnz .order_pointer_bad
    mov edi,esi
    mov esi,[es:esi]
    loop .order_load,ecx
    pit_sample
    sub dx,ax
    movzx eax,dx
    mov [order_pointer],esi
    cmp byte [order_measure],0
    je .return
    add [ticks],eax
    jmp .return
.order_address_bad:
    mov esi,edi
.order_pointer_bad:
    mov ebx,esi
    mov bp,4
    jmp .bad
.a20_bad:
    mov bp,1
    jmp .bad
.memory_bad:
    mov esi,eax
    mov bp,3
.bad:
    mov [failure_address],edi
    mov [failure_expected],esi
    mov [failure_actual],ebx
    mov dx,bp
    mov [failure_kind],dl
    mov byte [failed],1
    jmp .return
