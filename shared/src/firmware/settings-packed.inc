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
%ifdef BOARD_SETTINGS_LEGACY_CHIP_TAG
    jne .legacy
%else
    jne .invalid
%endif
    mov al,1
    jmp .done
.legacy:
    or al,bl
    or al,bh
%ifdef BOARD_SETTINGS_LEGACY_CHIP_TAG
    jz .legacy_valid
    ; An older adapter record can own these bytes before packed settings.
    mov al,0x69
    call rtc_read
    cmp al,BOARD_SETTINGS_LEGACY_CHIP_TAG
    jne .invalid
%else
    jnz .invalid
%endif
.legacy_valid:
    xor al,al
    jmp .done
.invalid:
    mov al,0xFF
.done:
    pop bx
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

%endif

; Recovery markers share one address owner with the extension format.
settings_recovery_index:
    ; Version survives an interrupted NV6 publication; marker33 may be invalid.
    mov al,0x34
    call rtc_read
    cmp al,6
    je .nv6
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
.nv6:
    mov al,0x69
    ret
settings_recovery_read:
    call settings_recovery_index
    jmp rtc_read
settings_recovery_publish:
    call settings_recovery_index
    mov ah,0xD2
    jmp rtc_write

%ifndef BOARD_PNP_NV6_LATE
%ifdef PRESARIO_SHARED_OWNER
%strcat PNP_SHARED_SOURCE PRESARIO_SOURCE_DIRECTORY,"../../shared/src/firmware/settings-nv6.inc"
%include PNP_SHARED_SOURCE
%else
%include "firmware/settings-nv6.inc"
%endif
%endif
