%include "pc/pci.inc"

; UMC BF mode, VGA decode and board wiring stay in this adapter.
board_pci_device:
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    mov esi,eax
    shr esi,16
    cmp si,0x0300
    jne .ide
    cmp word [fs:M_VGA_BDF],0xFFFF
    jne .ide
    mov [fs:M_VGA_BDF],bx
    mov eax,ebx
    shl eax,8
    or eax,0x80000030
    mov ecx,0x000C0001
    call pci_write
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    mov cx,ax
    or cl,3                   ; Legacy VGA and its expansion ROM need decode.
    mov al,[fs:M_PCI_REJECTED]
    not al
    and cl,al
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
.ide:
    cmp si,0x0101
    jne .done
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp eax,0x673A1060
    je .bf
    cmp eax,0x673B1060
    jne .done
.bf:
    mov [fs:HW_IDE_BDF],bx    ; Presence prevents fallback to the AF window.
    mov byte [fs:HW_IDE_USABLE],0
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    mov ecx,eax
    mov al,ch
    and al,0x0A
    shr al,1                  ; AMI module44 B84A..B887: only switchable bits.
    not al
    and ch,al
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    pushfd
    cli
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFD
    mov al,ch
    out dx,al
    popfd
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    test ah,5
    jnz .rejected
    test byte [fs:M_PCI_REJECTED],1
    jnz .rejected
    mov byte [fs:HW_IDE_USABLE],1
    mov eax,ebx
    shl eax,8
    or eax,0x80000040
    mov ecx,0xFF30C900
    call pci_write
    add eax,4
    mov ecx,0xBBBB6666
    call pci_write
    jmp .done
.rejected:
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    mov cx,ax
    and cl,0xFC
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
.done:
    ret

board_pci_irq:
    mov eax,ebx
    shl eax,8
    or eax,0x8000003C
    call pci_read
    mov cl,ah
    test cl,cl
    jz .done
    cmp cl,4
    ja .done
    mov dl,bl
    shr dl,3
    sub dl,0x0C
    cmp dl,2
    ja .done
    movzx esi,dl
    shl si,2
    dec cl
    movzx edx,cl
    add si,dx
    movzx si,byte [cs:pci_slot_links+si]
    mov cl,[cs:pci_irq_map+si]
    mov eax,ebx
    shl eax,8
    or eax,0x8000003C
    pushfd
    cli
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    mov al,cl
    out dx,al
    popfd
.done:
    ret
; Four native AMI main POST tables: 9998/99A8/99B8 (not module44).
pci_slot_links db 0,1,2,3, 3,0,1,2, 2,0,1,3
pci_irq_map db CFG_PLATFORM_PCI_IRQ_A,CFG_PLATFORM_PCI_IRQ_B,CFG_PLATFORM_PCI_IRQ_C,CFG_PLATFORM_PCI_IRQ_D

board_pci_router:
    pushf
    cli
    mov bl,0x43
    mov bh,(CFG_PLATFORM_PCI_IRQ_A << 4) | CFG_PLATFORM_PCI_IRQ_B
    call isa_write
    mov bl,0x44
    mov bh,(CFG_PLATFORM_PCI_IRQ_C << 4) | CFG_PLATFORM_PCI_IRQ_D
    call isa_write
    mov eax,0x80000044 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11)
    call pci_read
    shr eax,16
    mov bh,al
    or bh,0x0F
    mov bl,0x46
    call isa_write
    mov eax,0x80000044 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11)
    call pci_read
    shr eax,24
    mov bh,al
    or bh,0x0F
    mov bl,0x47
    call isa_write
    mov dx,0x4D0
    in al,dx
    or al,((1 << CFG_PLATFORM_PCI_IRQ_A) | (1 << CFG_PLATFORM_PCI_IRQ_B) | (1 << CFG_PLATFORM_PCI_IRQ_C) | (1 << CFG_PLATFORM_PCI_IRQ_D)) & 0xFF
    out dx,al
    inc dx
    in al,dx
    or al,((1 << CFG_PLATFORM_PCI_IRQ_A) | (1 << CFG_PLATFORM_PCI_IRQ_B) | (1 << CFG_PLATFORM_PCI_IRQ_C) | (1 << CFG_PLATFORM_PCI_IRQ_D)) >> 8
    out dx,al
    popf
    ret

initialize_video:
    cmp word [fs:M_VGA_BDF],0xFFFF
    je .bad
    mov ax,0xC000
    call rom_validate
    jc .bad
    push ds
    push es
    mov bl,0x55
    xor bh,bh
    call host_write
    mov ax,CFG_ROM_RESET_SEGMENT
    mov ds,ax
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    rep movsw
    mov ax,0xC000
    mov ds,ax
    mov es,ax
    xor si,si
    xor di,di
    movzx cx,byte [2]
    mov ax,cx
    shl ax,5
    add ax,0xC000
    add ax,0x7F
    and ax,0xFF80
    mov [fs:HW_VGA_END],ax
    shl cx,8
    rep movsw
    mov bl,0x54
    mov bh,2                  ; C000..C7FF:32KiB, then two distinct16KiB chunks.
    cmp word [fs:HW_VGA_END],0xC800
    jbe .shadow
    or bh,4
    cmp word [fs:HW_VGA_END],0xCC00
    jbe .shadow
    or bh,8
.shadow:
    call host_write
    mov bl,0x55
    mov bh,0xC0
    call host_write
    wbinvd
    pop es
    pop ds
    mov word [fs:M_ROM_PTR],3
    mov word [fs:M_ROM_PTR+2],0xC000
    mov ax,[fs:M_VGA_BDF]
    call option_rom_enter
    xor ax,ax
    mov ds,ax
    mov es,ax
    cmp word [0x42],CFG_ROM_CODE_SEGMENT
    je .bad
    clc
    ret
.bad:
    stc
    ret

%include "pc/option-rom.inc"
%include "pc/pci-rom.inc"

; HB55 write protection is global; preserve the VGA and system shadows.
board_pci_rom_writable:
    pushf
    cli
    pushad
    mov eax,0x80000054 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    shr eax,8
    mov bh,al
    and bh,0xBF
    mov bl,0x55
    wbinvd
    call host_write
    popad
    popf
    ret
board_pci_rom_shadow:
    pushf
    cli
    pushad
    mov eax,0x80000054 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    mov edx,ebp
    shl dl,4
    mov bh,al
    or bh,dl
    mov bl,0x54
    wbinvd
    call host_write
    popad
    popf
    ret
board_pci_rom_protect:
    pushf
    cli
    pushad
    mov eax,0x80000054 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    shr eax,8
    mov bh,al
    or bh,0x40
    mov bl,0x55
    wbinvd
    call host_write
    popad
    popf
    ret
