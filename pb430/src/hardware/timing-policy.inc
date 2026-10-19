; Presets fill the same draft fields that Manual edits; changing to Manual keeps them.
; SI=record. Normal keeps stock timing. Fast is the measured 33 MHz ACCPROF set.
chipset_profile_apply:
    push ax
    and byte [fs:si+18],0xF3 ; Retire the AT refresh burst override.
    and byte [fs:si+19],0xFE ; Standard AT refresh is required.
    and byte [fs:si+21],0x7F ; Posted writes are not supported by this port.
    cmp byte [fs:si+14],2
    je .done
    mov byte [fs:si+15],0x15
    mov byte [fs:si+16],0
    and byte [fs:si+18],0xF0
    and byte [fs:si+19],0xFC
    mov byte [fs:si+20],0
    mov byte [fs:si+7],0
    mov byte [fs:si+8],0
    mov byte [fs:si+9],0
    cmp byte [fs:si+14],1
    jne .done
    mov byte [fs:si+15],0
    or byte [fs:si+18],1
    mov byte [fs:si+20],0x20
    mov byte [fs:si+7],1
    mov byte [fs:si+8],1
.done:
    pop ax
    ret

; Keep the trial pending through RAM testing and the final summary.
chipset_timing_trial_begin:
    pushf
    cli
    push ax
    mov al,0x36
    call rtc_read
    and al,0xBF
    cmp al,0x1A ; Preserve the existing second-failure guard on a recovery POST.
    je .done
    mov ax,0xAB36
    call chipset_timing_trial_write
.done:
    pop ax
    popf
    ret

chipset_timing_trial_finish:
    pushf
    cli
    push ax
    mov al,0x36
    call rtc_read
    cmp al,0xAB
    jne .done
    mov ax,0x0036
    call chipset_timing_trial_write
.done:
    pop ax
    popf
    ret

chipset_timing_trial_write:
    call rtc_write
    mov al,0x36
    call rtc_read ; Ctrl+Alt+Del can arrive with a caller-owned FS.
    cmp al,ah
    je .done
    post_code_early 0xFB
    jmp hard_halt
.done:
    ret

; Only a fully verified Setup save permits a new trial after recovery.
chipset_timing_saved:
    push ax
    mov ax,0x0036
    call rtc_write
    mov ax,0x0036
    call settings_verify_byte
    pop ax
    jne .bad
    clc
    ret
.bad:
    stc
    ret

; Apply the same DRAM choices before uncached testing and after stock cache activation.
chipset_memory_policy:
    pushf
    cli
    pushad
    call chipset_refresh_policy
    call chipset_ras_policy
    call chipset_shadow_cache_policy
    cmp byte [fs:C_CHIP+1],1
    jne .skip
    cmp byte [fs:HW_CACHE_QUALIFIED],1
    jne .skip
    in al,0x78
    and al,7
    cmp al,5
    jne .skip
    ; The live reference table must be intact before applying any manual fields.
    mov al,4
    call acc_read
    and al,0xFE
    cmp al,0x14
    jne .skip
    mov al,0x0B
    call acc_read
    cmp al,0x15
    jne .skip
    mov al,0xB7
    out 0x70,al
    in al,0x84
    mov al,0xA7
    out 0x71,al
    mov al,0xB7 ; Select again for each access, like rtc_read/rtc_write.
    out 0x70,al
    in al,0x84
    in al,0x71
    cmp al,0xA7
    jne .failed
    post_code 0x76
    wbinvd
    ; Advance first, then refresh precharge, then shorten CAS last.
    mov al,[fs:C_CHIP+18]
    xor ah,ah
    test al,1
    jz .read_advance
    or ah,3
.read_advance:
    test al,2
    jz .write_advance
    or ah,0x0C
.write_advance:
.rom:
    test al,0x10
    jz .advance
    or ah,0x40
.advance:
    mov al,0x16
    mov dl,0x7F
    call chipset_masked_write
    post_code 0x79
    mov ax,0x0019
    mov ah,[fs:C_CHIP+20]
    mov dl,0xF7
    call chipset_masked_write
    mov al,0x12
    mov ah,[fs:C_CHIP+16]
    mov dl,0xC0
    call chipset_masked_write
    mov al,0x14
    mov ah,[fs:C_CHIP+17]
    mov dl,0x58
    call chipset_masked_write
    mov al,0x18
    mov ah,[fs:C_CHIP+19]
    and ah,0xFE
    test byte [fs:C_CHIP+21],8
    jnz .read_burst_ready
    and ah,0x7F
.read_burst_ready:
    mov dl,0xF3
    call chipset_masked_write
    mov al,4
    mov ah,[fs:C_CHIP+21]
    and ah,0x7F
    mov dl,0xF8
    call chipset_masked_write
    post_code 0x7A
    mov al,0x0B
    mov ah,[fs:C_CHIP+15]
    mov dl,0xFF
    call chipset_masked_write
    wbinvd
    test byte [fs:C_CHIP+22],0x0A
    jz .write_burst_done
    xor bx,bx
    test byte [fs:C_CHIP+22],2
    jz .save_refresh
    cmp byte [fs:HW_CACHE_ENABLED],1
    jne .save_refresh
    mov al,0x37
    call acc_read
    and al,3
    or al,4
    mov bl,al
.save_refresh:
    mov al,3
    call acc_read
    and al,0x40
    shr al,3
    or al,bl
    or al,0xB0
    mov ah,al
    pb430_trial_write 0x37,ah
    ; Save original register fields before either experiment touches hardware.
    test byte [fs:C_CHIP+22],8
    jz .cache_write
    mov ax,0x4003
    mov dl,0x40
    post_code 0x7E
    call chipset_masked_write
.cache_write:
    test bl,4
    jz .write_burst_done
    mov ah,[fs:C_CHIP+22]
    shr ah,2
    and ah,1
    mov al,0x37
    mov dl,3
    post_code 0x7D
    call chipset_masked_write
    wbinvd
.write_burst_done:
    post_code 0x77
    jmp .done
.skip:
    post_code 0x78
.done:
    popad
    popf
    ret
.failed:
    post_code_early 0xF0 ; Recovery marker could not be set.
    jmp hard_halt

chipset_ram_cache_finish:
    pushf
    cli
    pushad
    ; The stock transient sequence must see its original timing prerequisites.
    pb430_timing_restore
    call chipset_late_cache
    call BOARD_LATE_MEMORY_POLICY
    call chipset_isa_policy
    popad
    popf
    ret

; AL=index, AH=requested bits, DL=owned mask. Preserve unrelated and reserved bits.
chipset_masked_write:
    push bx
    mov bl,al
    call acc_read
    not dl
    and al,dl
    not dl
    and ah,dl
    or ah,al
    mov al,bl
    call acc_write
    mov al,bl
    call acc_read
    xor al,ah
    test al,dl
    jnz .failed
    pop bx
    ret
.failed:
    pb430_timing_restore
    post_code_early 0xEB
    jmp hard_halt

chipset_ras_policy:
    push ax
    mov ah,0x83 ; Readback adds reserved bits; use the stock programmed byte.
    cmp byte [fs:C_CHIP+9],0
    je .write
    mov ah,0x93
.write:
    post_code 0xD6
    mov al,1
    call acc_write
    mov al,1
    call acc_read
    and al,0xD3
    cmp al,ah
    jne .failed
    post_code 0xD7
    pop ax
    ret
.failed:
    mov ax,0x9301
    call acc_write
    post_code_early 0xD9
    jmp hard_halt

chipset_shadow_cache_policy:
    push ax
    push dx
    wbinvd
    mov ah,0x60
    cmp byte [fs:C_CHIP+13],0
    je .protect
    and ah,0xBF
.protect:
    test byte [fs:C_CHIP+22],1
    je .write
    and ah,0xDF
.write:
    mov al,2
    mov dl,0x60
    call chipset_masked_write
    wbinvd
    pop dx
    pop ax
    ret

chipset_refresh_policy:
    pushf
    cli
    push ax
    push bx
    movzx bx,byte [fs:C_CHIP+7]
    mov al,5
    call acc_read
    and al,0xFC
    or al,[cs:chipset_refresh_values+bx]
chipset_refresh_write:
    mov ah,al
    mov al,5
    call acc_write
    pop bx
    pop ax
    popf
    ret
chipset_refresh_values db 0,3,1,2

; Apply only after the reference cache sequence has returned to normal mode.
chipset_isa_policy:
    movzx bx,byte [fs:C_CHIP+22]
    shr bx,4
    and bx,7
    jz .done
    mov ah,[cs:chipset_isa_dividers+bx]
    mov al,6
    mov dl,0x1F
    call chipset_masked_write
.done:
    ret
chipset_isa_dividers db 0,0x10,0x15,0x11,0x12,0x17,0x13,0x14
