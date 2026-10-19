; DOS readback. Restore the sequencer index and extension-lock state.
bits 16
org 0x100
    push cs
    pop ds
    push cs
    pop es
    cld
    pushf
    cli
    mov dx,0x3c4
    in al,dx
    mov [saved_index],al
    mov al,6
    out dx,al
    inc dx
    in al,dx
    mov [saved_lock],al
    dec dx
    mov ax,0x1206
    out dx,ax
    mov si,indices
    mov di,values
    mov cx,5
.read:
    lodsb
    out dx,al
    inc dx
    in al,dx
    stosb
    dec dx
    loop .read
    mov ah,[saved_lock]
    mov al,6
    out dx,ax
    mov al,[saved_index]
    out dx,al
    popf

    mov si,values
    mov bp,fields
    mov cx,5
.format:
    lodsb
    mov di,[ds:bp]
    add bp,2
    mov ah,al
    shr al,4
    mov bx,hex
    xlat
    stosb
    mov al,ah
    and al,15
    xlat
    stosb
    loop .format
    mov dx,report
    mov ah,9
    int 0x21
    mov al,[values+2]
    shr al,3
    and ax,7
    shl ax,1
    mov bx,ax
    mov dx,[bus_names+bx]
    mov ah,9
    int 0x21
    mov ax,0x4c00
    int 0x21
saved_index: db 0
saved_lock: db 0
indices: db 0x0f,0x16,0x17,0x1f,0x07
values: times 5 db 0
hex: db '0123456789ABCDEF'
fields: dw text_f,text_16,text_17,text_1f,text_7
report: db 'GD5428 register readback',13,10,'SR0F='
text_f: db '00',13,10,'SR16='
text_16: db '00',13,10,'SR17='
text_17: db '00',13,10,'SR1F='
text_1f: db '00',13,10,'SR07='
text_7: db '00',13,10,'Bus strap: $'
bus_names: dw reserved,dx_bus,sx_bus,reserved,vl_high,mca_bus,vl_low,isa_bus
reserved: db 'Reserved',13,10,'$'
dx_bus: db '386DX local bus',13,10,'$'
sx_bus: db '386SX local bus',13,10,'$'
vl_high: db 'VLB above 33 MHz',13,10,'$'
mca_bus: db 'MicroChannel',13,10,'$'
vl_low: db 'VLB at or below 33 MHz',13,10,'$'
isa_bus: db 'ISA',13,10,'$'
