%include "setup/chipset-fields.inc"
chipset_defaults:
    pushad
    mov si, chipset_default
    mov cx, CHIP_SIZE
.byte:
    mov al, [cs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    popad
    ret

chipset_settings_load:
    pushad
    mov di, C_CHIP
    call chipset_defaults
%if BOARD_ATA_DEVICE_COUNT = 4
    call settings_format
    cmp al,1
    je .packed
    test al,al
    jnz .bad
%endif
    mov al, 0x69
    call rtc_read
    cmp al, 0xD2
    je .recovery
    cmp al,CHIP_RECORD_TAG
    jne .done
.record:
    mov dl, al
    mov bl, al
    xor bp, bp
.byte:
    mov al, [cs:chipset_cmos+bp]
    call rtc_read
    mov [fs:C_CHIP+bp], al
    add bl, al
    inc bp
    cmp bp, CHIP_SIZE
    jb .byte
    mov al, 0x6A
    call rtc_read
    add bl, al
    jnz .bad
.validate:
    mov si, C_CHIP
    call chipset_valid
    jc .bad
    jmp .done
%if BOARD_ATA_DEVICE_COUNT = 4
.packed:
    call chipset_packed_load
    jnc .done
%endif
.bad:
    mov di, C_CHIP
    call chipset_defaults
    mov byte [fs:C_VALID], 0
    jmp .done
.recovery:
    mov di,C_CHIP
    call chipset_safe_defaults
.done:
    popad
    ret
chipset_settings_save:
    pushad
    mov si,U_CHIP
    call chipset_record_save
    popad
    ret

; SI=active or draft record. Preserve verified publication and D2 on failure.
chipset_record_save:
    pushad
%if BOARD_ATA_DEVICE_COUNT = 4
    call settings_format
    cmp al,1
    je .packed
    test al,al
    jnz .format_bad
%endif
    xor dx,dx
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    jne .validate
    mov dl,0xD2
.validate:
    mov bx,20                 ; Legacy marker bytes must remain zero.
.clear_reserved:
    mov byte [fs:si+bx],0
    inc bx
    cmp bx,CHIP_SIZE
    jb .clear_reserved
    call chipset_valid
    jc .bad
.publish:
    mov ax,0x0069
    mov ah,dl
    call rtc_write
    mov bl,CHIP_RECORD_TAG
    xor bp,bp
.byte:
    mov al,[cs:chipset_cmos+bp]
    mov ah,[fs:si+bp]
    add bl,ah
    call rtc_write
    inc bp
    cmp bp,CHIP_SIZE
    jb .byte
    neg bl
    mov al,0x6A
    mov ah,bl
    call rtc_write
    mov al,0x6A
    call settings_verify_byte
    jne .bad
    xor bp,bp
.verify:
    mov al,[cs:chipset_cmos+bp]
    mov ah,[fs:si+bp]
    call settings_verify_byte
    jne .bad
    inc bp
    cmp bp,CHIP_SIZE
    jb .verify
    mov ax,(CHIP_RECORD_TAG << 8) | 0x69
    call rtc_write
    mov ax,(CHIP_RECORD_TAG << 8) | 0x69
    call settings_verify_byte
    jne .bad
    popad
    clc
    ret
.bad:
    mov ax,0x0069
    mov ah,dl
    call rtc_write
    popad
    stc
    ret
%if BOARD_ATA_DEVICE_COUNT = 4
.packed:
    call chipset_packed_save
    popad
    ret
.format_bad:
    popad
    stc
    ret

; CMOS71..7F: tag/checksum plus13 bytes of mask-selected policy bits.
chipset_packed_load:
    pushad
    sub sp,28
    mov bp,sp
    mov al,0x71
    call rtc_read
    cmp al,0xD2
    je .recovery
    mov di,bp
    mov al,0x71
    mov cx,15
    call settings_record_read
    jc .bad
    cmp byte [ss:bp],CHIP_RECORD_TAG
    jne .bad
    lea di,[bp+2]
    mov si,C_CHIP
    mov bx,chipset_masks
    mov cx,CHIP_OPTION_BYTES
    call settings_unpack
    call chipset_valid
    jc .bad
    ; Repacking also rejects all nonzero reserved bits and padding bytes.
    lea di,[bp+15]
    mov cx,13
.zero:
    mov byte [ss:di],0
    inc di
    loop .zero
    lea di,[bp+15]
    mov cx,CHIP_OPTION_BYTES
    call settings_pack
    mov di,0
.padding:
    mov al,[ss:bp+di+2]
    cmp al,[ss:bp+di+15]
    jne .bad
    inc di
    cmp di,13
    jb .padding
    lea sp,[bp+28]
    popad
    clc
    ret
.recovery:
    mov di,C_CHIP
    call chipset_safe_defaults
    lea sp,[bp+28]
    popad
    clc
    ret
.bad:
    lea sp,[bp+28]
    popad
    stc
    ret

chipset_packed_save:
    pushad
    sub sp,15
    mov bp,sp
    mov bx,CHIP_OPTION_BYTES
    jmp .reserved_test
.reserved:
    mov byte [fs:si+bx],0
    inc bx
.reserved_test:
    cmp bx,CHIP_SIZE
    jb .reserved
    call chipset_valid
    jc .bad
    mov di,bp
    mov cx,15
.zero:
    mov byte [ss:di],0
    inc di
    loop .zero
    mov byte [ss:bp],CHIP_RECORD_TAG
    lea di,[bp+2]
    mov bx,chipset_masks
    mov cx,CHIP_OPTION_BYTES
    call settings_pack
    mov di,bp
    mov cx,15
    mov bx,1
    call settings_record_checksum
    mov al,0x71
    call rtc_read
    mov ah,0
    cmp al,0xD2
    jne .write
    mov ah,0xD2
.write:
    mov al,0x71
    call settings_record_write
    lea sp,[bp+15]
    popad
    ret
.bad:
    lea sp,[bp+15]
    popad
    stc
    ret
%endif

chipset_cmos db 0x6B,0x6C,0x6D,0x6E,0x6F,0x70,0x71,0x72,0x73,0x74,0x75
    db 0x76,0x77,0x78,0x79,0x7A,0x7B,0x7C,0x7D,0x7E,0x7F,0x33,0x34,0x35

%include "setup/chipset-menu.inc"
%include "hardware/chipset-data.inc"
%include "firmware/ram-test.inc"

chipset_valid:
    pushad
    xor bx,bx
.byte:
    mov al,[fs:si+bx]
    mov ah,[cs:chipset_masks+bx]
    not ah
    test al,ah
    jnz .bad
    inc bx
    cmp bx,CHIP_OPTION_BYTES
    jb .byte
    mov al,[fs:si+7]
    and al,6
    cmp al,6
    je .bad
    mov al,[fs:si+7]
    and al,0x18
    cmp al,0x18
    je .bad
    mov al,[fs:si+8]
    mov cx,4
.ternary:
    mov dl,al
    and dl,3
    cmp dl,3
    je .bad
    shr al,2
    loop .ternary
    mov al,[fs:si+11]
    and al,3
    cmp al,3
    je .bad
    mov al,[fs:si+11]
    and al,0x1C
    cmp al,0x10
    ja .bad
    ; Decode each preserved low plane plus its appended high bit.
    mov al,[fs:si+20]
    mov ah,[fs:si+23]
    mov cx,4
.pio:
    test ah,1
    jz .pio_next
    mov dl,al
    and dl,3
    cmp dl,1
    ja .bad
.pio_next:
    shr al,2
    shr ah,1
    loop .pio
    mov bx,16
.irq_byte:
    mov al,[fs:si+bx]
    mov ah,al
    and al,15
    cmp al,11
    ja .bad
    shr ah,4
    cmp ah,11
    ja .bad
    inc bx
    cmp bx,18
    jb .irq_byte
.good:
    popad
    clc
    ret
.bad:
    popad
    stc
    ret
chipset_apply:
    pushf
    cli
    pushad
    call load_bios_state
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    mov ecx,eax
    mov cl,[fs:HW_CACHE_MAP]
    and cl,0x0F
    or cl,[fs:C_CHIP+3]
    and cl,0x3F             ; Apply timing with L2 disabled and WT selected.
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_write
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    mov ecx,eax
    and ch,0x0E
    or ch,1
    or ch,[fs:C_CHIP]
    mov al,ch
    call chipset_l1_protocol
    mov ch,al
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_write
    call chipset_apply_timing
    mov eax,cr0
    cmp byte [fs:C_CHIP+1],0
    je .l1_policy
    and eax,0x9FFFFFFF
.l1_policy:
    mov cr0,eax
    popad
    popf
    ret
chipset_post_ram_cache:
    pushf
    cli
    pushad
    call load_bios_state
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    test byte [fs:P_RAM_FLAGS],4
    jnz .cache
    call chipset_runtime_ram_check
    jnc .cache
    call post_error_tone
    call post_message_cursor
    call settings_recovery_read
    cmp al,0xD2
    je .ram_safe_failed
    mov di,C_CHIP
    call chipset_safe_defaults
    call chipset_apply
    call settings_recovery_publish
    mov ax,0x5A36
    call rtc_write
    mov si,chipset_ram_before_cache
    call print_string
    call chipset_recovery_ack
    jmp controlled_defaults_restart
.ram_safe_failed:
    mov si,chipset_ram_safe_failure
    call print_string
    post_code_early 0xE7
    jmp hard_halt
.cache:
    call chipset_parity_apply
    cmp byte [fs:C_CHIP+2],0
    jne .policy
    post_code 0x24
    call cache_qualify
    test byte [fs:HW_CACHE_FLAGS],2
    jnz cache_recovery
.policy:
    mov eax,cr0
    cmp byte [fs:C_CHIP+1],0
    je .l1
    and eax,0x9FFFFFFF
.l1:
    mov cr0,eax
    popad
    popf
    ret

chipset_late_cache:
    pushf
    cli
    pushad
    call load_bios_state
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    call cache_enable
    mov eax,cr0
    cmp byte [fs:C_CHIP+1],0
    jne .l1_enabled
    wbinvd
    or eax,0x60000000
    jmp .policy
.l1_enabled:
    and eax,0x9FFFFFFF
.policy:
    mov cr0,eax
    call board_rom_tuning
    call board_pci_runtime_policy
    call settings_recovery_read
    cmp al,0xD2
    je .done
    mov ax,0x0036
    call rtc_write
.done:
    popad
    popf
    ret

chipset_ram_before_cache db 13,10,'RAM check before L2 enable failed. Safe settings loaded; restarting.',13,10,0
chipset_ram_safe_failure db 13,10,'RAM check failed with safe settings and L2 off. Check memory configuration.',13,10,0

%include "hardware/timing.inc"
%include "hardware/rom-tuning.inc"
