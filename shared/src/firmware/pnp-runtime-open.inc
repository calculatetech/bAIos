pnp_runtime_open:
    push dx
    call load_bios_state
    mov eax,[fs:PNP_RUNTIME]
    test eax,eax
    jz .bad
    movzx ecx,byte [fs:0]
    shl ecx,10
    lea edx,[eax+P_T_SIZE]
    cmp edx,ecx
    ja .bad
    call pnp_runtime_relative
    cmp dword [gs:si+P_T_MAGIC],PNP_RUNTIME_MAGIC
    jne .bad
    mov eax,[gs:si+P_T_COUNT]
    imul eax,PNP_PROVIDER_BYTES
    jo .bad
    add eax,edx
    jc .bad
    cmp eax,ecx
    ja .bad
    mov dx,fs
    cmp [gs:si+P_T_BASE_SEG],dx
    je .good
    call pnp_rebase_fdpts
.good:
    pop dx
    clc
    ret
.bad:
    pop dx
    stc
    ret
