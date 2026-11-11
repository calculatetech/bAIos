%include "pc/pci.inc"
; Standard PCI classification and UMC BF IDE controls from the local manual.
board_pci_fixed_resources:
    cmp bx,CFG_PLATFORM_HOST_PCI_DEVICE << 3
    je .fixed
    cmp bx,CFG_PLATFORM_ISA_PCI_DEVICE << 3
    je .fixed
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp eax,0x673A1060
    jne .allocated
.fixed:
    mov byte [fs:M_PCI_REJECTED],0
    stc
    ret
.allocated:
    clc
    ret
board_select_video:
    push bx
    call pnp_module_install
    jc .done
    mov bx,pnp_board_select_video
    call pnp_post_invoke
.done:
    pop bx
    ret
board_vga_disable:
    push ax
    push bx
    mov ax,bx
    mov bx,pnp_video_disable_entry
    call pnp_post_invoke
    pop bx
    pop ax
    ret
pnp_selected_video_callback:
    call board_pci_device
    retf

board_pci_device:
    cmp bx,CFG_PLATFORM_HOST_PCI_DEVICE << 3
    jne .peripheral
    call board_pci_host_setup
    ret
.peripheral:
    ; The BF's documented integrated IDE function may lack a multifunction flag.
    cmp bx,CFG_PLATFORM_ISA_PCI_DEVICE << 3
    jne .class
    push bx
    inc bx
    call board_pci_fixed_resources
    jnc .no_integrated_ide
    call board_pci_device
    call board_pci_irq
.no_integrated_ide:
    pop bx
.class:
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    mov esi,eax
    shr esi,16
    cmp si,0x0300
    jne .ide
    cmp [fs:M_VGA_BDF],bx
    jne board_vga_disable
.selected_vga:
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
    or cl,3
    mov al,[fs:M_PCI_REJECTED]
    not al
    and cl,al
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
    ret
.ide:
    cmp si,0x0101
    jne .done
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    call pci_read
    cmp eax,0x673A1060
    jne .done
    cmp [fs:HW_IDE_BDF],bx
    je .done
    mov [fs:HW_IDE_BDF],bx
    mov byte [fs:HW_IDE_USABLE],0
    ; PCI IDE programming interface: change only switchable native-mode bits.
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    mov ch,ah
    test ah,2
    jz .secondary
    and ch,0xFE
.secondary:
    test ah,8
    jz .interface
    and ch,0xFB
.interface:
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFD
    mov al,ch
    out dx,al
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    test ah,5
    jnz .rejected
    test byte [fs:M_PCI_REJECTED],1
    jnz .rejected
    ; Plain PIO0; honor secondary decode policy before the VGA BIOS runs.
    mov eax,ebx
    shl eax,8
    or eax,0x80000040
    mov ecx,0xFF30C900
    test byte [fs:BOARD_IDE_SECONDARY_DISABLE_POLICY],BOARD_IDE_SECONDARY_DISABLE_MASK
    jz .channels
    and ch,0xBF
.channels:
    call pci_write
    add eax,4
    mov ecx,0xBBBB6666
    call pci_write
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    mov cx,ax
    and cl,0xFB
    or cl,1
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
    mov byte [fs:HW_IDE_USABLE],1
    ret
.rejected:
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_read
    mov cx,ax
    and cl,0xF8
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pci_command_write
.done:
    ret
; AMI module44's normal 1060:8881 header policy, before VGA initialization.
board_pci_host_setup:
    pushf
    cli
    pushad
    cmp bx,CFG_PLATFORM_HOST_PCI_DEVICE << 3
    jne .done
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    cmp eax,0x88811060
    jne .done
    ; Reference order: 64-clock latency, then four-DWORD cache line.
    mov eax,0x8000000C | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFD
    mov al,0x40
    out dx,al
    dec dx
    mov al,4
    out dx,al
    mov eax,0x80000004 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    mov cx,ax
    ; Keep existing parity/SERR policy and latched status outside this owner.
    or cl,0x1F
    mov eax,0x80000004 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_command_write
.done:
    popad
    popf
    ret
board_pci_irq:
    ; The chipset manual does not describe this board's slot swizzle wiring.
    ; Advertise no assigned IRQ instead of importing a vendor wiring table.
    mov eax,ebx
    shl eax,8
    or eax,0x8000003C
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    mov al,0xFF
    cmp bx,[fs:HW_IDE_BDF]
    jne .write
    mov al,14
.write:
    out dx,al
    ret
board_pci_router:
    ; Saved slot IRQ policy is applied after active peripherals are published.
    ret
initialize_video:
    call board_vga_bus_policy
    mov ax,0xC000
    call rom_validate
    jc .bad
    mov ax,0xC000
    mov es,ax
    movzx ax,byte [es:2]
    shl ax,5
    add ax,0xC000
    add ax,0x7F
    and ax,0xFF80
    mov [fs:HW_VGA_END],ax
    call board_vga_rom_extent
    call board_vga_shadow
    mov word [fs:M_ROM_PTR],3
    mov word [fs:M_ROM_PTR+2],0xC000
    xor ax,ax
    mov ds,ax
    mov es,ax
    xor di,di
    mov ax,[fs:M_VGA_BDF]
    cmp ax,0xFFFF
    jne .provider
    xor ax,ax
.provider:
    mov dx,0xC000
    mov cl,2
    post_code 0x53
    call pnp_rom_enter
    post_code 0x54
    xor ax,ax
    mov ds,ax
    mov es,ax
    cmp word [0x42],CFG_ROM_CODE_SEGMENT
    je .bad
    call board_vga_rom_release
    board_video_blank 0
    clc
    ret
.bad:
    stc
    ret
; AMI module44 normal POST: HB51.04, IBC50.80, IBC56.60, in that order.
; Use the selected provider instead of probing C000 after PCI ROM mapping.
board_vga_bus_policy:
    pushf
    cli
    pushad
    xor si,si
    cmp word [fs:M_VGA_BDF],0xFFFF
    je .selected
    mov si,0x6004
.selected:
    cache_read 0x51
    and al,0xFB
    mov bx,si
    or al,bl
    mov cl,al
    cache_write 0x51,cl
    mov eax,0x80000050 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11)
    call pci_read
    and al,0x7F
    ror bl,3
    or al,bl
    mov bh,al
    mov bl,0x50
    call isa_write
    mov eax,0x80000054 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11)
    call pci_read
    shr eax,16
    and al,0x9F
    mov bx,si
    or al,bh
    mov bh,al
    mov bl,0x56
    call isa_write
    popad
    popf
    ret
board_vga_rom_extent:
    push ax
    push bx
    mov ax,[fs:HW_VGA_END]
    mov bx,[fs:M_VGA_BDF]
    call pci_vga_rom_extent
    mov [fs:HW_VGA_END],ax
    pop bx
    pop ax
    ret
board_vga_rom_release:
    push bx
    mov bx,[fs:M_VGA_BDF]
    call pci_vga_rom_release
    pop bx
    ret
; Fill both firmware banks before enabling their shared RAM read selection.
board_firmware_shadow:
    pushf
    cli
    cld
    pushad
    push ds
    push es
    cache_read 0x55
    and al,0x1E
    mov bh,al
    mov bl,0x55
    call host_write
    mov ax,0xE000
    mov ds,ax
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    rep movsw
    ; Persisted ESCD changes the ROM bank sum; protect its visible shadow from UMBs.
    mov si,0x800
    xor ax,ax
    mov ecx,0xF800
.checksum:
    cmp si,0x81C
    je .next_byte
    add ah,[si]
.next_byte:
    inc si
    a32 loop .checksum
    neg ah
    mov [es:0x81C],ah
    mov ax,CFG_ROM_CODE_SEGMENT
    mov ds,ax
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    rep movsw
    cache_read 0x54
    or al,1
    mov bh,al
    mov bl,0x54
    call host_write
    cache_read 0x55
    or al,0xC0
    mov bh,al
    mov bl,0x55
    call host_write
    pop es
    pop ds
    popad
    popf
    ret

board_vga_shadow:
    ; Preserve code when the VGA provider changes its own PCI ROM decoding.
    pushf
    cli
    cld
    pushad
    push ds
    push es
    cache_read 0x55
    and al,0x9E             ; Keep E/F firmware reads on their prepared RAM copies.
    mov bh,al
    mov bl,0x55
    call host_write
    mov ax,0xC000
    mov ds,ax
    mov es,ax
    xor si,si
    xor di,di
    mov cx,[fs:HW_VGA_END]
    sub cx,0xC000
    shl cx,3
    rep movsw
    cache_read 0x54
    mov bh,al
    or bh,3                 ; E firmware stays shadowed while C VGA is added.
    cmp word [fs:HW_VGA_END],0xC800
    jbe .regions
    or bh,4
    cmp word [fs:HW_VGA_END],0xCC00
    jbe .regions
    or bh,8
.regions:
    mov bl,0x54
    call host_write
    cache_read 0x55
    or al,0xC0
    mov bh,al
    mov bl,0x55
    call host_write
    pop es
    pop ds
    popad
    popf
    ret
%include "pc/option-rom.inc"
; Only POST deployment/scan code moves; public PCI services and all physical
; shadow/register owners remain resident with their existing contracts.
pci_option_roms:
    push bx
    mov bx,pnp_pci_option_roms
    call pnp_post_invoke
    pop bx
    ret
pci_rom_skip:
    push bx
    mov bx,pnp_pci_rom_skip
    call pnp_post_invoke
    pop bx
    ret
; Optional PCI ROM copying uses the described HB54/55 regional shadow controls.
%include "hardware/pci-tuning.inc"
