chipset_parity_apply:
    cmp byte [fs:C_CHIP+6],0
    jne .initialize
    in al,0x61
    or al,4
    out 0x61,al
    ret
.initialize:
    pushf
    cli
    pushad
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    wbinvd
    mov ebp,cr0
    mov eax,ebp
    or eax,0x60000000
    mov cr0,eax
    cache_data_enter
    ; Refresh existing values: cover live low RAM without destroying its state.
    xor edi,edi
    mov esi,0xA0000
.seed:
    mov eax,[gs:edi]
    mov [gs:edi],eax
    add edi,4
    cmp edi,esi
    jb .seed
    cmp edi,0xA0000
    jne .seeded
    test byte [fs:P_RAM_FLAGS],4
    jz .extended
    test byte [fs:BOARD_FAST_BOOT_SETTING],1
    jz .seeded
.extended:
    ; Esc and Fast Boot skip extended writes; parity still needs initialized data.
    mov edi,0x100000
    memory_installed_kib esi
    add esi,1024
    shl esi,10
    cmp edi,esi
    jb .seed
.seeded:
    wbinvd
    cache_data_leave
    mov cr0,ebp
    pop ax
    or al,4
    out 0x61,al
    and al,0xFB
    out 0x61,al
    popad
    popf
    ret
