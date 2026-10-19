bits 16
org 0
db 0x55,0xAA,4
jmp initialize
initialize:
    xor ax,ax
    mov ds,ax
    inc word [0x620]
    mov word [0x64],entry
    mov word [0x66],cs
    retf
entry:
    xor ax,ax
    mov ds,ax
    inc word [0x622]
%ifdef PROVIDER_INT18
    mov ax,0x2222
    mov ds,ax
    mov es,ax
    mov fs,ax
    mov ss,ax
    mov esp,0x400
    std
    cli
    int 0x18
    hlt
%else
    retf 2 ; Pop the synthetic interrupt FLAGS from boot_candidate's PUSHF.
%endif
times 2047-($-$$) db 0
db 0
