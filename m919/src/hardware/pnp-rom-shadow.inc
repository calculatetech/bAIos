%include "hardware/cache-io.inc"
; Existing PCI ROM shadow transactions, unchanged except the resident host bridge.
pnp_board_pci_rom_writable:
    pushf
    cli
    pushad
    cache_read 0x55
    and al,0xBF
    mov bh,al
    mov bl,0x55
    wbinvd
    call pnp_module_host_write
    popad
    popf
    ret
pnp_board_pci_rom_shadow:
    pushf
    cli
    pushad
    cache_read 0x54
    mov edx,ebp
    shl dl,4
    or al,dl
    mov bh,al
    mov bl,0x54
    call pnp_module_host_write
    ; Preserve F shadow: copy the executing BIOS before global read enable.
    push ds
    push es
    mov ax,CFG_ROM_CODE_SEGMENT
    mov ds,ax
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x8000
    cld
    rep movsw
    cache_read 0x55
    or al,0x80
    mov bh,al
    mov bl,0x55
    wbinvd
    call pnp_module_host_write
    pop es
    pop ds
    popad
    popf
    ret
pnp_board_pci_rom_protect:
    pushf
    cli
    pushad
    cache_read 0x55
    or al,0x40
    mov bh,al
    mov bl,0x55
    wbinvd
    call pnp_module_host_write
    popad
    popf
    ret
pnp_module_host_write:
    call CFG_ROM_CODE_SEGMENT:pnp_host_write_callback
    ret
