bits 16
org 0x7C00
    cli
    xor ax,ax
    mov ss,ax
    mov sp,0x7B00
    mov ds,ax
    mov es,ax
    sti
    cmp dl,0x80
    jne failed
    mov bx,0x8000
    mov ax,0x0201
    mov cx,2
    xor dh,dh
    int 0x13
    jc failed
    cmp dword [0x8000],0x41544144
    jne failed
    int 0x12
    cmp ax,632
    jne failed
    mov al,0xD1
    out 0x64,al
    xor cx,cx
.wait:
    in al,0x64
    test al,2
    loopne .wait
    jnz failed
%ifndef A20_OUTPUT
%define A20_OUTPUT 0xCD
%endif
    mov al,A20_OUTPUT
    out 0x60,al
%ifndef A20_BOARD_OUTPUT
%define A20_BOARD_OUTPUT 1
%endif
    mov al,0xE1
    out 0x5A,al
    mov al,A20_BOARD_OUTPUT
    out 0x5B,al
    mov ebx,0x87654321
    mov edi,0x13572468
    mov ebp,0x19283746
    mov edx,0x76540080
    mov esi,0x24680000
    mov si,descriptors
    mov cx,2
    mov ah,0x87
    int 0x15
    jc failed
    cmp ebx,0x87654321
    jne failed
    cmp edi,0x13572468
    jne failed
    cmp ebp,0x19283746
    jne failed
    cmp edx,0x76540080
    jne failed
    cmp esi,0x24680000+descriptors
    jne failed
    mov byte [source+4],0x12
    mov word [destination+2],0x8200
    mov byte [destination+4],0
    mov cx,2
    mov ah,0x87
    int 0x15
    jc failed
    cmp dword [0x8200],0x11223344
    jne failed
    mov al,0x5A
    out 0xE9,al
    cli
    hlt
failed:
    mov al,0xEE
    out 0xE9,al
    cli
    hlt
align 8
descriptors:
    times 16 db 0
source:
    dw 0xFFFF
    db 0,0,0x11,0x93,0,0
destination:
    dw 0xFFFF
    db 0,0,0x12,0x93,0,0
    times 16 db 0
times 510-($-$$) db 0
dw 0xAA55
