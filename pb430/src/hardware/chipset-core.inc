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

chipset_valid:
    pushad
    xor bx,bx
    cmp byte [fs:si+23],0xA3
    je .extended
.next:
    mov al,[fs:si+bx]
    cmp al,1
    ja .bad
    inc bx
    cmp bx,9
    jb .next
.reserved:
    cmp byte [fs:si+bx],0
    jne .bad
    inc bx
    cmp bx,CHIP_SIZE
    jb .reserved
    popad
    clc
    ret
.extended:
    mov al,[fs:si+bx]
    mov ah,[cs:chipset_allowed+bx]
    not ah
    test al,ah
    jnz .bad
    inc bx
    cmp bx,23
    jb .extended
    cmp byte [fs:si+14],2
    ja .bad
    mov al,[fs:si+18]
    and al,0x0C
    cmp al,0x0C
    je .bad
    popad
    clc
    ret
.bad:
    popad
    stc
    ret
chipset_settings_load:
    pushad
    call settings_recovery_read
    cmp al,0xD2
    je .safe
    call chipset_settings_load_raw
    call settings_recovery_read
    cmp al,0xD2
    jne .done
.safe:
    mov di,C_CHIP
    call chipset_defaults
    mov byte [fs:C_CHIP+2],0
.done:
    popad
    ret
; Read and validate saved policy even when recovery selects safe live timings.
; D2 replaced a legacy tag; the original tag is admitted only by its checksum.
chipset_settings_load_raw:
    pushad
    mov di,C_CHIP
    call chipset_defaults
    call settings_nv6_present
    jne .legacy
    call settings_nv6_chip_load
    jc .bad
    mov si,C_CHIP
    call chipset_valid
    jc .bad
    jmp .profile
.legacy:
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    jne .tag
    mov al,0xC2
.tag:
    cmp al,0xC2
    jne .done
    mov bl,al
    xor bp,bp
.byte:
    mov al,[cs:chipset_cmos+bp]
    call rtc_read
    mov [fs:C_CHIP+bp],al
    add bl,al
    inc bp
    cmp bp,CHIP_SIZE
    jb .byte
    mov al,0x6A
    call rtc_read
    add bl,al
    jnz .bad
    mov si,C_CHIP
    call chipset_valid
    jc .bad
    cmp byte [fs:C_CHIP+23],0xA3
    je .profile
    ; Old records used only the first nine bytes. Preserve those choices.
    mov bx,9
.upgrade:
    mov al,[cs:chipset_default+bx]
    mov [fs:C_CHIP+bx],al
    inc bx
    cmp bx,CHIP_SIZE
    jb .upgrade
    mov byte [fs:C_CHIP+14],2
    cmp byte [fs:C_CHIP+8],0
    je .profile
    mov byte [fs:C_CHIP+15],4
.profile:
    call chipset_profile_apply
    jmp .done
.bad:
    mov di,C_CHIP
    call chipset_defaults
    mov byte [fs:C_VALID],0
    jmp .done
.done:
    popad
    ret
chipset_settings_save:
    mov si,U_CHIP
    call chipset_profile_apply
    call chipset_valid
    jc settings_nv6_bad
    jmp settings_nv6_chip_save


chipset_apply:
    pushf
    cli
    pushad
    pb430_timing_restore
%ifdef PB430_CACHE_BURST_PROBE
    call chipset_burst_disable
%endif
    call load_bios_state
    ; L1 is already flushed and held off; preserve OEM warm1E state until L2 is off.
    post_code 0xD3
    mov al,4
    call acc_read
    and al,0xFE ; L2 stays disabled until the existing final Setup gate.
    mov ah,al
    mov al,4
    call acc_write
    mov byte [fs:HW_CACHE_ENABLED],0
    post_code 0xD4
    mov al,0x1A
    call acc_read
    and al,0x7F
    cmp byte [fs:C_CHIP],0
    je .ads
    cmp byte [fs:C_CHIP+5],0
    je .ads
    or al,0x80
.ads:
    mov ah,al
    mov al,0x1A
    call acc_write
    call shadow_system_policy
    cmp byte [fs:HW_VGA_REQUIRED],1
    je .cpu
    cmp byte [fs:C_CHIP+4],0
    je .video_off
    call shadow_external_video
    jmp .cpu
.video_off:
    mov al,2
    call acc_read
    and al,0xFE
    mov ah,al
    mov al,2
    call acc_write
.cpu:
    call shadow_additional_policy
    call chipset_cpu_policy
    pb_stage 0x52
    popad
    popf
    ret
%include "hardware/timing-policy.inc"
chipset_cpu_policy:
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    ; OEM8F3A..972B holds L1 off until the final cache owner.
    mov cr0,eax
    ret
chipset_cmos db 0x6B,0x6C,0x6D,0x6E,0x6F,0x70,0x71,0x72,0x73,0x74,0x75
    db 0x76,0x77,0x78,0x79,0x7A,0x7B,0x7C,0x7D,0x7E,0x7F,0x33,0x34,0x35
chipset_default db 0,DEFAULT_CACHE_ENABLED,DEFAULT_CACHE_ENABLED,1,1,0,0,0,0,0,0,0,0,0,0,0x15,0,0,0,0,0,0x10,0,0xA3
chipset_allowed db 1,1,1,1,1,1,1,3,1,1,1,1,1,1,3,0xFF,0xC0,0x58,0x1F,0xF3,0xF7,0xF8,0x7F
%include "setup/chipset-menu.inc"
%include "hardware/chipset-data.inc"
%include "firmware/ram-test.inc"
%ifdef PB430_CACHE_BURST_PROBE
%include "hardware/cache-burst.inc"
%endif
