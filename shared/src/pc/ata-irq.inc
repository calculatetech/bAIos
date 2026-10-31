; OEM F000:B343: DOS ATAPI drivers chain hard-disk IRQ14 here.
; A bare IRET leaves the slave PIC and cascade in service and blocks devices.
int76:
    push ax
    mov al,0x66               ; Specific slave IRQ6 (system IRQ14) EOI.
    jmp ata_irq_complete
%if BOARD_ATA_DEVICE_COUNT = 4
int77:
    push ax
    mov al,0x67               ; Specific slave IRQ7 (system IRQ15) EOI.
%endif
ata_irq_complete:
    push ds
    push ax
    mov ax, 0x0040
    mov ds, ax
    mov byte [0x008E], 0xFF
    pop ax
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
