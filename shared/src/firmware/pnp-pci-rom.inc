; Existing M919 POST-only PCI ROM deployment, in the qualified private module.
; Configuration, shadow policy and presentation retain their resident owners.
%define pci_read pnp_module_pci_read
%define pci_write pnp_module_pci_write
%define pci_command_write pnp_module_pci_command
%define pci_next_function pnp_module_pci_next
%define rom_validate pnp_module_rom_validate
%define board_pci_rom_writable pnp_board_pci_rom_writable
%define board_pci_rom_shadow pnp_board_pci_rom_shadow
%define board_pci_rom_protect pnp_board_pci_rom_protect
%define post_ui_rom pnp_module_rom_ui
%define option_rom_enter pnp_module_rom_enter
%include "hardware/pnp-rom-shadow.inc"
%include "pc/pci-rom.inc"
%undef pci_read
%undef pci_write
%undef pci_command_write
%undef pci_next_function
%undef rom_validate
%undef board_pci_rom_writable
%undef board_pci_rom_shadow
%undef board_pci_rom_protect
%undef post_ui_rom
%undef option_rom_enter
%macro pnp_pci_bridge 2
%1:
    call CFG_ROM_CODE_SEGMENT:%2
    ret
%endmacro
pnp_pci_bridge pnp_module_pci_read,pnp_pci_read_callback
pnp_pci_bridge pnp_module_pci_write,pnp_pci_write_callback
pnp_pci_bridge pnp_module_pci_command,pnp_pci_command_callback
pnp_pci_bridge pnp_module_pci_next,pnp_pci_next_callback
pnp_pci_bridge pnp_module_rom_validate,pnp_rom_validate_callback
pnp_pci_bridge pnp_module_rom_ui,pnp_rom_ui_callback
%unmacro pnp_pci_bridge 2
pnp_module_rom_enter:
    mov dx,[fs:ROM_POINTER+2]
    xor cl,cl
    jmp pnp_initialize_image
