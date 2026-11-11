fill_edd_parameters:
    cmp word [ds:si], 26
    jb .bad
    movzx eax, si
    add eax, 26
    cmp eax, 0x10000
    ja .bad
    xor eax, eax
    mov ax, ds
    shl eax, 4
    movzx edx, si
    add eax, edx
    mov edx, eax
    add edx, 26
    call check_disk_buffer
    jc .bad
.buffer_safe:
    mov word [ds:si], 26
    mov word [ds:si + 2], 2
    call get_chs_geometry
    push ax
    movzx ecx, al
    movzx edx, ah
    imul ecx, edx
    mov eax, [fs:S_CAPACITY]
    xor edx, edx
    div ecx
    mov [ds:si + 4], eax
    pop ax
    movzx ecx, al
    mov [ds:si + 8], ecx
    movzx ecx, ah
    mov [ds:si + 12], ecx
    mov eax, [fs:S_CAPACITY]
    mov [ds:si + 16], eax
    mov dword [ds:si + 20], 0
    mov word [ds:si + 24], 512
    clc
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    ret

