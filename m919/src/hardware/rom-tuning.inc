; Explicit extra shadows supplement copies required by actual ROM providers.
board_rom_tuning:
    pushf
    cli
    pushad
    push ds
    push es
    wbinvd
    cache_read 0x55
    and al,0xBE
    mov cl,al
    cache_write 0x55,cl
    mov ax,0xC800
    mov bp,4
.region:
    mov bx,bp
    test [fs:C_CHIP+15],bl
    jz .next
    mov ds,ax
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x2000
    cld
    rep movsw
    cache_read 0x54
    or ax,bp
    mov cl,al
    cache_write 0x54,cl
.next:
    ; Cache macros clobber AX; derive the next source from the region index.
    shl bp,1
    cmp bp,0x100
    je .protect
    bsf ax,bp
    sub ax,2
    shl ax,10
    add ax,0xC800
    jmp .region
.protect:
    cache_read 0x55
    or al,0xC0
    mov cl,al
    cache_write 0x55,cl
    cache_read 0x50
    test al,0x80
    jz .done
    cache_read 0x55
    mov cl,[fs:C_CHIP+14]
    and cl,1
    or cl,al
    cache_write 0x55,cl
.done:
    wbinvd
    pop es
    pop ds
    popad
    popf
    ret
