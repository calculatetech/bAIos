bits 16
org 0x7C00
    cli
    xor ax,ax
    mov ss,ax
    mov sp,0x7B00
    mov ds,ax
    dec ax
    mov es,ax
    ; Read P2, then use only its standard AT A20 bit as HIMEM does.
    mov al,0xD0
    out 0x64,al
    xor cx,cx
.reply:
    in al,0x64
    test al,1
    loopz .reply
    jz failed
    in al,0x60
    mov dl,al
    or al,2
    call set_gate
    mov bl,[0x500]
    mov bh,[es:0x510]            ; FFFF:0510 = 100500h.
    and al,0xFD
    call set_gate
    mov byte [0x500],0xA5
    mov byte [es:0x510],0x5A
    cmp byte [0x500],0x5A
    sete dh                     ; Off must wrap to conventional RAM.
    or al,2
    call set_gate
    mov byte [0x500],0xA5
    mov byte [es:0x510],0x5A
    cmp byte [0x500],0xA5
    sete cl                     ; On must reach separate extended RAM.
    mov [0x500],bl
    mov [es:0x510],bh
    mov al,dl
    call set_gate
    and dh,cl
    test dh,dh
    jz failed
    mov al,0x5A
    out 0xE9,al
    hlt
set_gate:
    push ax
    call wait_input
    mov al,0xD1
    out 0x64,al
    call wait_input
    pop ax
    out 0x60,al
    push ax
    call wait_input
    pop ax
    ret
wait_input:
    push cx
    xor cx,cx
.wait:
    in al,0x64
    test al,2
    loopnz .wait
    pop cx
    jnz failed
    ret
failed:
    mov al,0xEE
    out 0xE9,al
    hlt
times 510-($-$$) db 0
dw 0xAA55
