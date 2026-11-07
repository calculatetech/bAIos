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
%include "firmware/post-module-invoke.inc"
