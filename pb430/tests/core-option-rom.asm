bits 16
org 0
db 0x55,0xAA,4
jmp short initialize
db 0
initialize:
    xor ax,ax
    mov ds,ax
    mov eax,[0x40]
    mov [0xB40],eax
    mov word [0x40],dirty_video
    mov ax,cs
    mov [0x42],ax
    mov byte [0xB48],0
    ; Returning option ROM deliberately moves its return frame and poisons DF.
    pop ax
    pop dx
    cli
    mov bx,0x7000
    mov ss,bx
    mov sp,0xFFF0
    push dx
    push ax
    mov ax,0xFFFF
    mov ds,ax
    mov es,ax
    mov fs,ax
    mov gs,ax
    std
    retf
dirty_video:
    push bp
    mov bp,sp
    push ax
    push ds
    xor ax,ax
    mov ds,ax
    mov ax,[ss:bp-2]
    pushf
    call far [0xB40]
    pop ds
    pop ax
    cmp ax,0x0500
    jne .done
    pushad
    push ds
    push es
    xor ax,ax
    mov ds,ax
    mov eax,[0xB40]
    mov [0x40],eax
    mov byte [0xB48],1
    mov ax,0xB800
    mov es,ax
    xor di,di
    mov ax,0x4E58
    mov cx,2000
    cld
    rep stosw
    pop es
    pop ds
    popad
    mov ax,0xFFFF
    mov fs,ax
    mov gs,ax
    or word [ss:bp+6],0x400
.done:
    pop bp
    iret
times 2047-($-$$) db 0
db 0
