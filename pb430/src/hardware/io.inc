; AL=index, AH=value. Preserve the other owners' registers.
acc_read:
    out CHIPSET_INDEX,al
    out 0xED,al
    in al,CHIPSET_DATA
    out 0xED,al
    ret
acc_write:
    push ax
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,ah
    out CHIPSET_DATA,al
    out 0xED,al
    pop ax
    ret
init_at_prerequisites:
    post_code 0xB0
    pb430_refresh_dma
    post_code 0xB1
    mov dx,FDC_DOR
    out dx,al
    mov al,0x0C
    out SYSTEM_PORT_B,al
    post_code 0xB9
    ret
