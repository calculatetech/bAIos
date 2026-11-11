; Existing non-executing VGA selection/staging; physical operations unchanged.
    post_code 0x3C
    pushf
    cli
    pushad
    push ds
    push es
    mov ax,0xC000
    mov ds,ax
    cmp word [0],0xAA55
    je .present
    mov byte [fs:HW_VGA_REQUIRED],1
    mov al,2
    call acc_read
    and al,0xD7
    mov ah,al
    mov al,2
    call acc_write
    mov ax,0xE000
    mov ds,ax
    mov ax,0x2000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x4000
    rep movsw
    post_code 0x3D
    mov al,2
    call acc_read
    or al,9
    mov ah,al
    mov al,2
    call acc_write
    mov ax,0xE000
    mov es,ax
    xor ax,ax
    xor di,di
    mov cx,0x4000
    rep stosw
    mov ax,0x2000
    mov ds,ax
    mov ax,0xC000
    mov es,ax
    xor si,si
    xor di,di
    mov cx,0x4000
    rep movsw
    post_code 0x3E
.present:
    mov ax,0xC000
    mov ds,ax
    cmp word [0],0xAA55
    jne .failed
    movzx bp,byte [2]
    test bp,bp
    jz .failed
    cmp bp,0x80            ; The declared provider must fit the C000 segment.
    ja .failed
    cmp byte [fs:HW_VGA_REQUIRED],1
    jne .external
    cmp bp,0x40            ; The retained onboard provider is exactly32KiB.
    jne .failed
.external:
    xor bx,bx
    xor si,si
.sum_unit:
    mov cx,512
.sum:
    lodsb
    add bl,al
    loop .sum
    dec bp
    jnz .sum_unit
    test bl,bl
    jnz .failed
    post_code 0x3F ; The complete declared provider header and checksum passed.
    pop es
    pop ds
    popad
    popf
    clc
    ret
.failed:
    pb_stage 0xE5
    pop es
    pop ds
    popad
    popf
    stc
    ret
