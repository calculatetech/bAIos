; Four-device extension: marker33..35 = 34h,02h,CAh; legacy writes all zero.
%if BOARD_ATA_DEVICE_COUNT = 4
settings_format:
    push bx
    mov al,0x33
    call rtc_read
    mov bl,al
    mov al,0x34
    call rtc_read
    mov bh,al
    mov al,0x35
    call rtc_read
    cmp bx,0x0234
    jne .legacy
    cmp al,0xCA
    jne .invalid
    mov al,1
    jmp .done
.legacy:
    or al,bl
    or al,bh
    jnz .invalid
    xor al,al
    jmp .done
.invalid:
    mov al,0xFF
.done:
    pop bx
    ret

; Full Settings Save alone migrates the overlapping extension owners.
settings_format_prepare:
    pushad
    mov si,U_IDE
    call ide_settings_valid
    jc .bad
    mov si,U_PORTS
    call ports_valid
    jc .bad
    mov si,U_CHIP
    call chipset_valid
    jc .bad
    mov ax,0x0033
    call rtc_write
    mov ax,0x0234
    call rtc_write
    mov ax,0x0234
    call settings_verify_byte
    jne .bad
    mov ax,0xCA35
    call rtc_write
    mov ax,0xCA35
    call settings_verify_byte
    jne .bad
    mov ax,0x3433
    call rtc_write
    mov ax,0x3433
    call settings_verify_byte
    jne .bad
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

; AL=CMOS start, CX=length, SS:DI=buffer. Checksum covers the whole record.
settings_record_read:
    pushad
    mov dl,al
    xor bl,bl
.byte:
    mov al,dl
    call rtc_read
    mov [ss:di],al
    add bl,al
    inc di
    inc dl
    loop .byte
    test bl,bl
    jnz .bad
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

; AL=start, AH=invalid marker, CX=length, SS:DI=complete checksummed record.
settings_record_write:
    pushad
    mov bx,ax
    call rtc_write
    mov dl,bl
    inc dl
    mov si,di
    inc si
    dec cx
    push cx
.byte:
    mov al,dl
    mov ah,[ss:si]
    call rtc_write
    inc si
    inc dl
    loop .byte
    pop cx
    mov dl,bl
    inc dl
    mov si,di
    inc si
.verify:
    mov al,dl
    mov ah,[ss:si]
    call settings_verify_byte
    jne .bad
    inc si
    inc dl
    loop .verify
    mov al,bl
    mov ah,[ss:di]
    call rtc_write
    mov al,bl
    mov ah,[ss:di]
    call settings_verify_byte
    jne .bad
    popad
    clc
    ret
.bad:
    mov ax,bx
    call rtc_write
    popad
    stc
    ret

; SS:DI=record, CX=length, BX=checksum byte offset.
settings_record_checksum:
    pushad
    mov byte [ss:di+bx],0
    mov si,di
    xor al,al
.byte:
    add al,[ss:si]
    inc si
    loop .byte
    neg al
    mov [ss:di+bx],al
    popad
    ret

; Pack/unpack mask-selected bits, low bit first. The packed buffer starts zero.
; FS:SI=unpacked bytes, CS:BX=masks, CX=unpacked length, SS:DI=packed bytes.
settings_pack:
    pushad
    mov dl,1
.byte:
    mov al,[fs:si]
    mov ah,[cs:bx]
    mov dh,1
.bit:
    test ah,dh
    jz .next_bit
    test al,dh
    jz .advance
    or [ss:di],dl
.advance:
    shl dl,1
    jnz .next_bit
    inc di
    mov dl,1
.next_bit:
    shl dh,1
    jnz .bit
    inc si
    inc bx
    loop .byte
    popad
    ret

settings_unpack:
    pushad
    mov dl,1
.byte:
    mov byte [fs:si],0
    mov ah,[cs:bx]
    mov dh,1
.bit:
    test ah,dh
    jz .next_bit
    test [ss:di],dl
    jz .advance
    or [fs:si],dh
.advance:
    shl dl,1
    jnz .next_bit
    inc di
    mov dl,1
.next_bit:
    shl dh,1
    jnz .bit
    inc si
    inc bx
    loop .byte
    popad
    ret
%endif

; Recovery markers share one address owner with the extension format.
settings_recovery_index:
%if BOARD_ATA_DEVICE_COUNT = 4
    call settings_format
    test al,al
    mov al,0x69
    jz .done
    mov al,0x71
.done:
%else
    mov al,0x69
%endif
    ret
settings_recovery_read:
    call settings_recovery_index
    jmp rtc_read
settings_recovery_publish:
    call settings_recovery_index
    mov ah,0xD2
    jmp rtc_write
