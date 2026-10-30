; Board routes from the identical $IRT tables in all four original AMI ROMs.
; Rows are devices 0C/0D/0E, columns INTA..INTD, values routing links 0..3.
board_pci_slot_links db 0,1,2,3, 3,0,1,2, 2,0,1,3
board_pci_irq_values db 0,4,5,7,9,10,11,12,14,15,3,0xFF
board_pci_irq_priority db 11,12,9,10,5,3,4,7,14,15,0

; Apply after the active peripheral policy is published, before option ROMs.
board_pci_runtime_policy:
    pushf
    cli
    pushad
    push ds
    xor ax,ax
    mov ds,ax
    mov bp,0xDEB8
    mov si,0x400
.serial:
    lodsw
    cmp ax,0x3F8
    je .irq4
    cmp ax,0x3E8
    je .irq4
    cmp ax,0x2F8
    je .irq3
    cmp ax,0x2E8
    jne .serial_next
.irq3:
    and bp,~(1 << 3)
    jmp .serial_next
.irq4:
    and bp,~(1 << 4)
.serial_next:
    cmp si,0x408
    jb .serial
    mov si,0x408
.parallel:
    lodsw
    test ax,ax
    jz .parallel_next
    cmp ax,0x278
    jne .irq7
    and bp,~(1 << 5)
    jmp .parallel_next
.irq7:
    and bp,~(1 << 7)
.parallel_next:
    cmp si,0x40E
    jb .parallel
    cmp byte [fs:C_PORTS+P_FLOPPY],0
    je .ide
    and bp,~(1 << 6)
.ide:
    cmp byte [fs:HW_IDE_USABLE],0
    je .allocate
    cmp byte [fs:C_IDE],0
    je .allocate
    and bp,~((1 << 14) | (1 << 15))
.allocate:
    mov ax,bp
    xor ax,0xDEB8             ; Active onboard ISA sources must return to edge.
    cmp byte [fs:C_PORTS+P_FLOPPY],0
    je .isa_mask
    or ax,1 << 6
.isa_mask:
    push ax
    mov [fs:HW_PCI_USED_IRQS],bp
    xor di,di
.link:
    mov bx,di
    shr bx,1
    mov al,[fs:C_CHIP+16+bx]
    test di,1
    jz .selection
    shr al,4
.selection:
    and ax,15
    mov bx,ax
    mov al,[cs:board_pci_irq_values+bx]
    cmp al,0xFF
    je .selected
    test al,al
    jnz .explicit
    mov si,board_pci_irq_priority
.automatic:
    mov al,[cs:si]
    inc si
    test al,al
    jz .unavailable
    movzx bx,al
    bt bp,bx
    jnc .automatic
    btr bp,bx
    jmp .selected
.explicit:
    movzx bx,al
    bt [fs:HW_PCI_USED_IRQS],bx
    jnc .unavailable
    btr bp,bx
    jmp .selected
.unavailable:
    mov al,0xFF
.selected:
    mov [fs:HW_PCI_LINKS+di],al
    inc di
    cmp di,4
    jb .link
    mov word [fs:HW_PCI_ROUTE_MASKS],0
    mov word [fs:HW_PCI_LEVEL_IRQS],0
    mov word [fs:HW_PCI_USED_IRQS],0
    xor ebx,ebx
.device:
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp ax,0xFFFF
    je .advance
    test ax,ax
    jz .advance
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    shr eax,16
    cmp ax,0x0300
    jne .pin
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    mov cx,ax
    and cx,0xFFDF
    test byte [fs:C_CHIP+18],8
    jz .palette
    or cx,0x20
.palette:
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
.pin:
    mov ax,bx
    and al,0xF8
    sub ax,0x60
    cmp ax,0x10
    ja .advance
    shr ax,1
    mov di,ax
    mov eax,ebx
    shl eax,8
    or eax,0x8000003C
    call pci_read
    cmp ah,1
    jb .advance
    cmp ah,4
    ja .advance
    movzx si,ah
    dec si
    add si,di
    movzx di,byte [cs:board_pci_slot_links+si]
    mov cl,[fs:HW_PCI_LINKS+di]
    cmp cl,0xFF
    je .line
    bts word [fs:HW_PCI_ROUTE_MASKS],di
    movzx si,cl
    bts [fs:HW_PCI_USED_IRQS],si
    cmp cl,14
    jb .level
    test byte [fs:C_CHIP+19],1
    jz .line
.level:
    bts [fs:HW_PCI_LEVEL_IRQS],si
    add di,8
    bts word [fs:HW_PCI_ROUTE_MASKS],di
.line:
    mov eax,ebx
    shl eax,8
    or eax,0x8000003C
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    mov al,cl
    out dx,al
.advance:
    call pci_next_function
    cmp bx,256
    jb .device
    mov si,HW_PCI_LINKS
    mov di,0x43
.nibbles:
    mov bh,[fs:si]
    and bh,15
    shl bh,4
    mov al,[fs:si+1]
    and al,15
    or bh,al
    mov ax,di
    mov bl,al
    call isa_write
    add si,2
    inc di
    cmp di,0x45
    jb .nibbles
    mov eax,0x80000044 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11)
    call pci_read
    mov ecx,eax
    and ecx,0xF0F0FFFF
    mov al,[fs:HW_PCI_ROUTE_MASKS]
    and al,15
    movzx eax,al
    shl eax,16
    or ecx,eax
    mov al,[fs:HW_PCI_ROUTE_MASKS+1]
    and al,15
    movzx eax,al
    shl eax,24
    or ecx,eax
    mov eax,0x80000044 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11)
    call pci_write
    pop cx
    or cx,[fs:HW_PCI_USED_IRQS]
    not cx
    mov bx,[fs:HW_PCI_LEVEL_IRQS]
    mov dx,0x4D0
    in al,dx
    and al,cl
    or al,bl
    out dx,al
    inc dx
    in al,dx
    and al,ch
    or al,bh
    out dx,al
    pop ds
    popad
    popf
    ret
