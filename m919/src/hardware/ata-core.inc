; Scan every physical position. Keep the donor's two logical records and API.
; Only ATA-owned fields move; common floppy, mouse, policy and CPU state do not.
ata_identify:
ata_detect_primary:
    pushf
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    call ide_apply_controller
    sub sp,4
    mov bp,sp
    mov word [ss:bp],0         ; Next physical position.
    mov word [ss:bp+2],0       ; Next donor logical record.
    cmp byte [fs:C_IDE],0
    je .done
    cmp word [fs:HW_IDE_BDF],0xFFFF
    je .done
    cmp byte [fs:HW_IDE_USABLE],1
    jne .done
.position:
    mov ax,STATE_SEG+0x40
    mov fs,ax
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,0x100
    rep stosw
    mov bx,[ss:bp]
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
    mov [es:di],ax
    add si,2
    add di,2
    loop .port
    mov al,bl
    and al,1
    shl al,4
    mov [fs:S_ATA_DEVICE],al
    mov byte [fs:S_CONTROLLER],1
    mov byte [fs:C_HDD],1
    mov ax,STATE_SEG
    mov es,ax
    mov si,C_IDE+1
    cmp word [ss:bp+2],0
    je .policy
    add si,IDE_RECORD_SIZE
.policy:
    mov di,S_IDE
    mov cx,IDE_RECORD_SIZE
.byte:
    mov al,[es:si]
    mov [fs:di],al
    inc si
    inc di
    loop .byte
    test byte [fs:HW_POSITION],1
    jnz .identify
    push bp
    call ata_reset_bus
    pop bp
.identify:
    push bp
    call ata_identify_selected
    pop bp
    cmp byte [fs:S_PRESENT],1
    je .detected
    cmp byte [fs:S_ATAPI],1
    jne .next
.detected:
    cmp word [ss:bp+2],2
    jae .next                 ; The donor currently exposes two logical devices.
    mov ax,STATE_SEG
    mov es,ax
    mov al,[es:BOARD_IDE_32BIT_POLICY]
    mov cx,[ss:bp+2]
    shr al,cl
    and al,1
    mov [fs:S_PIO32],al
    mov ax,[ss:bp+2]
    shl ax,5
    add ax,STATE_SEG
    mov es,ax
    mov si,S_PRESENT
    mov di,S_PRESENT
    mov cx,S_WARM_BOOT-S_PRESENT
    call .copy
    mov si,S_FDPT
    mov di,S_FDPT
    mov cx,S_SETUP_REQUEST-S_FDPT
    call .copy
    mov si,S_PACKET_BYTES
    mov di,S_PACKET_BYTES
    mov cx,C_TYPES-S_PACKET_BYTES
    call .copy
    mov si,S_IDE
    mov di,S_IDE
    mov cx,C_PORTS-S_IDE
    call .copy
    mov si,HW_PORT_TABLE
    mov di,HW_PORT_TABLE
    mov cx,HW_POSITION+1-HW_PORT_TABLE
    call .copy
    push fs
    call load_bios_state
    mov al,[fs:C_HDD]
    cmp word [ss:bp+2],0
    je .enabled
    mov al,[fs:C_SLAVE]
.enabled:
    pop fs
    mov [es:C_HDD],al
    test al,al
    jnz .announce
    mov byte [es:S_PRESENT],0
    mov byte [es:S_ATAPI],0
.announce:
    push fs
    push es
    pop fs
    push bp
    call post_ui_disk
    pop bp
    pop fs
    inc word [ss:bp+2]
.next:
    inc word [ss:bp]
    cmp word [ss:bp],4
    jb .position
.done:
    add sp,4
    call load_bios_state
    call disk_refresh_vector
    call publish_disk_cmos
    in al,0xA1
    and al,0x3F               ; Primary IRQ14 and secondary IRQ15.
    out 0xA1,al
    in al,0x21
    and al,0xFB
    out 0x21,al
    pop fs
    pop es
    pop ds
    popad
    popf
    call load_bios_state
    ret
.copy:
    mov al,[fs:si]
    mov [es:di],al
    inc si
    inc di
    loop .copy
    ret

hardware_bpb_owner:
    push ax
    push dx
    push es
    xor ax,ax
    mov es,ax
    mov ax,[es:0x40E]
    mov es,ax
    cmp byte [es:B_DRIVE],0x80
    jb .other_boot
    mov dx,fs
    cmp ax,dx
    je .first
    cmp byte [es:S_PRESENT],1
    jne .first
    stc
    jmp .done
.other_boot:
    stc                      ; A floppy BPB does not describe an ATA disk.
    jmp .done
.first:
    clc
.done:
    pop es
    pop dx
    pop ax
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
int77:
    push ax
    push ds
    mov ax,0x40
    mov ds,ax
    mov byte [0x8E],0xFF
    mov al,0x67               ; Specific secondary IDE IRQ15 EOI.
    out 0xA0,al
    mov al,0x62
    out 0x20,al
    xor ax,ax
    mov ds,ax
    mov ax,0x9100
    int 0x15
    pop ds
    pop ax
    iret
