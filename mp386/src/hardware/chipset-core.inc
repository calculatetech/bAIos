%include "setup/chipset-fields.inc"

; bAIos owns NVRAM0229..023F. OEM memory records0240..02FF remain untouched.
chipset_defaults:
    pushad
    mov si,mp_chip_default
    mov cx,CHIP_SIZE
.copy:
    mov al,[cs:si]
    mov [fs:di],al
    inc si
    inc di
    loop .copy
    sub di,CHIP_SIZE
    ; Match the OEM clock straps, including the alternate low-clock setting.
    in al,0x49
    mov ah,6
    test al,1
    jz .divisor
    inc ah
.divisor:
    mov [fs:di+3],ah
    test al,6
    jnz .done
    mov byte [fs:di+2],0x80
.done:
    popad
    ret

chipset_valid:
    pushad
    xor bx,bx
.byte:
    mov al,[cs:mp_chip_allowed+bx]
    not al
    test [fs:si+bx],al
    jnz .bad
    inc bx
    cmp bx,CHIP_SIZE
    jb .byte
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

chipset_settings_load:
    pushad
    mov di,C_CHIP
    call chipset_defaults
    mov al,0x69
    call rtc_read
    cmp al,0xD3
    jne .done
    mov bl,al
    xor bp,bp
.byte:
    mov ax,bp
    add al,0x6B
    call rtc_read
    mov [fs:C_CHIP+bp],al
    add bl,al
    inc bp
    cmp bp,21
    jb .byte
    mov al,0x6A
    call rtc_read
    add bl,al
    jnz .bad
    mov si,C_CHIP
    call chipset_valid
    jnc .done
.bad:
    mov di,C_CHIP
    call chipset_defaults
    mov byte [fs:C_VALID],0
.done:
    popad
    ret

chipset_settings_save:
    pushad
    mov si,U_CHIP
    call chipset_valid
    jc .bad
    mov ax,0xD269             ; Safe selection stays held until the whole Save verifies.
    call rtc_write
    mov ax,0xD269
    call settings_verify_byte
    jne .bad
    mov bl,0xD3
    xor bp,bp
.byte:
    mov ax,bp
    add al,0x6B
    mov ah,[fs:U_CHIP+bp]
    add bl,ah
    call rtc_write
    inc bp
    cmp bp,21
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
    mov ax,bp
    add al,0x6B
    mov ah,[fs:U_CHIP+bp]
    call settings_verify_byte
    jne .bad
    inc bp
    cmp bp,21
    jb .verify
    popad
    clc
    ret
.bad:
    mov ax,0xD269
    call rtc_write
    popad
    stc
    ret

chipset_apply:
    call chipset_timing_trial_begin
    call mp_timing_apply
    jmp cache_test
chipset_late_cache:
    ret                         ; The late memory owner activates shadow before L2.

; Pending timings are unconfirmed, not a measured RAM failure.
chipset_timing_startup_state:
    cmp al,0xAB
    jne .ram_state
    push ax
    mov ax,0xD269
    call rtc_write
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    jne chipset_timing_marker_failed
    pop ax
.ram_state:
    ram_test_startup_state
    ret

chipset_timing_trial_begin:
    pushf
    cli
    push ax
    mov al,0x36
    call rtc_read
    cmp al,0x5A
    je .done
    cmp al,0xDA
    je .done
    and al,0xBF
    cmp al,0x1A
    je .done                    ; Keep the existing measured-error retry guard.
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
    call rtc_read               ; Reset can arrive with caller-owned FS.
    cmp al,ah
    jne chipset_timing_marker_failed
    ret
chipset_timing_marker_failed:
    post_code_early 0xFB
    jmp hard_halt

; Shared settings_save calls this only after every record verifies.
chipset_timing_saved:
    push ax
    mov ax,0xD369
    call rtc_write
    mov ax,0xD369
    call settings_verify_byte
    jne .bad
    mov ax,0x0036
    call rtc_write
    mov ax,0x0036
    call settings_verify_byte
    jne .bad
    pop ax
    clc
    ret
.bad:
    mov ax,0xD269
    call rtc_write
    pop ax
    stc
    ret

mp_timing_restore:
    pushf
    cli
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    xor si,si
    call oem_cache_92EB          ; Complete reference holdoff before timing changes.
    mov di,C_CHIP
    call chipset_defaults
    call mp_timing_apply
    pop fs
    pop es
    pop ds
    popad
    popf
    ret

; MR98AB/AE9C masks only. The Mitsubishi mapper retains population and geometry.
mp_timing_apply:
    pushf
    cli
    pushad
    mov dx,0x0801
    mov bx,[fs:C_CHIP+2]
    mov cx,0x07EF
    call .merge
    inc dx
    movzx bx,byte [fs:C_CHIP+4]
    mov cx,0x003F
    call .merge
    xor si,si
    mov di,C_CHIP+7
.controller:
    mov dx,si
    or dl,3
    mov bx,[fs:C_CHIP+5]
    mov cx,0x7003
    call .merge
    inc dx
    mov bx,[fs:di]
    mov cx,0x1FFF
    call .merge
    inc dx
    mov bx,[fs:di+2]
    call .merge
    add di,4
    add si,0x100
    mov ax,si
    shr ax,8
    cmp ax,[fs:HW_MCU_COUNT]
    jb .controller
    popad
    popf
    ret
.merge:
    mp_mcu_read
    push cx
    not cx
    and ax,cx
    pop cx
    and bx,cx
    or ax,bx
    mp_mcu_write
    out 0xEB,ax
    out 0xEB,ax
    ret

mp_chip_default:
    db 0,1,0xA4,6,0x15,1,0x40
    dw 0x10E4,0x10E4,0x16E4,0x16E4,0x16E4,0x16E4
    times CHIP_SIZE-($-mp_chip_default) db 0
mp_chip_allowed:
    db 1,1,0xEF,7,0x3F,3,0x70
    times 6 db 0xFF,0x1F
    times CHIP_SIZE-($-mp_chip_allowed) db 0

%define chipset_ui_draw mp_chipset_fields_draw
%include "setup/chipset-menu.inc"
%undef chipset_ui_draw
chipset_ui_draw:
    call mp_chipset_fields_draw
    cmp byte [fs:U_CHIP_SCREEN],2
    jne .done
    ui_text 12,UI_LABEL_COL,mp_page_mode,7
    ui_text 12,UI_VALUE_COL,mp_board_controlled,8
    ui_text 13,UI_LABEL_COL,mp_interleave,7
    ui_text 13,UI_VALUE_COL,mp_board_controlled,8
.done:
    ret
%include "hardware/chipset-data.inc"
mp386_ram_sweep:
%include "firmware/ram-test.inc"
