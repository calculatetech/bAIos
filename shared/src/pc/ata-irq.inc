; OEM F000:B343: DOS ATAPI drivers chain hard-disk IRQ14 here.
; A bare IRET leaves the slave PIC and cascade in service and blocks devices.
int76:
    push ax
    push ds
    mov ax, 0x0040
    mov ds, ax
    mov byte [0x008E], 0xFF
    mov al, 0x66               ; Specific slave IRQ6 (system IRQ14) EOI.
    out 0xA0, al
    mov al, 0x62               ; Specific master cascade EOI.
    out 0x20, al
    xor ax, ax
    mov ds, ax
    mov ax, 0x9100             ; OEM device-completion notification hook.
    int 0x15
    pop ds
    pop ax
    iret
