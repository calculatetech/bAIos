; S3 DB014-B (March1995), sections14/15/17: read only named controls.
; CR45 reads reset the cursor color stack. Never sweep the CRTC register space.
bits 16
org 0x100
start:
    cld
    push cs
    pop ds
    smsw ax
    test al,1
    jnz refuse_mode
    mov si,title
    call puts
    mov ax,0xB101
    int 0x1A
    jc refuse_pci
    test ah,ah
    jnz refuse_pci
    cmp edx,0x20494350
    jne refuse_pci
    mov ax,0xB103
    mov ecx,0x030000
    xor si,si
    int 0x1A
    jc refuse_pci
    test ah,ah
    jnz refuse_pci
    mov [bdf],bx
    xor di,di
    mov bp,pci_identity
    mov cx,5
.pci:
    pushad
    mov bx,[bdf]
    mov ax,0xB108
    int 0x1A
    jc refuse_pci
    test ah,ah
    jnz refuse_pci
    mov [bp],cl
    popad
    inc bp
    inc di
    loop .pci
    cmp dword [pci_identity],0x88115333
    jne refuse_card
    mov al,[pci_identity+4]
    and al,3
    cmp al,3
    jne refuse_card
    mov ah,0x0F
    int 0x10
    and al,0x7F
    cmp al,3
    je .text
    cmp al,7
    jne refuse_text
.text:
    mov [old_mode],al
    mov si,rom_title
    call puts
    call rom_fingerprint
    mov si,text_title
    call puts
    call snapshot
    jc refuse_card
    call print_snapshot
    mov si,graphics_title
    call puts
    call graphics_capture
    mov si,planar_title
    call puts
    mov byte [planar],1
    call graphics_capture
    mov si,complete
    call puts
    mov ax,0x4C00
    int 0x21
graphics_capture:
    mov al,0x13
    call set_mode
    cmp byte [planar],0
    je .capture
    call doom_planar
.capture:
    call snapshot
    pushf
    ; Restore text before any output/error path can exit or hit a DOS error.
    mov al,[old_mode]
    call set_mode
    popf
    jc refuse_card
    call print_snapshot
    ret
refuse_mode:
    mov si,real_message
    jmp refused
refuse_pci:
    mov si,pci_message
    jmp refused
refuse_card:
    mov si,card_message
    jmp refused
refuse_text:
    mov si,text_message
refused:
    call puts
    mov ax,0x4C02
    int 0x21

set_mode:
    pushad
    push ds
    push es
    push fs
    push gs
    xor ah,ah
    int 0x10
    pop gs
    pop fs
    pop es
    pop ds
    popad
    cld
    ret

; Retained DOSBENCH DOOM I_InitGraphics: unchain the standard mode13 aperture.
; No S3 private timing changes; the following BIOS mode restore owns cleanup.
doom_planar:
    pushf
    cli
    mov dx,0x3C4
    mov al,4
    out dx,al
    inc dx
    in al,dx
    and al,0xF7
    or al,4
    out dx,al
    mov dx,0x3CE
    mov al,5
    out dx,al
    inc dx
    in al,dx
    and al,0xEC
    out dx,al
    dec dx
    mov al,6
    out dx,al
    inc dx
    in al,dx
    and al,0xFD
    out dx,al
    mov dx,0x3C4
    mov ax,0x0F02
    out dx,ax
    popf
    push es
    mov ax,0xA000
    mov es,ax
    xor ax,ax
    xor di,di
    mov cx,0x8000
    rep stosw
    pop es
    pushf
    cli
    mov dx,0x3D4
    mov al,0x14
    out dx,al
    inc dx
    in al,dx
    and al,0xBF
    out dx,al
    dec dx
    mov al,0x17
    out dx,al
    inc dx
    in al,dx
    or al,0x40
    out dx,al
    mov dx,0x3CE
    mov al,4
    out dx,al
    popf
    ret

snapshot:
    pushf
    cli
    pushad
    mov byte [identity_ok],0
    mov dx,0x3CC
    in al,dx
    mov [misc],al
    and al,1
    mov dx,0x3B4
    jz .port
    mov dx,0x3D4
.port:
    mov [cr_port],dx
    in al,dx
    mov [cr_index],al
    mov al,0x38
    call cr_read
    mov [lock38],al
    mov ax,0x4838
    call cr_write
    mov al,0x39
    call cr_read
    mov [lock39],al
    mov ax,0xA539
    call cr_write
    mov al,0x2D
    call cr_read
    cmp al,0x88
    jne .restore_cr
    mov al,0x2E
    call cr_read
    cmp al,0x11
    jne .restore_cr
    mov byte [identity_ok],1
    mov si,cr_regs
    mov di,cr_values
    mov cx,cr_count
.cr:
    lodsb
    call cr_read
    mov [di],al
    inc di
    loop .cr
    mov al,[lock38]
    mov [cr_values+11],al
    mov al,[lock39]
    mov [cr_values+12],al
    mov dx,0x3C4
    in al,dx
    mov [sr_index],al
    mov al,8
    out dx,al
    inc dx
    in al,dx
    mov [lock08],al
    mov al,6
    out dx,al
    mov si,sr_regs
    mov di,sr_values
    mov cx,sr_count
.sr:
    mov dx,0x3C4
    lodsb
    out dx,al
    inc dx
    in al,dx
    mov [di],al
    inc di
    loop .sr
    mov dx,0x3C4
    mov al,8
    out dx,al
    inc dx
    mov al,[lock08]
    out dx,al
    mov [sr_values],al
    dec dx
    mov al,[sr_index]
    out dx,al
.restore_cr:
    mov ah,[lock39]
    mov al,0x39
    call cr_write
    mov ah,[lock38]
    mov al,0x38
    call cr_write
    mov dx,[cr_port]
    mov al,[cr_index]
    out dx,al
    popad
    popf
    cmp byte [identity_ok],1
    ret
cr_read:
    mov dx,[cr_port]
    out dx,al
    inc dx
    in al,dx
    ret
cr_write:
    mov dx,[cr_port]
    out dx,al
    inc dx
    mov al,ah
    out dx,al
    ret

print_snapshot:
    mov si,misc_title
    call puts
    mov al,[misc]
    call hex8
    mov si,newline
    call puts
    mov si,cr_title
    call puts
    mov bp,cr_regs
    mov di,cr_values
    mov cx,cr_count
    call print_registers
    mov si,sr_title
    call puts
    mov bp,sr_regs
    mov di,sr_values
    mov cx,sr_count
print_registers:
    xor bx,bx
.next:
    mov al,[bp]
    call hex8
    mov al,'='
    call character
    mov al,[di]
    call hex8
    mov al,' '
    call character
    inc bp
    inc di
    inc bx
    test bl,7
    jnz .continue
    mov si,newline
    call puts
.continue:
    loop .next
    mov si,newline
    call puts
    ret

rom_fingerprint:
    push es
    mov ax,0xC000
    mov es,ax
    cmp word [es:0],0xAA55
    jne .unknown
    movzx ecx,byte [es:2]
    test cx,cx
    jz .unknown
    cmp cx,128
    ja .unknown
    shl ecx,9
    mov eax,ecx
    call hex32
    mov al,' '
    call character
    xor si,si
    mov eax,0x811C9DC5
.hash:
    xor al,[es:si]
    imul eax,eax,0x01000193
    inc si
    dec ecx
    jnz .hash
    call hex32
    mov si,newline
    call puts
    pop es
    ret
.unknown:
    mov si,unknown
    call puts
    pop es
    ret
hex32:
    pushad
    mov cx,4
.byte:
    rol eax,8
    call hex8
    loop .byte
    popad
    ret
hex8:
    push ax
    shr al,4
    call hex_nibble
    pop ax
    push ax
    and al,15
    call hex_nibble
    pop ax
    ret
hex_nibble:
    push ax
    and al,15
    add al,'0'
    cmp al,'9'
    jbe .print
    add al,7
.print:
    call character
    pop ax
    ret
character:
    pushad
    mov bx,[used]
    mov [output+bx],al
    inc bx
    mov [used],bx
    cmp al,10
    je .flush
    cmp bx,128
    jb .done
.flush:
    call flush
.done:
    popad
    ret
puts:
    pushad
.next:
    lodsb
    test al,al
    jz .done
    call character
    jmp .next
.done:
    popad
    ret
flush:
    pushad
    mov cx,[used]
    jcxz .done
    mov word [used],0
    mov dx,output
    mov bx,1
    mov ah,0x40
    int 0x21
    jc output_error
    cmp ax,cx
    jne output_error
.done:
    popad
    ret
output_error:
    mov ax,0x4C01
    int 0x21

title db 'S3STATE 1 - Trio64 text and mode13 comparison',13,10,0
text_title db 'Text state',13,10,0
graphics_title db 'Mode13 capture; returning to text before printing',13,10,0
planar_title db 'DOOM planar capture; returning to text before printing',13,10,0
complete db 'S0 Complete. Text mode and register locks restored.',13,10,0
real_message db 'S2 Run in plain DOS without EMM386 or another protected manager.',13,10,0
pci_message db 'S2 PCI BIOS read unavailable.',13,10,0
card_message db 'S2 Active PCI Trio64 required; no timing controls changed.',13,10,0
text_message db 'S2 Start in text mode 3 or 7.',13,10,0
rom_title db 'Live ROM bytes / FNV1a32: ',0
misc_title db 'MISC=',0
cr_title db 'CR index=value',13,10,0
sr_title db 'SR index=value',13,10,0
unknown db 'unknown',13,10,0
newline db 13,10,0
cr_regs db 0x2D,0x2E,0x2F,0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37,0x38,0x39,0x3A,0x3B,0x3C
        db 0x40,0x41,0x42,0x43,0x50,0x51,0x52,0x53,0x54,0x55,0x58,0x59,0x5A,0x5D,0x5E,0x60
        db 0x65,0x66,0x67,0x68,0x69,0x6A,0x6B,0x6C
cr_count equ $-cr_regs
sr_regs db 0x08,0x09,0x0A,0x0B,0x0D,0x10,0x11,0x12,0x13,0x14,0x15,0x18
sr_count equ $-sr_regs
cr_values times cr_count db 0
sr_values times sr_count db 0
bdf dw 0
pci_identity times 5 db 0
cr_port dw 0
cr_index db 0
sr_index db 0
lock38 db 0
lock39 db 0
lock08 db 0
misc db 0
identity_ok db 0
old_mode db 0
planar db 0
used dw 0
output times 128 db 0
