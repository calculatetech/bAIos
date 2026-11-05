; D824 CPU-top alias: selected lower ROM is mirrored at FFFE0000h.
; Use the existing real INT15/AH87 owner after IVT/RTC/AT initialization.
; Its helper enables A20 for the copy and exits with NMI enabled/index0.
; Preserve caller IF through the real interrupt and our surrounding frame.
pnp_allocate_callback:
    call pnp_journal_allocate
    retf
pnp_state_callback:
    call load_bios_state
    retf
pnp_release_callback:
    call pnp_journal_release
    retf

pnp_module_install:
    pushf
    cli
    pushad
    push ds
    push es
    mov dword [fs:PNP_MODULE_POINTER],0
    call pnp_journal_begin
    jc .failed
    mov ecx,0x4000
    call pnp_journal_allocate
    jc .release
    mov ebp,eax
    sub sp,48
    mov si,sp
    push ss
    pop es
    ; Existing AH87 reads descriptors at ES:SI+10h and+18h, all32 base bits.
    mov word [ss:si+0x10],0xFFFF
    mov dword [ss:si+0x12],0x93FEC000
    mov word [ss:si+0x16],0xFF00
    mov word [ss:si+0x18],0xFFFF
    mov [ss:si+0x1A],eax
    mov byte [ss:si+0x1D],0x93
    mov word [ss:si+0x1E],0
    mov cx,0x2000
    mov ax,0x8700
    int 0x15
    lea sp,[si+48]
    jc .release
    shr ebp,4
    mov ax,bp
    mov es,ax
    cmp dword [es:0],0x50494142
    jne .release
    cmp dword [es:4],0x0032504E
    jne .release
    cmp word [es:8],pnp_module_end-pnp_module_start
    jne .release
    xor si,si
    xor bl,bl
    mov cx,0x4000
.checksum:
    mov al,[es:si]
    add bl,al
    inc si
    loop .checksum
    test bl,bl
    jnz .release
    mov word [fs:PNP_MODULE_POINTER],pnp_module_entry
    mov [fs:PNP_MODULE_POINTER+2],bp
    pop es
    pop ds
    popad
    popf
    clc
    ret
.release:
    call pnp_journal_release
.failed:
    pop es
    pop ds
    popad
    popf
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
