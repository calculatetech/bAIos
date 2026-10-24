post_cache_name:
    mov si,mp_cache_failed
    test byte [fs:HW_CACHE_STATUS],16
    jnz .done
    mov si,mp_cache_disabled
    test byte [fs:HW_CACHE_STATUS],2
    jz .done
    mov si,mp_cache_size
.done:
    ret

post_ui_cache:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax,0xB800
    mov es,ax
    ui_text 3,3,mp_l1,0x0B
    mov di,3*160+24*2
    call post_clear_value
    ui_text 3,24,mp_no_l1,7
    ui_text 4,3,u_l2,0x0B
    mov di,4*160+24*2
    call post_clear_value
    call post_cache_name
    mov di,4*160+24*2
    mov bh,7
    call setup_text
    pop es
    pop ds
    popad
    ret
post_summary_cache:
    call post_cache_name
    mov di,4*160+20*2
    mov bh,7
    jmp setup_text
post_memory_banks:
    pushad
    mov bl,[fs:HW_BANK_CODES]
    xor cx,cx
.bank:
    test bl,1
    jz .next
    mov ax,0x0730
    add al,cl
    stosw
    mov ax,0x0720
    stosw
.next:
    shr bl,1
    inc cl
    cmp cl,6
    jb .bank
    popad
    ret
post_rom_state:
    xor ax,ax
    cmp dx,0xF000
    jne .done
    cmp byte [fs:HW_F_SHADOW],2
    jne .done
    mov ax,0x0101
.done:
    ret
mp_l1 db 'L1 cache',0
mp_no_l1 db 'Not present',0
mp_cache_disabled db 'Disabled',0
mp_cache_size db '32 KB',0
mp_cache_failed db 'Cache test failed',0
