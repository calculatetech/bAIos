initialize_video:
    post_code 0x3C
    pushf
    cli
    pushad
    push ds
    push es
    mov ax,0xC000
    mov ds,ax
    cmp word [0],0xAA55
    jne .failed
    movzx bp,byte [2]
    test bp,bp
    jz .failed
    cmp bp,0x80
    ja .failed
    post_code 0x3D
    xor si,si
    xor bx,bx
.unit:
    mov cx,512
.sum:
    lodsb
    add bl,al
    loop .sum
    dec bp
    jnz .unit
    test bl,bl
    jnz .failed
    post_code 0x3E
    mov [fs:HW_VIDEO_SS],ss
    mov [fs:HW_VIDEO_SP],sp
    ; MR888C/88BF..88CF: IF set, IRQ0/1 masked, DS=ROM, ES=BIOS data area.
    mov ax,0x40
    mov es,ax
    mov si,0x67
    mov word [es:si],3
    mov [es:si+2],ds
    movzx ax,byte [2]
    shl ax,5
    mov dx,ds
    add dx,ax
    xor di,di
    sti
    call far [es:si]
    post_code_early 0x3F        ; Report return before touching the ROM's stack/state.
    cli
    xor ax,ax
    mov fs,ax
    mov fs,[fs:0x40E]
    mov ss,[fs:HW_VIDEO_SS]
    mov sp,[fs:HW_VIDEO_SP]
    cld
    post_code 0x42
    xor ax,ax
    mov ds,ax
    mov es,ax
    movzx eax,word [0x42]
    shl eax,4
    movzx edx,word [0x40]
    add eax,edx
    cmp eax,0xC0000
    jb .failed
    cmp eax,0xD0000
    jae .failed
    ; Keep the VGA ROM's fallback; aliasing INT42 to INT10 recurses on unknown calls.
    mov ax,3
    int 0x10
    post_code 0x40
    pop es
    pop ds
    popad
    popf
    clc
    ret
.failed:
    pop es
    pop ds
    popad
    popf
    stc
    ret
