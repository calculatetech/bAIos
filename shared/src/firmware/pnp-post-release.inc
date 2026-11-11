; The existing accounting release is resident: publication may overwrite the
; private RAM module after its final far return, but must still release its RAM.
pnp_journal_release:
    pushad
    push ds
    call load_bios_state
    xor ax,ax
    mov ds,ax
    mov eax,[fs:PNP_JOURNAL_CURSOR]
    test eax,eax
    jz .external
    shr eax,10
    cmp [0x413],ax
    jb .external
    mov ax,[fs:PNP_JOURNAL_EXTERNAL_KIB]
    mov [0x413],ax
.external:
    mov dword [fs:PNP_JOURNAL_FIRST],0
    mov dword [fs:PNP_JOURNAL_COUNT],0
    mov dword [fs:PNP_JOURNAL_CURSOR],0
    mov dword [fs:PNP_JOURNAL_END],0
    pop ds
    popad
    ret
