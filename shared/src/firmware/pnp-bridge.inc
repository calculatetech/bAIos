; Private POST callbacks stay in the established F000 code mapping.
pnp_state_callback:
    call load_bios_state
    retf
pnp_pci_candidate:
    push bx
    mov bx,pnp_pci_candidate_core
    call pnp_post_invoke
    pop bx
    ret

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
