; Establish one primary display before resource ownership and video use.
pnp_board_select_video:
    mov word [fs:M_VGA_BDF],0xFFFF
    mov di,0xFFFF
    xor ebx,ebx
.scan:
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pnp_module_pci_read
    shr eax,16
    cmp ax,0x0300
    jne .next
    cmp di,0xFFFF
    jne .disable
    mov di,bx
.disable:
    call pnp_board_vga_disable       ; Remove warm PCI ROM/legacy decode first.
.next:
    call pnp_module_pci_next
    cmp bx,256
    jb .scan
    cmp byte [fs:C_VIDEO_ORDER],0
    jne .pci
    ; chipset_initialize already removes all warm C000 shadow reads.
    mov ax,0xC000
    call pnp_module_rom_validate
    jnc .done                   ; Valid ISA image; retain the FFFF sentinel.
.pci:
    cmp di,0xFFFF
    je .done
    mov bx,di
    mov [fs:M_VGA_BDF],bx
    call pnp_selected_video
.done:
    ret

; Also called after BAR allocation, which may re-enable endpoint decode.
pnp_board_vga_disable:
    mov eax,ebx
    shl eax,8
    or eax,0x80000030
    xor ecx,ecx
    call pnp_module_pci_write
    sub al,0x2C
    call pnp_module_pci_read
    mov cx,ax
    and cl,0xFC
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    jmp pnp_module_pci_command

pnp_selected_video:
    call CFG_ROM_CODE_SEGMENT:pnp_selected_video_callback
    ret
pnp_video_disable_entry:
    mov bx,ax
    jmp pnp_board_vga_disable
