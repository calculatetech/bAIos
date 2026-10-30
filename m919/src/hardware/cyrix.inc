; Original AMI normal-state 20D8/267C policy, with a positive CPU guard.
chipset_cyrix_apply:
    pushad
    mov al,0x80
    out 0x70,al
    call chipset_cyrix_5x86
    jnc .mapping
    mov al,0xC3
    out 0x22,al
    in al,0x23
    mov ch,al
    ; Reusable apply must undo a prior linear mode before the host changes.
    and al,0xFB
    test byte [fs:C_CHIP+18],2
    jnz .linear
    out 0x23,al
    jmp .lsser
.linear:
    cache_read 0x08
    cmp al,4
    jne .clear_linear
    cache_read 0x62
    or al,2
    mov cl,al
    cache_write 0x62,cl
    mov al,0xC3
    out 0x22,al
    mov al,ch
    or al,4
    out 0x23,al
    or ch,4
    jmp .lsser
.clear_linear:
    mov al,0xC3
    out 0x22,al
    mov al,ch
    and al,0xFB
    out 0x23,al
.lsser:
    mov al,0xC3
    out 0x22,al
    in al,0x23
    mov ch,al
    or al,0x10
    out 0x23,al
    mov al,0x20
    out 0x22,al
    in al,0x23
    cmp byte [fs:HW_CYRIX_SAVED],1
    je .saved
    mov [fs:HW_CYRIX_PCR],al
    mov byte [fs:HW_CYRIX_SAVED],1
.saved:
    and al,0x7F
    test byte [fs:C_CHIP+18],4
    jnz .store_pcr
    mov ah,[fs:HW_CYRIX_PCR]
    and ah,0x80
    or al,ah
.store_pcr:
    out 0x23,al
    mov al,0xC3
    out 0x22,al
    mov al,ch
    out 0x23,al
.mapping:
    cache_read 0x08
    cmp al,4
    jne .done
    cache_read 0x62
    and al,0xFC
    mov cl,[fs:C_CHIP+18]
    and cl,1
    or cl,al
    call chipset_cyrix_5x86
    jnc .host
    test byte [fs:C_CHIP+18],2
    jz .host
    or cl,2
.host:
    cache_write 0x62,cl
.done:
    mov al,RTC_NMI_SELECT_MASK
    out 0x70,al
    popad
    ret

; CF=Cyrix 5x86. Failed vendor/legacy/DIR guards never program tuning bits.
chipset_cyrix_5x86:
    pushfd
    pushad
    pushfd
    pop eax
    mov ecx,eax
    xor eax,0x00200000
    push eax
    popfd
    pushfd
    pop eax
    xor eax,ecx
    test eax,0x00200000
    jz .legacy
    xor eax,eax
    cpuid
    cmp ebx,0x69727943
    jne .bad
    cmp edx,0x736E4978
    jne .bad
    cmp ecx,0x64616574
    jne .bad
    jmp .probe
.legacy:
    mov eax,ecx
    xor eax,0x00040000
    push eax
    popfd
    pushfd
    pop eax
    xor eax,ecx
    test eax,0x00040000
    jz .bad
    xor ax,ax
    sahf
    mov ax,5
    mov bl,2
    div bl
    lahf
    cmp ah,2
    jne .bad
.probe:
    mov al,0xC3
    out 0x22,al
    in al,0x23
    mov bl,al
    and al,0xFD
    out 0x23,al
    mov al,0xC0
    out 0x22,al
    in al,0x23
    mov al,0xC3
    out 0x22,al
    in al,0x23
    test al,2
    jnz .restore_bad
    mov al,bl
    or al,2
    out 0x23,al
    mov al,0xC0
    out 0x22,al
    in al,0x23
    mov al,0xC3
    out 0x22,al
    in al,0x23
    test al,2
    jz .restore_bad
    mov al,bl
    out 0x23,al
    mov al,0xFE
    out 0x22,al
    in al,0x23
    cmp al,0x28
    jb .bad
    cmp al,0x2F
    ja .bad
    popad
    popfd
    stc
    ret
.restore_bad:
    mov al,bl
    out 0x23,al
.bad:
    popad
    popfd
    clc
    ret
