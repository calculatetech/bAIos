%include "pc/primary-ata.inc"

; BX=physical position, ES=root, FS=its runtime record. No task-file access.
hardware_ata_position:
    pushad
    mov [fs:HW_POSITION],bl
    mov si,umc_primary_ports
    test bl,2
    jz .table
    mov si,umc_secondary_ports
.table:
    mov di,HW_PORT_TABLE
    mov cx,9
.port:
    mov ax,[cs:si]
    mov [fs:di],ax
    add si,2
    add di,2
    loop .port
    mov al,bl
    and al,1
    shl al,4
    mov [fs:S_ATA_DEVICE],al
    mov byte [fs:S_CONTROLLER],0
    cmp byte [es:C_IDE],0
    je .done
    cmp word [es:HW_IDE_BDF],0xFFFF
    je .done
    cmp byte [es:HW_IDE_USABLE],1
    jne .done
    mov byte [fs:S_CONTROLLER],1
.done:
    popad
    ret

hardware_cd_select:
    pushad
    mov al,[fs:bx+HW_POSITION]
    mov [fs:HW_CD_POSITION],al
    mov si,bx
    add si,HW_PORT_TABLE
    mov di,HW_CD_PORT_TABLE
    mov cx,9
.port:
    mov ax,[fs:si]
    mov [fs:di],ax
    add si,2
    add di,2
    loop .port
    popad
    ret

hardware_cd_packet_controller:
    mov al,[fs:HW_CD_POSITION]
    shr al,1
    ret

hardware_ata_channel:
    mov al,[fs:HW_POSITION]
    shr al,1
    ret

; The BF supports the complete PIO recipe across its silicon revisions.
hardware_ata_pio_host:
    call load_bios_state
    cmp byte [fs:HW_IDE_USABLE],1
    jne .bad
    cmp byte [fs:C_IDE],1
    jne .bad
    movzx ebp,word [fs:HW_IDE_BDF]
    mov ax,bp
    and al,7
    cmp al,1
    jne .bad
    shl ebp,8
    or ebp,0x80000000
    mov eax,ebp
    call pci_read
    cmp eax,0x673A1060
    jne .bad
    clc
    ret
.bad:
    stc
    ret

hardware_ata_pio_allowed:
    pushad
    push fs
    call hardware_ata_pio_host
    pop fs
    popad
    ret

hardware_ata_pio_apply:
    push bx
    mov bl,[fs:HW_POSITION]
    call hardware_ata_pio_position
    pop bx
    ret

hardware_ata_pio_reset:
    pushad
    mov bl,[fs:HW_POSITION]
    and bl,2
    xor al,al
    call hardware_ata_pio_position
    inc bl
    xor al,al
    call hardware_ata_pio_position
    popad
    ret

; AL=mode, BL=physical position. All seven fields preserve peer bits.
hardware_ata_pio_position:
    pushf
    cli
    pushad
    push fs
    movzx si,al
    imul si,3
    add si,hardware_ata_pio_values
    movzx di,bl
    call hardware_ata_pio_host
    jc .done
    mov cx,di
    xor cl,3
    shl cl,1
    mov bl,3
    shl bl,cl
    mov bh,[cs:si]
    shl bh,cl
    push di
    mov di,0x43
    call hardware_ata_pio_field
    pop di
    mov cx,di
    and cl,1
    xor cl,1
    shl cl,2
    shr di,1
    add di,0x44
    mov bl,15
    shl bl,cl
    mov bh,[cs:si+1]
    shl bh,cl
    push cx
    mov cx,3
.b:
    call hardware_ata_pio_field
    add di,4
    loop .b
    sub di,10
    pop cx
    mov bh,[cs:si+2]
    shl bh,cl
    mov cx,3
.c:
    call hardware_ata_pio_field
    add di,4
    loop .c
.done:
    pop fs
    popad
    popf
    ret

hardware_ata_pio_field:
    mov eax,ebp
    or ax,di
    and al,0xFC
    mov dx,0xCF8
    out dx,eax
    mov dx,di
    and dx,3
    add dx,0xCFC
    in al,dx
    mov ah,bl
    not ah
    and al,ah
    or al,bh
    out dx,al
    ret
hardware_ata_pio_values db 3,6,0xB, 2,5,8, 1,4,5, 0,3,2, 0,3,0

post_device_label:
    push bx
    movzx bx,byte [fs:HW_POSITION]
    and bx,3
    shl bx,1
    mov si,[cs:umc_device_labels+bx]
    pop bx
    ret
umc_device_labels dw u_post_master,u_post_slave,u_umc_secondary_master,u_umc_secondary_slave
u_umc_secondary_master db 'Secondary Master',0
u_umc_secondary_slave db 'Secondary Slave',0
umc_primary_ports dw 0x1F0,0x1F1,0x1F2,0x1F3,0x1F4,0x1F5,0x1F6,0x1F7,0x3F6
umc_secondary_ports dw 0x170,0x171,0x172,0x173,0x174,0x175,0x176,0x177,0x376
