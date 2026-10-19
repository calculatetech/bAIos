; Presario two-position primary ATA owner; public disk services remain shared.
ata_identify:
ata_detect_primary:
    pushad
    push ds
    push fs
    xor ax, ax
    mov ds, ax
    call load_bios_state
    call ide_apply_controller
    mov si, C_IDE + 1
    mov di, S_IDE
    call ide_copy_record
    mov si, C_IDE + 1 + IDE_RECORD_SIZE
    mov di, 0x200 + S_IDE
    call ide_copy_record
    mov al, [fs:C_IDE]
    mov [fs:S_CONTROLLER], al
    mov [fs:0x200 + S_CONTROLLER], al
    test al, al
    jz .detect
    cmp byte [fs:C_HDD], 1
    je .reset_bus
    cmp byte [fs:C_SLAVE], 1
    jne .detect
.reset_bus:
    ; OEM F000:A1AE resets the channel before identifying either position.
    post_code 0x86
    call ata_reset_bus
.detect:
    mov byte [fs:S_ATA_DEVICE], 0
    call ata_identify_selected
    call post_ui_disk
    mov al, [fs:C_SLAVE]
    mov [fs:0x200 + C_HDD], al
    mov ax, fs
    add ax, 0x20
    mov fs, ax
    mov byte [fs:S_ATA_DEVICE], 0x10
    call ata_identify_selected
    call post_ui_disk
    call load_bios_state
    post_code 0x84
    call disk_refresh_vector
    call publish_disk_cmos
    ; Windows WDCTRL checks that primary IDE IRQ14 is unmasked before its
    ; geometry validation. Keep POST probing masked, then hand off the
    ; enabled controller with its standard AT interrupt and cascade armed.
    cmp byte [fs:S_CONTROLLER], 0
    je .irq_ready
    in al, 0xA1
    and al, 0xBF
    out 0xA1, al
    in al, 0x21
    and al, 0xFB
    out 0x21, al
.irq_ready:
    post_code 0x85
    pop fs
    pop ds
    popad
    call load_bios_state
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
    jb .other
    mov dx,fs
    cmp ax,dx
    je .first
    cmp byte [es:S_PRESENT],1
    jne .first
.other:
    stc
    jmp .done
.first:
    clc
.done:
    pop es
    pop dx
    pop ax
    ret
hardware_cd_select:
    ret
hardware_cd_packet_controller:
    xor al,al
    ret
post_device_label:
    mov si,u_post_master
    cmp byte [fs:S_ATA_DEVICE],0x10
    jne .done
    mov si,u_post_slave
.done:
    ret
