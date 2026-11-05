; Private POST callbacks stay in the established F000 code mapping.
%include "firmware/pnp-post-release.inc"
pnp_state_callback:
    call load_bios_state
    retf
pnp_pci_candidate:
    push bx
    mov bx,pnp_pci_candidate_core
    call pnp_post_invoke
    pop bx
    ret

%macro pnp_pci_callback 2
%1:
    call %2
    retf
%endmacro
pnp_pci_callback pnp_pci_read_callback,pci_read
pnp_pci_callback pnp_pci_write_callback,pci_write
pnp_pci_callback pnp_pci_command_callback,pci_command_write
pnp_pci_callback pnp_pci_next_callback,pci_next_function
pnp_pci_callback pnp_rom_validate_callback,rom_validate
pnp_pci_callback pnp_rom_writable_callback,board_pci_rom_writable
pnp_pci_callback pnp_rom_shadow_callback,board_pci_rom_shadow
pnp_pci_callback pnp_rom_protect_callback,board_pci_rom_protect
pnp_pci_callback pnp_rom_ui_callback,post_ui_rom
%unmacro pnp_pci_callback 2

; Existing M919 SMM startup preserves the complete generated E000 bank.
pnp_module_install:
    push ax
    push es
    mov ax,0xE000
    mov es,ax
    mov dword [fs:PNP_MODULE_POINTER],0
    cmp dword [es:pnp_module_start],0x50494142
    jne .bad
    cmp dword [es:pnp_module_start+4],0x0032504E
    jne .bad
    cmp word [es:pnp_module_start+8],pnp_module_end-pnp_module_start
    jne .bad
    mov word [fs:PNP_MODULE_POINTER],pnp_module_entry
    mov word [fs:PNP_MODULE_POINTER+2],0xE000
    pop es
    pop ax
    clc
    ret
.bad:
    pop es
    pop ax
    stc
    ret
pnp_post_invoke:
    cmp word [fs:PNP_MODULE_POINTER+2],0
    je .missing
    call far [fs:PNP_MODULE_POINTER]
    ret
.missing:
    stc
    ret
