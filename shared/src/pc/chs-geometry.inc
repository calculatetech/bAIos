get_chs_geometry:
    mov ax, [fs:S_GEOMETRY]
    test ax, ax
    jnz .return
    mov ax, 0x3F20
    cmp dword [fs:S_CAPACITY], 0x001F8000
    jbe .capacity_done
    mov al, 64
    cmp dword [fs:S_CAPACITY], 0x003F0000
    jbe .capacity_done
    mov al, 128
    cmp dword [fs:S_CAPACITY], 0x007E0000
    jbe .capacity_done
    mov al, 255
.capacity_done:
    ; The boot-sector BPB belongs only to the first logical disk.
    call hardware_bpb_owner
    jc .return
.bpb:
    push ds
    push ax
    xor ax, ax
    mov ds, ax
    pop ax
    cmp byte [0x7C00], 0xEB
    je .check_bpb
    cmp byte [0x7C00], 0xE9
    jne .done
.check_bpb:
    cmp word [0x7C0B], 512
    jne .done
    cmp word [0x7C0E], 0
    je .done
    cmp word [0x7C18], 0
    je .done
    cmp word [0x7C18], 63
    ja .done
    cmp word [0x7C1A], 0
    je .done
    cmp word [0x7C1A], 255
    ja .done
    cmp word [0x7DFE], 0xAA55
    jne .done
    mov ah, [0x7C18]
    mov al, [0x7C1A]
.done:
    pop ds
.return:
    ret

