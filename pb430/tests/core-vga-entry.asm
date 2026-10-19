; Wrapper in checked zero padding of a disposable retained VGA ROM copy.
; Its original entry initializes the real provider before poisoning return.
bits 16
org 0xE4
%include "vga-entry.inc"
    call 0xC000:ORIGINAL_VGA_ENTRY
    xor ax,ax
    mov ds,ax
    mov byte [0xB49],1
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
