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
    mov al, 0x69
    call rtc_read
    cmp al, 0xD2
    je .recovery
    cmp al,0x55
    je .record
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
    cmp dl,0x55
    jne .new_record
    ; Preserve the original three-field record before adding profile metadata.
    test byte [fs:C_CHIP],0x0F
    jnz .bad
    cmp byte [fs:C_CHIP+1],1
    ja .bad
    cmp byte [fs:C_CHIP+2],1
    ja .bad
    mov bx,3
.legacy_reserved:
    cmp byte [fs:C_CHIP+bx],0
    jne .bad
    inc bx
    cmp bx,CHIP_SIZE
    jb .legacy_reserved
    mov byte [fs:C_CHIP+7],1
    mov byte [fs:C_CHIP+8],0x80
.new_record:
    mov si, C_CHIP
    call chipset_valid
    jc .bad
    ; Hardware changes can remove Fast's benefit without corrupting the record.
    call chipset_profile_apply
    jmp .done
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
    mov bx,0
.compare:
    mov al,[fs:C_CHIP+bx]
    cmp al,[fs:U_CHIP+bx]
    jne .changed
    inc bx
    cmp bx,CHIP_OPTION_BYTES
    jb .compare
    jmp .save
.changed:
    mov si,U_CHIP
    call cache_validation_clear
.save:
    mov si,U_CHIP
    call chipset_record_save
    popad
    ret

; SI=active or draft record. Preserve verified publication and D2 on failure.
chipset_record_save:
    pushad
    xor dx,dx
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    jne .validate
    mov dl,0xD2
.validate:
    call chipset_valid
    jc .bad
    mov al,[fs:si+8]
    and al,0xC0
    cmp al,0xC0
    jne .publish
    call chipset_fast_available
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
    mov al,[fs:si+8]
    and al,0x30
    cmp al,0x30
    je .bad
    mov al,[fs:si+CHIP_CERT_OFFSET]
    test al,al
    jz .profile
    cmp al,CHIP_CERT_TAG
    jne .bad
.profile:
    mov al,[fs:si+8]
    and al,0xC0
    cmp al,0x80
    je .good
.tuple:
    call chipset_profile_tuple
    mov al,[cs:chipset_profiles+bx]
    cmp [fs:si],al
    jne .bad
    mov al,[fs:si+3]
    and al,0x30
    cmp al,[cs:chipset_profiles+bx+1]
    jne .bad
    mov al,[fs:si+5]
    and al,2
    cmp al,[cs:chipset_profiles+bx+2]
    jne .bad
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
    and cl,0xBF             ; AMI keeps the unprimed cache in WT before testing.
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_write
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    mov ecx,eax
    and ch,0x0E
    or ch,1
    or ch,[fs:C_CHIP]
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
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    je .ram_safe_failed
    mov di,C_CHIP
    call chipset_safe_defaults
    call chipset_apply
    mov ax,0xD269
    call rtc_write
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
    cmp byte [fs:HW_CACHE_CODE],0
    je .absent
    call cache_supported_extent
    jc .absent
    call cache_validation_identity
    call cache_validation_reuse
    jnc .policy
    post_code 0x24
    call post_l2_test_begin
    call cache_qualify
    test byte [fs:HW_CACHE_FLAGS],2
    jnz cache_recovery
    test byte [fs:HW_CACHE_FLAGS],1
    jz .policy
    call post_l2_test_passed
    call cache_validation_save
    jmp .policy
.absent:
    cmp byte [fs:C_CHIP+CHIP_CERT_OFFSET],0
    je .policy
    mov si,C_CHIP
    call cache_validation_clear
    call chipset_record_save
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
    je .policy
    and eax,0x9FFFFFFF
.policy:
    mov cr0,eax
    mov al,0x69
    call rtc_read
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
