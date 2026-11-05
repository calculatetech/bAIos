; End the old runtime instance only after the original warm cache return.
; Restore the existing fixed prefix before the unchanged warm memory reader.
pnp_warm_budget:
    pushad
    push ds
    push es
    push fs
    push gs
    call pnp_runtime_open
    jc .done
    cmp byte [gs:si+P_T_PREFIX_KIB],CFG_PLATFORM_STATE_KIB
    jne .done
    mov ax,[gs:si+P_T_ORIGINAL_KIB]
    mov [0x413],ax
    push fs
    pop ds
    mov ax,STATE_SEG
    mov es,ax
    mov si,CFG_PLATFORM_STATE_KIB*1024-2
    mov di,si
    mov cx,CFG_PLATFORM_STATE_KIB*512
    std
    rep movsw
    cld
    mov byte [es:0],CFG_PLATFORM_STATE_KIB
    mov dword [es:PNP_RUNTIME],0
    xor ax,ax
    mov ds,ax
    mov word [0x40E],STATE_SEG
.done:
    pop gs
    pop fs
    pop es
    pop ds
    popad
    ret
