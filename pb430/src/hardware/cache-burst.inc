; Separate experiment after the complete stock cache parent has returned.
chipset_burst_disable:
    pushf
    cli
    pushad
    mov edx,cr0
    wbinvd
    mov eax,edx
    or eax,0x60000000
    mov cr0,eax
    wbinvd
    pb430_burst_clear
    mov cr0,edx
    popad
    popf
    ret

chipset_burst_policy:
    call chipset_refresh_policy
    pushf
    cli
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    cmp byte [fs:C_CHIP+1],0
    je .skip
    cmp byte [fs:C_CHIP+2],0
    je .skip
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .skip
    cmp byte [fs:HW_CACHE_ENABLED],1
    jne .skip
    cmp word [fs:S_EXTENDED_KIB],4096
    jb .skip
    mov ebp,cr0
    test ebp,0x60000001
    jnz .guard_failed
    in al,0xF2
    push ax
    mov al,4
    call acc_read
    cmp al,0x15
    jne .guard_failed
    sub sp,6
    mov di,sp
    sgdt [ss:di]
    in al,0x92
    push ax
    and al,0xFE
    or al,2
    out 0x92,al
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    wbinvd
    mov eax,ebp
    or eax,0x60000000
    mov cr0,eax
    wbinvd
    lgdt [cs:move_gdtr]
    or al,1
    mov cr0,eax
    jmp 8:.protected
.protected:
    mov ax,16
    mov ds,ax
    mov es,ax
    mov edx,0xA55AA55A
.pattern:
    ; Reuse ACCPROBE's address-dependent pattern across more than the L2 size.
    mov edi,0x100000
.write:
    mov eax,edi
    xor eax,edx
    mov [es:edi],eax
    add edi,4
    cmp edi,0x500000
    jb .write
    post_code_early 0x7A
    mov al,0x1D
    acc_commit_early 4
    in al,0xF3
    cmp al,0x1D
    jne .register_failed
    post_code_early 0x7B
    mov eax,ebp
    or al,1
    mov cr0,eax
    post_code_early 0x7C
    mov edi,0x100000
.read:
    mov eax,edi
    xor eax,edx
    cmp [es:edi],eax
    jne .memory_failed
    add edi,4
    cmp edi,0x500000
    jb .read
    not edx
    cmp edx,0xA55AA55A
    je .leave
    wbinvd
    mov eax,ebp
    or eax,0x60000001
    mov cr0,eax
    wbinvd
    pb430_burst_clear
    jmp .pattern
.leave:
    mov eax,ebp
    mov cr0,eax
    jmp 0xF000:.real
.real:
    pop dx
    pop ax
    and al,0xFE
    out 0x92,al
    mov si,sp
    o32 lgdt [ss:si]
    add sp,6
    pop ax
    out 0xF2,al
    out 0xED,al
    pop fs
    pop es
    pop ds
    mov al,dl
    out 0x61,al
    post_code_early 0x7D
    popad
    popf
    ret
.skip:
    post_code_early 0x7E
.return:
    pop fs
    pop es
    pop ds
    popad
    popf
    ret
.register_failed:
    mov bl,0xEC
    jmp .failed
.memory_failed:
    mov bl,0xED
.failed:
    wbinvd
    mov eax,ebp
    or eax,0x60000001
    mov cr0,eax
    wbinvd
    pb430_burst_clear
    mov al,bl
    out 0x80,al
    jmp hard_halt
.guard_failed:
    post_code_early 0xEF
    jmp hard_halt
