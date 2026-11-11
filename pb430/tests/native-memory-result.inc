; Guest-owned result: unused video-page bytes after the2000 visible cells.
; Export BDA400..43F, including current40E and413, without altering the BDA.
    push word 0xB800
    pop es
    mov si,0x400
    mov di,4000
    mov cx,32
    rep movsw
