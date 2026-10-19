; Bus-zero PCI mechanism 1. EAX address, ECX write data; DX scratch.
pci_read:
    pushfd
    cli
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    popfd
    ret
pci_write:
    pushfd
    cli
    push eax
    mov dx,0xCF8
    out dx,eax
    mov eax,ecx
    mov dx,0xCFC
    out dx,eax
    pop eax
    popfd
    ret
; Command writes must not clear write-one-to-clear status.
pci_command_write:
    pushfd
    cli
    push eax
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    mov ax,cx
    out dx,ax
    pop eax
    popfd
    ret

; BX current BDF. Skip nonexistent devices and unadvertised functions.
pci_next_function:
    test bl,7
    jnz .one
    movzx eax,bx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp ax,0xFFFF
    je .device
    test ax,ax
    jz .device
    movzx eax,bx
    shl eax,8
    or eax,0x8000000C
    call pci_read
    test eax,0x00800000
    jnz .one
.device:
    add bx,8
    ret
.one:
    inc bx
    ret

pci_initialize:
    mov dword [fs:M_PCI_MMIO],CFG_PLATFORM_PCI_MEMORY_BASE
    mov dword [fs:M_PCI_IO],CFG_PLATFORM_PCI_IO_BASE
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
    or eax,0x8000000C
    call pci_read
    shr eax,16
    and al,0x7F
    jnz .irq
    call pci_allocate_bars
    call board_pci_device
.irq:
    call board_pci_irq
.advance:
    call pci_next_function
    cmp bx,256
    jb .device
    jmp board_pci_router

; Type-zero endpoint BARs, bounded existing monotonic pools. No bus mastering.
pci_allocate_bars:
    pushad
    sub sp,16
    mov di,sp
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    and ax,0xFFF8
    mov [ss:di],ax
    mov word [ss:di+2],0       ; Allocated decode bits, rejected decode bits.
    mov cx,ax
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
    mov bp,0x10
.bar:
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    movzx edx,bp
    or eax,edx
    mov [ss:di+4],eax
    mov ecx,0xFFFFFFFF
    call pci_write
    call pci_read
    mov [ss:di+8],eax
    test eax,eax
    jz .zero
    test al,1
    jnz .io
    mov dl,al
    and dl,6
    cmp dl,4
    je .wide
    test dl,dl
    jnz .bad_memory
    jmp .memory
.wide:
    cmp bp,0x24
    jae .bad_memory
    mov eax,[ss:di+4]
    add eax,4
    mov ecx,0xFFFFFFFF
    call pci_write
    call pci_read
    cmp eax,0xFFFFFFFF
    jne .bad_memory
.memory:
    mov esi,[ss:di+8]
    and esi,0xFFFFFFF0
    neg esi
    jz .bad_memory
    lea edx,[esi-1]
    test esi,edx
    jnz .bad_memory
    mov ecx,[fs:M_PCI_MMIO]
    add ecx,edx
    jc .bad_memory
    not edx
    and ecx,edx
    mov edx,ecx
    add edx,esi
    jc .bad_memory
    cmp edx,CFG_PLATFORM_PCI_MEMORY_END
    ja .bad_memory
    mov [fs:M_PCI_MMIO],edx
    mov eax,[ss:di+8]
    and eax,15
    or ecx,eax
    or byte [ss:di+2],2
    jmp .assign
.io:
    test al,2
    jnz .bad_io
    mov esi,eax
    ; A 16-bit I/O BAR can return zeros in the unimplemented upper half.
    test esi,0xFFFF0000
    jnz .io_mask
    or esi,0xFFFF0000
.io_mask:
    and esi,0xFFFFFFFC
    neg esi
    cmp esi,0x10000
    ja .bad_io
    lea edx,[esi-1]
    test esi,edx
    jnz .bad_io
    mov ecx,[fs:M_PCI_IO]
    add ecx,edx
    jc .bad_io
    not edx
    and ecx,edx
    mov edx,ecx
    add edx,esi
    jc .bad_io
    cmp edx,0x10000
    ja .bad_io
    mov [fs:M_PCI_IO],edx
    or ecx,1
    or byte [ss:di+2],1
    jmp .assign
.bad_io:
    or byte [ss:di+3],1
    jmp .zero
.bad_memory:
    or byte [ss:di+3],2
.zero:
    xor ecx,ecx
.assign:
    mov eax,[ss:di+4]
    call pci_write
    mov edx,[ss:di+8]
    and dl,7
    cmp dl,4
    jne .next
    cmp bp,0x24
    jae .next
    add bp,4
    add eax,4
    xor ecx,ecx
    call pci_write
.next:
    add bp,4
    cmp bp,0x28
    jb .bar
    mov eax,ebx
    shl eax,8
    or eax,0x80000030
    xor ecx,ecx
    call pci_write
    mov cx,[ss:di]
    mov al,[ss:di+3]
    mov [fs:M_PCI_REJECTED],al
    not al
    and al,[ss:di+2]
    or cl,al
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
    add sp,16
    popad
    ret

; PCI BIOS 2.1: only documented result portions and saved CF may change.
pci_int1a:
    cmp ah,0xB1
    jne rtc_interrupt
    push bp
    mov bp,sp
    pushad
    cmp al,1
    je .present
    cmp al,2
    je .find
    cmp al,3
    je .find_class
    cmp al,8
    jb .unsupported
    cmp al,13
    ja .unsupported
    test bh,bh
    jnz .bad_register
    cmp di,0xFF
    ja .bad_register
    cmp al,8
    je .config
    cmp al,11
    je .config
    test di,1
    jnz .bad_register
    cmp al,9
    je .config
    cmp al,12
    je .config
    test di,3
    jnz .bad_register
.config:
    movzx eax,bx
    shl eax,8
    movzx edx,di
    and dl,0xFC
    or eax,edx
    or eax,0x80000000
    cli
    mov dx,0xCF8
    out dx,eax
    mov dx,di
    and dx,3
    add dx,0xCFC
    mov al,[ss:bp-4]
    cmp al,8
    je .r8
    cmp al,9
    je .r16
    cmp al,10
    je .r32
    cmp al,11
    je .w8
    cmp al,12
    je .w16
    mov eax,ecx
    out dx,eax
    jmp .ok
.w8:
    mov al,cl
    out dx,al
    jmp .ok
.w16:
    mov ax,cx
    out dx,ax
    jmp .ok
.r8:
    in al,dx
    mov [ss:bp-8],al
    jmp .ok
.r16:
    in ax,dx
    mov [ss:bp-8],ax
    jmp .ok
.r32:
    in eax,dx
    mov [ss:bp-8],eax
    jmp .ok
.present:
    mov byte [ss:bp-4],1
    mov word [ss:bp-16],0x0210
    mov byte [ss:bp-8],0
    mov dword [ss:bp-12],0x20494350
    jmp .ok
.find:
    cmp dx,0xFFFF
    je .bad_vendor
    movzx esi,si
    movzx edi,cx
    shl edi,16
    mov di,dx
    xor ecx,ecx
    jmp .search_start
.find_class:
    movzx esi,si
    mov edi,ecx
    and edi,0xFFFFFF
    mov ecx,8
.search_start:
    xor bx,bx
.search:
    movzx eax,bx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp ax,0xFFFF
    je .search_next
    test ax,ax
    jz .search_next
    test ecx,ecx
    jz .match
    movzx eax,bx
    shl eax,8
    or eax,0x80000008
    call pci_read
    shr eax,8
.match:
    cmp eax,edi
    jne .search_next
    test esi,esi
    jz .found
    dec esi
.search_next:
    call pci_next_function
    cmp bx,256
    jb .search
    mov al,0x86
    jmp .error
.found:
    mov [ss:bp-16],bx
.ok:
    mov byte [ss:bp-3],0
    and word [ss:bp+6],0xFFFE
    jmp .return
.bad_vendor:
    mov al,0x83
    jmp .error
.bad_register:
    mov al,0x87
    jmp .error
.unsupported:
    mov al,0x81
.error:
    mov [ss:bp-3],al
    or word [ss:bp+6],1
.return:
    popad
    pop bp
    iret
