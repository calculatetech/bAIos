; Type-zero bus-zero option ROMs. The board supplies 16-KiB shadow blocks.
pci_option_roms:
    mov byte [fs:M_PCI_ROM_USED],0
    mov byte [fs:M_PCI_ROM_RESERVED],0
    ; Reserve complete ISA images, including images that start below D000.
    mov dx,ROM_FIRST_SEG
.isa:
    cmp dx,PCI_ROM_LIMIT_SEG
    jae .devices
    mov ds,dx
    cmp word [0],0xAA55
    jne .isa_next
    movzx eax,byte [2]
    shl eax,5
    add ax,dx
    jc .isa_next
    cmp ax,PCI_ROM_LIMIT_SEG
    ja .isa_next
    mov di,dx
.reserve:
    cmp di,ax
    jae .isa_next
    cmp di,PCI_ROM_FIRST_SEG
    jb .reserve_next
    mov cx,di
    sub cx,PCI_ROM_FIRST_SEG
    shr cx,10
    mov bp,1
    shl bp,cl
    push dx
    mov dx,bp
    or [fs:M_PCI_ROM_RESERVED],dl
    pop dx
.reserve_next:
    add di,0x80
    jmp .reserve
.isa_next:
    add dx,0x80
    jmp .isa
.devices:
    xor ebx,ebx
.device:
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp ax,0xFFFF
    je .next
    test ax,ax
    jz .next
    cmp bx,[fs:M_VGA_BDF]
    je .next
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    shr eax,24
    cmp al,6                     ; Chipset/bridge reserved registers are not ROMs.
    je .next
    cmp al,3                     ; Display ROMs belong to video initialization.
    je .next
    mov eax,ebx
    shl eax,8
    or eax,0x8000000C
    call pci_read
    test eax,0x007F0000
    jnz .next
    call pci_rom_load
.next:
    call pci_next_function
    cmp bx,256
    jb .device
    xor ax,ax
    mov ds,ax
    mov es,ax
    ret

; BX device. Keep the original command and disable ROM decode on every exit.
pci_rom_load:
    pushad
    push ds
    push es
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    push ax
    mov cx,ax
    and cl,0xFD
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
    mov eax,ebx
    shl eax,8
    or eax,0x80000030
    mov ecx,0xFFFFFFFE
    call pci_write
    call pci_read
    mov esi,eax
    and esi,0xFFFFF800
    neg esi
    ; shortcut: first x86 image, <=64 KiB; extend for multi-image/EFI cards.
    cmp esi,0x10000
    ja .cleanup
    cmp esi,0x800
    jb .cleanup
    lea edx,[esi-1]
    test esi,edx
    jnz .cleanup
    mov edi,esi
    cmp edi,0x4000
    jae .blocks
    mov edi,0x4000
.blocks:
    shr edi,4
    mov ax,PCI_ROM_FIRST_SEG
.space:
    mov dx,ax
    add dx,di
    cmp dx,PCI_ROM_LIMIT_SEG
    ja .cleanup
    mov cx,di
    shr cx,10
    mov bp,1
    shl bp,cl
    dec bp
    mov cx,ax
    sub cx,PCI_ROM_FIRST_SEG
    shr cx,10
    shl bp,cl
    mov cl,[fs:M_PCI_ROM_USED]
    or cl,[fs:M_PCI_ROM_RESERVED]
    test bp,cx
    jz .map
    add ax,di
    jmp .space
.map:
    mov di,ax
    movzx ecx,ax
    shl ecx,4
    or ecx,1
    mov eax,ebx
    shl eax,8
    or eax,0x80000030
    call pci_write
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    mov cx,ax
    or cl,2
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
    mov ds,di
    cmp word [0],0xAA55
    jne .cleanup
    movzx ecx,byte [2]
    test ecx,ecx
    jz .cleanup
    shl ecx,9
    cmp ecx,esi
    ja .cleanup
    movzx edx,word [0x18]
    lea eax,[edx+0x18]
    cmp eax,ecx
    ja .cleanup
    cmp dword [edx],0x52494350
    jne .cleanup
    cmp byte [edx+0x14],0
    jne .cleanup
    mov esi,edx
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp eax,[esi+4]
    jne .cleanup
    mov ax,di
    call rom_validate
    jc .cleanup
    call board_pci_rom_writable
    mov es,di
    xor si,si
    xor di,di
    movzx ecx,byte [2]
    shl ecx,8
    cld
    rep movsw
    call board_pci_rom_shadow
    mov dx,ds
    mov [fs:ROM_POINTER+2],dx
    mov word [fs:ROM_POINTER],3
    mov eax,ebx
    shl eax,8
    or eax,0x80000030
    xor ecx,ecx
    call pci_write
    mov ax,bp
    or [fs:M_PCI_ROM_USED],al
    mov dx,ds
    call post_ui_rom
    xor ax,ax
    mov es,ax
    xor di,di
    mov ax,bx
    sti
    call option_rom_enter
    call board_pci_rom_protect
    ; Keep the ROM's command changes, but remove our temporary memory decode.
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    mov cx,ax
    pop ax
    and cx,0xFFFD
    and ax,2
    or cx,ax
    push cx
.cleanup:
    mov eax,ebx
    shl eax,8
    or eax,0x80000030
    xor ecx,ecx
    call pci_write
    pop cx
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
    pop es
    pop ds
    popad
    ret

; DX generic scan position: PCI images have already initialized exactly once.
pci_rom_skip:
    push ax
    push cx
    push bx
.block:
    cmp dx,PCI_ROM_FIRST_SEG
    jb .done
    cmp dx,PCI_ROM_LIMIT_SEG
    jae .done
    mov cx,dx
    sub cx,PCI_ROM_FIRST_SEG
    shr cx,10
    mov al,1
    shl al,cl
    test [fs:M_PCI_ROM_USED],al
    jz .done
    add dx,0x400
    and dx,0xFC00
    jmp .block
.done:
    pop bx
    pop cx
    pop ax
    ret
