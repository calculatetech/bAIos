; RAM-E69DB..6AA0 aperture; RAMLD6F59..6FA6 fill; late89DC..8A73 activation.
; Allocation is generated in RAM. OEM validity/error bytes are replaced by the
; checked inventory, established cache holdoff and this boot's backing test.
mp_shadow_prepare:
    pushf
    pushad
    push ds
    push es
    cli
    cld
    ; Startup re-enables NMI after this owner returns.
    mov al,0x8D
    out 0x70,al
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    mov byte [fs:HW_F_SHADOW],0
    test byte [fs:HW_CACHE_STATUS],1
    jz .done
    in al,0x49
    test al,8
    jz .done
    mov cx,[fs:HW_MCU_COUNT]
    cmp cx,1
    jb .done
    cmp cx,3
    ja .done
    mov ax,[fs:HW_BANK_COUNTS]
    add ax,[fs:HW_BANK_COUNTS+2]
    cmp ax,16
    jb .done
    xor dx,dx
    mp_mcu_read
    test al,al
    jnz .done
    ; Verify the cold mapper's allocation, including retained warm-boot maps.
    xor si,si
    mov dx,2
.mapping:
    mp_mcu_read
    cmp ax,0x8100
    jne .done
    mov dx,7
    add dx,si
    mp_mcu_read
    test ah,ah
    jnz .done
    mov dx,si
    shl dx,4
    or dx,0x803C
    mov bx,0x8028
    mov di,4
.f_page:
    mp_mcu_read
    test si,si
    jnz .other_unit
    cmp ax,bx
    jne .done
    jmp .next_page
.other_unit:
    test ax,0x8000
    jnz .done
.next_page:
    inc dx
    inc bx
    dec di
    jnz .f_page
    test si,si
    jz .next_unit
    mov dx,si
    shl dx,4
    or dx,0x8020
    mp_mcu_read
    test ax,0x8000
    jnz .done
.next_unit:
    add si,0x100
    mov dx,si
    or dl,2
    loop .mapping
    post_code 0x24
    mov dx,0x8020
    mp_mcu_read
    cmp ax,0x8020
    jne .done
    mov bp,ax
    mov ax,0x8000
    mov es,ax
    mov bx,0x8028
    xor si,si
.qualify:
    mov ax,bx
    mp_mcu_write
    mov ax,0x4924
    call .pattern
    mov ax,0x9249
    call .pattern
    inc bx
    cmp bx,0x802C
    jb .qualify
    mov ax,bp
    mp_mcu_write
    test si,si
    jnz .done
    ; Keep the complete native5500/copy/zero window free of diagnostics.
.fill_begin:
    mov cx,[fs:HW_MCU_COUNT]
    mov ax,0x5500
    mov dx,7
.open:
    mp_mcu_write
    inc dh
    dec cl
    jnz .open
    push cs
    push cs
    pop es
    pop ds
    xor di,di
    xor si,si
    mov cx,0x8000
    cld
    rep movsw
    mov cx,[fs:HW_MCU_COUNT]
    xor ax,ax
    mov dx,7
.close:
    mp_mcu_write
    inc dh
    dec cl
    jnz .close
.fill_end:
    ; Read the copied backing through the same native low aperture.
    mov dx,0x8020
    mov ax,0x8000
    mov es,ax
    mov bx,0x8028
    xor si,si
    xor bp,bp
.verify:
    mov ax,bx
    mp_mcu_write
    xor di,di
    mov cx,0x2000
    repe cmpsw
    je .verified_page
    inc bp
.verified_page:
    mov si,bx
    sub si,0x8027
    shl si,14
    inc bx
    cmp bx,0x802C
    jb .verify
    ; Restore the conventional-memory aperture, even on a failed copy.
    mov ax,0x8020
    mp_mcu_write
    test bp,bp
    jnz .done
    mov byte [fs:HW_F_SHADOW],1
    post_code 0x25
.done:
    pop ax
    out 0x61,al
    pop es
    pop ds
    popad
    popf
    ret
.pattern:
    xor di,di
    mov cx,0x2000
    rep stosw
    xor di,di
    mov cx,0x2000
    repe scasw
    je .pattern_ok
    inc si
.pattern_ok:
    xor ax,ax
    xor di,di
    mov cx,0x2000
    rep stosw
    ret

mp_shadow_activate:
    pushf
    pushad
    cli
    cmp byte [fs:C_CHIP+1],1
    jne .done
    cmp byte [fs:HW_F_SHADOW],1
    jne .done
    ; OEM89DC reads MCU0007 and broadcasts the modified word to every MCU.
    mov dx,7
    mp_mcu_read
    or ax,0xAA00
    mp_mcu_write
    mov cx,[fs:HW_MCU_COUNT]
    mov dx,7
.all:
    mp_mcu_write
    inc dh
    dec cl
    jnz .all
    mov byte [fs:HW_F_SHADOW],2
.done:
    popad
    popf
    ret
