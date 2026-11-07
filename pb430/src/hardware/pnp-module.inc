; ACC E000 ROM-read window, identical to the retained-VGA staging owner.
; Copy the private upper32KiB-bank payload before either video branch can
; replace E000 reads with shadow RAM. F000 execution is never remapped.
pnp_allocate_callback:
    call pnp_journal_allocate
    retf
pnp_state_callback:
    call load_bios_state
    retf
pnp_release_callback:
    call pnp_journal_release
    retf
pnp_video_callback:
    call board_video_prepare
    retf
pnp_acc_read_callback:
    call acc_read
    retf
pnp_acc_write_callback:
    call acc_write
    retf
pnp_video_failed_callback:
    pb_stage 0xE5
    retf


pnp_module_install:
    pushad
    push ds
    push es
    mov dword [fs:PNP_MODULE_POINTER],0
    call pnp_journal_begin
    jc .failed
    mov ecx,(pnp_module_end-pnp_module_start+15)&~15
    call pnp_journal_allocate
    jc .release
    shr eax,4
    mov es,ax
    mov bp,ax
    mov al,2
    call acc_read
    push ax
    and al,0xD7
    mov ah,al
    mov al,2
    call acc_write
    mov ax,0xE000
    mov ds,ax
    cmp dword [0x8000],0x50494142
    jne .map_failed
    cmp dword [0x8004],0x0032504E
    jne .map_failed
    cmp word [0x8008],pnp_module_end-pnp_module_start
    jne .map_failed
    mov si,0x8000
    mov cx,0x8000
    xor bl,bl
.checksum:
    lodsb
    add bl,al
    loop .checksum
    test bl,bl
    jnz .map_failed
    mov si,0x8000
    xor di,di
    mov cx,pnp_module_end-pnp_module_start
    cld
    rep movsb
    mov si,0x8000
    xor di,di
    mov cx,pnp_module_end-pnp_module_start
    repe cmpsb
    jne .map_failed
    pop ax
    mov ah,al
    mov al,2
    call acc_write
    mov word [fs:PNP_MODULE_POINTER],pnp_module_entry
    mov [fs:PNP_MODULE_POINTER+2],bp
    pop es
    pop ds
    popad
    clc
    ret
.map_failed:
    pop ax
    mov ah,al
    mov al,2
    call acc_write
.release:
    call pnp_journal_release
.failed:
    pop es
    pop ds
    popad
    stc
    ret

%include "firmware/post-module-invoke.inc"
