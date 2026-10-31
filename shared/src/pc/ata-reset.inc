; Restore each ATA/packet peer after a channel reset before later data commands.
ata_reset:
    push bx
    push cx
    push dx
    push di
    push fs
    ata_port ATA_CONTROL
    mov di,dx
    call ata_reset_bus
    call load_bios_state
    mov cx,BOARD_ATA_DEVICE_COUNT
.position:
    ata_port ATA_CONTROL
    cmp dx,di
    jne .next
    mov byte [fs:S_MULTIPLE],0
%ifdef BOARD_ATA_PIO_MAX
    mov byte [fs:S_PIO_MODE],0
    mov al,[fs:S_PRESENT]
    or al,[fs:S_ATAPI]
    jz .next
    push cx
    call ide_pio_restore
    jc .geometry_error
    pop cx
%endif
    cmp byte [fs:S_PRESENT],1
    jne .next
    push cx
    call ide_initialize_geometry
    jc .geometry_error
    call ide_negotiate_multiple
    pop cx
.next:
    mov ax,fs
    add ax,0x20
    mov fs,ax
    loop .position
    pop fs
    call ata_select_ready
.done:
    pop di
    pop dx
    pop cx
    pop bx
    ret
.geometry_error:
    pop cx
    mov bl,[fs:S_STATUS]
    pop fs
    mov [fs:S_STATUS],bl
    stc
    jmp .done


ata_reset_bus:
%ifdef BOARD_ATA_PIO_MAX
    call ide_pio_reset
%endif
    push cx
    push dx
    ata_port ATA_CONTROL
    mov al, 4
    out dx, al
    mov cx, 16
.hold_srst:
    call ata_delay
    loop .hold_srst
    xor al, al
    out dx, al
    mov cx, 5000
.settle:
    call ata_delay
    loop .settle
    pop dx
    pop cx
    ret

