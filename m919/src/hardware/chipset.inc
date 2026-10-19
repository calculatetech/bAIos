; Startup values from AMI observations and the UMC manual, not executable code.
; Keep timings conservative, ROM external and both external-cache gates off.
; BL offset, BH value. No stack or RAM state; preserve the probe registers.
%macro early_chipset_write 1
    mov eax,0x80000000 | (%1 << 11)
    movzx ecx,bl
    and cl,0xFC
    or eax,ecx
    mov dx,0xCF8
    out dx,eax
    movzx dx,bl
    and dx,3
    add dx,0xCFC
    mov al,bh
    out dx,al
%endmacro

chipset_initialize:
    mov si,host_table
.host:
    cs lodsb
    cmp al,0xFF
    je .south
    mov bl,al
    cs lodsb
    mov bh,al
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    jmp .host
.south:
    mov si,isa_table
.isa:
    cs lodsb
    cmp al,0xFF
    je .done
    mov bl,al
    cs lodsb
    mov bh,al
    early_chipset_write CFG_PLATFORM_ISA_PCI_DEVICE
    jmp .isa
.done:
    mov al,0x54
    out 0x43,al
    mov al,0x12
    out 0x41,al
    in al,0x92
    and al,0xFE
    or al,2
    out 0x92,al
    mov al,0x20
    out POST_PORT,al
    jmp flat_addressing

host_write:
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    jmp chipset_byte_write
isa_write:
    mov eax,0x80000000 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11)
chipset_byte_write:
    movzx ecx,bl
    and cl,0xFC
    or eax,ecx
    mov dx,0xCF8
    out dx,eax
    movzx dx,bl
    and dx,3
    add dx,0xCFC
    mov al,bh
    out dx,al
    ret

host_table:
    db 0x50,0x00,0x51,0x00,0x52,0x01,0x53,0x00
    db 0x54,0x00,0x55,0x40,0x56,0xFF,0x57,0x0F
    db 0x58,0xFF,0x59,0x0F,0x5A,0x00,0x5B,0x00
    db 0x5C,0x00,0x5D,0x20,0x5E,0x00,0x5F,0xFF
    db 0x60,0x00,0x61,0x02,0xFF
isa_table:
    db 0x40,0x01,0x41,0x40,0x42,0x08,0x43,0x9A
    db 0x44,0xBC,0x45,0x04,0x46,0x1F,0x47,0x4F
    db 0x50,0x00,0x51,0x02,0x56,0x00,0x57,0x24
    db 0x70,0x0F,0x71,0x00,0x76,0x00,0xA0,0x00,0xA4,0x01,0xFF
