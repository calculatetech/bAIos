; Boca N2.6 calls F000:F065 for a detected MDA/CGA adapter during installation.
; MR BIOS C582..C64C supplies its mode-set service before VGA owns INT1Dh.
times 0xF065-($-$$) db 0xFF
legacy_video:
    cmp ah,0
    jne .done
    cmp al,3
    je .set
    cmp al,7
    jne .done
.set:
    sti
    cld
    pushad
    push es
    push ds
    push ax
    mov ax,0x40
    mov ds,ax
    pop ax
    mov bx,0xB000
    ; Select the same adapter as MR's equipment-word predicate.
    push ax
    mov al,[0x10]
    and al,0x30
    cmp al,0x30
    pop ax
    je .mono
    mov bh,0xB8
.mono:
    mov es,bx
    mov bx,es
    cmp bh,0xB0
    jne .color
    mov dx,0x3B4
    mov al,7
    jmp .mode
.color:
    mov dx,0x3D4
    cmp al,6
    jbe .mode
    mov al,[0x10]
    shr al,4
    and al,2
.mode:
    cwde
    mov bx,ax
    mov si,ax
    cmp al,6
    jne .table
    dec si
.table:
    shr si,1
    shl si,4
    xor di,di
    mov byte [0x84],24
    mov [di+0x63],dx
    mov [di+0x49],al
    mov al,[cs:legacy_video_columns+bx]
    mov [di+0x4A],ax
    mov al,[cs:legacy_video_mode_controls+bx]
    mov [di+0x65],al
    and bl,0xFE
    mov cx,[cs:legacy_video_page_sizes+bx]
    mov [di+0x4C],cx
    and al,0x37
    add dl,4
    out dx,al
    out 0xEB,ax
    sub dl,4
    push ds
    xor ax,ax
    mov ds,ax
    lds bx,[0x74]
    add si,bx
    mov bx,[si+10]
    xor al,al
.crtc:
    out dx,al
    out 0xEB,ax
    inc dx
    mov ah,al
    lodsb
    out dx,al
    mov al,ah
    out 0xEB,ax
    dec dx
    inc ax
    cmp al,0x10
    jb .crtc
    pop ds
    xchg bh,bl
    mov [di+0x60],bx
    mov byte [di+0x62],0
    add dx,5
    mov bl,[di+0x49]
    mov al,0x3F
    cmp bl,6
    je .palette
    mov al,0x30
.palette:
    mov [di+0x66],al
    out dx,al
    mov ax,0x0720
    mov cx,0x0800
    ja .clear
    cmp bl,3
    mov ch,0x20
    jbe .clear
    xor ax,ax
.clear:
    rep stosw
    xor ax,ax
    mov di,0x4E
    push ds
    pop es
    mov cx,9
    rep stosw
    dec dx
    mov al,[0x65]
    out dx,al
    pop ds
    pop es
    popad
.done:
    iret

; MR BIOS F0A4..F0FB: four CRTC records and their mode lookup tables.
legacy_video_params:
    db 0x38,0x28,0x2D,0x0A,0x1F,0x06,0x19,0x1C,0x02,0x07,0x06,0x07,0,0,0,0
    db 0x71,0x50,0x5A,0x0A,0x1F,0x06,0x19,0x1C,0x02,0x07,0x06,0x07,0,0,0,0
    db 0x38,0x28,0x2D,0x0A,0x7F,0x06,0x64,0x70,0x02,0x01,0x06,0x07,0,0,0,0
    db 0x61,0x50,0x52,0x0F,0x19,0x06,0x19,0x19,0x02,0x0D,0x0B,0x0C,0,0,0,0
legacy_video_page_sizes: dw 0x0800,0x1000,0x4000,0x4000
legacy_video_columns: db 40,40,80,80,40,40,80,80
legacy_video_mode_controls: db 0x2C,0x28,0x2D,0x29,0x2A,0x2E,0x1E,0x29
