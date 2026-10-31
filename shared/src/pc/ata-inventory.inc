; Each physical connector owns its fixed saved policy, even when absent.
ata_identify:
ata_detect_primary:
    pushf
    pushad
    push ds
    push es
    push fs
    cld
    call load_bios_state
%ifdef BOARD_ATA_PIO_MAX
    mov byte [fs:S_PIO_BLOCKED],0
%endif
    call ide_apply_controller
    mov ax,fs
    mov es,ax
    xor bx,bx
.position:
    mov ax,bx
    shl ax,5
    mov dx,es
    add ax,dx
    mov fs,ax
    mov [fs:S_POLICY_INDEX],bl
    call hardware_ata_position
    call ata_inventory_policy
    cmp byte [fs:S_CONTROLLER],1
    jne .identify
    test bl,1
    jnz .identify
    call ata_reset_bus
.identify:
    push bx
    call ata_identify_selected
    pop bx
.next:
    inc bx
    cmp bx,BOARD_ATA_DEVICE_COUNT
    jb .position
    xor bx,bx
.complete:
    mov ax,bx
    shl ax,5
    mov dx,es
    add ax,dx
    mov fs,ax
    call post_ui_disk
    inc bx
    cmp bx,BOARD_ATA_DEVICE_COUNT
    jb .complete
    call load_bios_state
    post_code 0x84
    call disk_refresh_vector
    call publish_disk_cmos
    cmp byte [fs:S_CONTROLLER],0
    je .done
    in al,0xA1
    and al,0x3F
    out 0xA1,al
    in al,0x21
    and al,0xFB
    out 0x21,al
.done:
    post_code 0x85
    pop fs
    pop es
    pop ds
    popad
    popf
    call load_bios_state
    ret

; ES=root, FS=physical record, BX=physical position. Preserve iteration state.
ata_inventory_policy:
    pushad
    mov si,bx
    imul si,IDE_RECORD_SIZE
    add si,C_IDE+1
    mov di,S_IDE
    mov cx,IDE_RECORD_SIZE
.byte:
    mov al,[es:si]
    mov [fs:di],al
    inc si
    inc di
    loop .byte
    mov al,[es:C_HDD]
    test bx,bx
    jz .enable
    mov al,[es:C_SLAVE]
    cmp bx,1
    je .enable
    mov si,bx
    mov al,[es:C_IDE+IDE_ENABLE_EXTRA-2+si]
.enable:
    mov [fs:S_ENABLED],al
%ifdef BOARD_IDE_32BIT_POLICY
    mov al,[es:BOARD_IDE_32BIT_POLICY]
    mov cx,bx
    shr al,cl
    and al,1
    mov [fs:S_PIO32],al
%endif
%ifdef BOARD_ATA_PIO_POLICY
    mov al,[es:BOARD_ATA_PIO_POLICY]
    mov cx,bx
    shl cl,1
    shr al,cl
    and al,3
    shr cl,1
    mov ah,[es:BOARD_ATA_PIO_POLICY_HIGH]
    shr ah,cl
    and ah,1
    shl ah,2
    or al,ah
    mov [fs:S_PIO_REQUEST],al
%elifdef BOARD_ATA_PIO_MAX
    mov byte [fs:S_PIO_REQUEST],0
%endif
    popad
    ret

hardware_bpb_owner:
    jmp ata_bpb_owner
