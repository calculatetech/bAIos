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
pnp_pci_callback pnp_rom_ui_callback,post_ui_rom
pnp_pci_callback pnp_host_write_callback,host_write
%unmacro pnp_pci_callback 2

%include "hardware/pnp-module.inc"
