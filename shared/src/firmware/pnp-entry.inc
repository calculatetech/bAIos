; Real POST facade. Reuse the existing complete settings/peripheral owners
; before any expansion consumer. Private module state never enters PM calls.
%ifdef M919_BOARD_DEFINITION
pnp_pci_initialize:
    call pnp_early
    jmp pci_initialize
%endif
pnp_publish_finish:
    call pnp_publish
    jmp pnp_finish_entry

pnp_early:
    pushf
    pushad
    call load_bios_state
    call settings_load
%ifdef M919_BOARD_DEFINITION
    mov bx,(CFG_PLATFORM_ISA_PCI_DEVICE << 3)+1
    call board_pci_device
    ; Establish the existing fixed VGA ROM decode before live ROM ownership.
    ; Relocatable BAR allocation still follows required ISA assignment.
    xor ebx,ebx
.fixed_pci:
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pci_read
    shr eax,16
    cmp ax,0x0300
    jne .next_pci
    call board_pci_device
.next_pci:
    call pci_next_function
    cmp bx,256
    jb .fixed_pci
%endif
%ifndef M919_BOARD_DEFINITION
    call ports_apply       ; M919's existing IDE owner already applies ports.
%endif
    call ide_apply_controller
    call pnp_publish
    call pnp_module_install
    jc .done
    mov bx,pnp_prepare
    call pnp_post_invoke
.done:
    popad
    popf
    ret

pnp_finish_entry:
    pushf
    cli
    pushad
    call load_bios_state
    mov bx,pnp_finish
    call pnp_post_invoke
    popad
    popf
    ret
