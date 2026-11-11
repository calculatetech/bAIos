; End the old runtime instance only after the original warm cache return.
; Restore the existing fixed prefix before the unchanged warm memory reader.
pnp_warm_budget:
    pushad
    push ds
    push es
    push fs
    push gs
    call pnp_runtime_open
    jc .transient
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
    jmp .done
.transient:
    ; Setup can reset before runtime publication. Admit only the current fixed
    ; prefix and a complete installed module inside its live journal bounds.
    mov ax,fs
    cmp ax,STATE_SEG
    jne .done
    cmp byte [fs:0],CFG_PLATFORM_STATE_KIB
    jne .done
    movzx edx,word [fs:PNP_JOURNAL_ORIGINAL_KIB]
    cmp edx,STATE_SEG >> 6
    ja .done
    movzx ecx,word [fs:PNP_JOURNAL_EXTERNAL_KIB]
    cmp ecx,edx
    ja .done
    cmp ecx,PNP_JOURNAL_FLOOR >> 10
    jb .done
    shl edx,10
    cmp [fs:PNP_JOURNAL_END],edx
    jne .done
    mov eax,[fs:PNP_JOURNAL_CURSOR]
    cmp eax,PNP_JOURNAL_FLOOR
    jb .done
    movzx ebx,word [fs:PNP_MODULE_POINTER+2]
    mov gs,bx
    shl ebx,4
    cmp eax,ebx
    ja .done
    add ebx,(pnp_module_end-pnp_module_start+15)&~15
    cmp ebx,edx
    ja .done
    cmp word [fs:PNP_MODULE_POINTER],pnp_module_entry
    jne .done
    cmp dword [gs:0],0x50494142
    jne .done
    cmp dword [gs:4],0x0032504E
    jne .done
    cmp word [gs:8],pnp_module_end-pnp_module_start
    jne .done
    call pnp_journal_release
    mov dword [fs:PNP_MODULE_POINTER],0
    mov dword [fs:PNP_RUNTIME],0
.done:
    pop gs
    pop fs
    pop es
    pop ds
    popad
    ret
