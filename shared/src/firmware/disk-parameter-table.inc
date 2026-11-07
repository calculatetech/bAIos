publish_disk_table:
    pushad
    push es
    mov ax, fs
    mov es, ax
    mov di, S_FDPT
    xor ax, ax
    mov cx, 8
    cld
    rep stosw
    cmp byte [fs:S_PRESENT], 1
    jne .done
    call get_chs_geometry
    mov [fs:S_FDPT+2], al
    mov [fs:S_FDPT+14], ah
    mov byte [fs:S_FDPT+7], 4
    mov word [fs:S_FDPT+5], 0xFFFF
    cmp byte [fs:S_IDE + IDE_TYPE], 0
    je .default_metadata
    mov ax, [fs:S_IDE + IDE_PRECOMP]
    mov [fs:S_FDPT+5], ax
.default_metadata:
    call get_chs_geometry
    cmp al, 8
    jbe .control
    mov byte [fs:S_FDPT+8], 8
.control:
    movzx ecx, al
    movzx edx, ah
    imul ecx, edx
    mov eax, [fs:S_CAPACITY]
    xor edx, edx
    div ecx
    cmp eax, 1024
    jbe .cylinders
    mov eax, 1024
.cylinders:
    mov [fs:S_FDPT], ax
    mov [fs:S_FDPT+12], ax
    cmp byte [fs:S_IDE + IDE_TYPE], 0
    je .done
    mov ax, [fs:S_IDE + IDE_LANDING]
    mov [fs:S_FDPT+12], ax
.done:
    pop es
    popad
    ret

; Publish the logical80h/81h disks, excluding packet devices.
