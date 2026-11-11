; Real POST facade. Reuse the existing complete settings/peripheral owners
; before any expansion consumer. Private module state never enters PM calls.
%ifdef M919_BOARD_DEFINITION
pnp_pci_initialize:
    post_code 0x50
    call pnp_early
    post_code 0x51
    jmp pci_initialize
%endif
%ifndef BOARD_PNP_SETUP_LATE
%include "firmware/pnp-post-display.inc"
%endif

; Actual caller-selected image, before its first device use. Private POST code
; validates/initializes once and connects a selected display before INT10.
pnp_rom_enter:
    push bx
    mov bx,pnp_initialize_image
    call pnp_post_invoke
    pop bx
    ret

pnp_early:
    pushf
    pushad
    call load_bios_state
    call settings_load
%ifdef M919_BOARD_DEFINITION
    mov bx,(CFG_PLATFORM_ISA_PCI_DEVICE << 3)+1
    call board_pci_device
    call board_select_video
%endif
%ifndef M919_BOARD_DEFINITION
    call ports_apply       ; M919's existing IDE owner already applies ports.
%endif
    call ide_apply_controller
    call pnp_publish
    call pnp_module_install
    jc .done
    mov bx,pnp_prepare_video
    call pnp_post_invoke
.done:
    popad
    popf
    ret

; Called after RAM, cache and fixed ports, before drive probes.
pnp_configure_isa:
    pushf
    pushad
    push fs
    call load_bios_state
    cmp byte [fs:C_PNP+PNP_CLEAR],0
    je .configure
    mov al,10
    call post_status
.configure:
    mov bx,pnp_configure_post
    call pnp_post_invoke
    pop fs
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
    jc .incomplete
    ; The private epilogue and RETF have completed before this first copy.
    call pnp_promote_runtime
    jc .incomplete
    cmp byte [fs:C_PNP+PNP_CLEAR],0
    je .release
    mov al,11
    call post_status
%ifdef BOARD_ESCD_SOURCE
    call pnp_escd_clear_post
    jc .retry
%endif
    call settings_nv6_retire
    jc .retry
    mov al,12
    call post_status
    jmp .release
.incomplete:
    call CFG_ROM_CODE_SEGMENT:pnp_incomplete_callback
    cmp byte [fs:C_PNP+PNP_CLEAR],0
    je .release
.retry:
    mov al,13
    call post_status
.release:
    mov dword [fs:PNP_MODULE_POINTER],0
    call pnp_journal_release
    popad
.atomic_end:
    popf
    ret

%include "firmware/pnp-promote.inc"
%include "firmware/settings-nv6-retire.inc"
