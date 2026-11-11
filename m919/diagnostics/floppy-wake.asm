; Read-only media recovery comparison after IDLECHK. Plain DOS, M919 only.
bits 16
org 0x100
%ifndef SIO_INDEX
%error "Pass the board Super I/O index port"
%endif
start:
    push cs
    pop ds
    push cs
    pop ss
    mov sp,stack_top
    smsw ax
    test al,1
    jnz unsupported
    mov ax,0xE000
    mov es,ax
    cmp dword [es:0x14],0x53494142
    jne unsupported
    cmp dword [es:0x18],0x00314D4D
    jne unsupported
    pushf
    cli
    mov dx,0xCF8
    in eax,dx
    mov esi,eax
    mov eax,0x80008000
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    cmp eax,0x88811060
    jne .wrong
    mov dx,0xCF8
    mov eax,0x80009000
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    cmp eax,0x886A1060
    je .valid
    cmp eax,0x888A1060
    jne .wrong
.valid:
    mov bl,1
    jmp .restore
.wrong:
    xor bl,bl
.restore:
    mov eax,esi
    mov dx,0xCF8
    out dx,eax
    popf
    test bl,bl
    jz unsupported
    ; A physical 512-byte boundary cannot cross the ISA DMA 64-KiB boundary.
    xor eax,eax
    mov ax,cs
    shl eax,4
    add eax,buffer+511
    and eax,0xFFFFFE00
    shr eax,4
    mov [buffer_segment],ax
    call read_sector
    jnc done
    mov byte [code],'1'
    call reset_read
    jnc done
    ; Existing M919 floppy_controller_mode, excluding PS/2 and other devices.
    pushf
    cli
    mov dx,SIO_INDEX
    mov al,0xAA
    out dx,al
    mov al,0xC2
    out dx,al
    inc dx
    in al,dx
    and al,0xDF
    or al,0x81
    out dx,al
    dec dx
    mov al,0x55
    out dx,al
    popf
    mov byte [code],'2'
    call reset_read
    jnc done
    ; Existing AT cascade setup; leave unrelated DMA channels untouched.
    pushf
    cli
    mov al,4
    out 0xD4,al
    mov al,0xC0
    out 0xD6,al
    xor al,al
    out 0xD2,al
    out 0xD4,al
    popf
    mov byte [code],'3'
    call reset_read
    jnc done
    mov byte [code],'4'
    jmp done
unsupported:
    mov byte [code],'X'
done:
    mov dx,message
    mov ah,9
    int 0x21
    mov ax,0x4C00
    int 0x21
reset_read:
    xor ax,ax
    xor dx,dx
    int 0x13
read_sector:
    mov es,[buffer_segment]
    xor bx,bx
    mov ax,0x0201
    mov cx,1
    xor dx,dx
    int 0x13
    ret
message: db 'F'
code: db '0',13,10,'$'
buffer_segment: dw 0
buffer: times 1024 db 0
times 512 db 0
stack_top:
