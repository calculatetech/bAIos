prepare_chs:
    push cx
    push dx
    push bx
    mov [fs:S_COUNT], al
    mov byte [fs:S_DONE], 0
    test al, al
    jz .bad
    cmp al, 128                ; Legacy CHS permits a full 64 KiB transfer.
    ja .bad
    call chs_to_lba
    jc .bad
    mov [fs:S_LBA], eax
    pop bx
    mov [fs:S_BUFFER_OFF], bx
    mov [fs:S_BUFFER_SEG], es
    call validate_request
    pop dx
    pop cx
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    pop bx
    pop dx
    pop cx
    ret

; Translate one CHS address without any data-buffer or sector-count dependency.
chs_to_lba:
    push bx
    push edx
    call get_chs_geometry
    mov bx, ax
    mov al, cl
    and al, 0x3F
    jz .bad
    cmp al, bh
    ja .bad
    cmp dh, bl
    jae .bad
    movzx eax, ch
    push dx
    movzx edx, cl
    and edx, 0xC0
    shl edx, 2
    or eax, edx
    pop dx
    push dx
    movzx edx, bl
    imul eax, edx
    pop dx
    movzx edx, dh
    add eax, edx
    movzx edx, bh
    imul eax, edx
    movzx edx, cl
    and edx, 0x3F
    dec edx
    add eax, edx
    pop edx
    pop bx
    clc
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    pop edx
    pop bx
    ret

prepare_dap:
    cmp byte [ds:si], 0x10
    jne .bad
    cmp byte [ds:si + 1], 0
    jne .bad
    mov ax, [ds:si + 2]
    test ax, ax
    jz .bad
    cmp ax, 127
    ja .bad
    mov [fs:S_COUNT], al
    mov byte [fs:S_DONE], 0
    mov ax, [ds:si + 4]
    mov [fs:S_BUFFER_OFF], ax
    mov ax, [ds:si + 6]
    mov [fs:S_BUFFER_SEG], ax
    mov eax, [ds:si + 8]
    mov [fs:S_LBA], eax
    cmp dword [ds:si + 12], 0
    jne .bad
    call validate_request
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    ret

; EMM386 relocates the EBDA and updates 0040:000E. Never cache its segment
; across BIOS calls. OEM handlers also load the BDA pointer (e.g. F000:9CCC).
