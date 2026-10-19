; Saved L1 choice and effective L2 state use the established POST positions.
post_ui_cache:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax,0xB800
    mov es,ax
    ui_text 3,3,u_post_l1,0x0B
    mov di,3*160+24*2
    call post_clear_value
    mov si,u_disabled
    cmp byte [fs:C_CHIP+1],0
    je .l1
    mov si,u_post_enabled
.l1:
    mov di,3*160+24*2
    mov bh,7
    call setup_text
    cmp byte [fs:P_PHASE],5
    jb .done
    ui_text 14,3,u_l2,0x0B
    mov di,14*160+24*2
    call post_clear_value
    call post_cache_name
    mov di,14*160+24*2
    mov bh,7
    call setup_text
.done:
    pop es
    pop ds
    popad
    ret
post_summary_cache:
    call post_cache_name
    mov di,4*160+20*2
    mov bh,7
    jmp setup_text
post_cache_name:
    mov si,u_disabled
    cmp byte [fs:HW_CACHE_PRESENT],0
    je .done
    mov si,acc_cache_unknown
    movzx bx,byte [fs:HW_CACHE_CODE]
    test bx,bx
    jz .done
    dec bx
    shl bx,1
    mov si,[cs:acc_cache_off+bx]
    cmp byte [fs:HW_CACHE_ENABLED],1
    jne .done
    mov si,[cs:acc_cache_on+bx]
.done:
    ret
acc_cache_off dw acc128off,acc512off,acc256off
acc_cache_on dw acc128on,acc512on,acc256on
acc128off db '128 KB Off',0
acc512off db '512 KB Off',0
acc256off db '256 KB Off',0
acc128on db 'Enabled (128 KB)',0
acc512on db 'Enabled (512 KB)',0
acc256on db 'Enabled (256 KB)',0
acc_cache_unknown db 'Present / unknown',0
post_memory_banks:
    pushad
    mov bx,[fs:HW_BANK_CODES]
    xor cx,cx
.bank:
    test bl,15
    jz .next
    mov ax,0x0730
    add al,cl
    stosw
    mov ax,0x0720
    stosw
.next:
    shr bx,4
    inc cl
    cmp cl,4
    jb .bank
    popad
    ret
post_rom_state:
    pushad
    movzx edi,dx
    movzx ecx,bx
    add edi,ecx
    movzx ebp,dx
    mov si,0x0300
    mov al,2
    call acc_read
    mov dh,al
.block:
    mov eax,ebp
    sub ax,0xC000
    shr ax,11
    cmp al,2
    jb .bit
    shr al,1
    inc al
.bit:
    mov cl,al
    mov bl,dh
    shr bl,cl
    and bl,1
    cmp byte [fs:HW_CACHE_ENABLED],1
    jne .aggregate
    test dh,0x40
    jz .aggregate
    or bl,2
.aggregate:
    mov ax,si
    or al,bl
    and ah,bl
    mov si,ax
    add ebp,0x80
    cmp ebp,edi
    jb .block
    mov bp,sp
    mov [ss:bp+28],si
    popad
    ret
