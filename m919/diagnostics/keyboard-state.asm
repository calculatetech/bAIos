bits 16
org 0x100

    push fs
    push cs
    pop ds
    push cs
    pop es
    cld
    pushf
    cli
    mov ax,0x40
    mov fs,ax
    mov si,fields
    mov di,snapshot
    mov cx,field_count
.capture:
    lodsw
    mov bx,ax
    mov ax,[fs:bx]
    stosw
    loop .capture
    popf
    pop fs
    and word [snapshot],0xFF
    and word [snapshot+2],0xFF
    and word [snapshot+4],0xFF
    and word [snapshot+14],0xFF
    and word [snapshot+16],0xFF
    ; No controller commands, input reads, or keyboard-state writes.
    xor dx,dx
    mov al,[snapshot]
    and al,15
    mov dl,al
    shl dx,4
    mov al,[snapshot+2]
    and al,3
    or dl,al
    shl dx,4
    mov al,[snapshot+4]
    and al,15
    or dl,al
    shl dx,4
    mov bx,[snapshot+10]
    mov cx,[snapshot+12]
    cmp bx,cx
    jae .invalid
    mov ax,bx
    or ax,cx
    or ax,[snapshot+6]
    or ax,[snapshot+8]
    test al,1
    jnz .invalid
    mov ax,[snapshot+6]
    cmp ax,bx
    jb .invalid
    cmp ax,cx
    jae .invalid
    mov ax,[snapshot+8]
    cmp ax,bx
    jb .invalid
    cmp ax,cx
    jae .invalid
    add ax,2
    cmp ax,cx
    jb .next
    mov ax,bx
.next:
    cmp ax,[snapshot+6]
    jne .pause
    or dl,2
    jmp .pause
.invalid:
    or dl,1
.pause:
    cmp byte [snapshot+14],0
    je .owner
    or dl,4
.owner:
    cmp byte [snapshot+16],0
    je .print
    or dl,8
.print:
    mov ax,dx
    mov di,message+1
    call hex_word
    mov si,snapshot
    mov di,details
    mov cx,field_count
.detail:
    lodsw
    call hex_word
    mov al,' '
    stosb
    loop .detail
    mov dx,message
    mov ah,9
    int 0x21
    mov ax,0x4C00
    int 0x21

hex_word:
    push cx
    push bx
    mov bx,ax
    mov cx,4
.digit:
    rol bx,4
    mov al,bl
    and al,15
    add al,'0'
    cmp al,'9'
    jbe .store
    add al,7
.store:
    stosb
    loop .digit
    pop bx
    pop cx
    ret

fields dw 0x17,0x18,0x96,0x1A,0x1C,0x80,0x82,0xA7,0xA6
field_count equ ($-fields)/2
snapshot times field_count dw 0
message db 'K0000  F1 F2 Ext Head Tail Start End Pause Owner: '
details times field_count*5 db ' '
    db 13,10,'$'
