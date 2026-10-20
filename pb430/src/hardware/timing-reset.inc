; Stackless restoration precedes every stock cache/reset owner. CMOS37 is private.
%macro pb430_trial_write 2
    mov al,%1 | 0x80
    out 0x70,al
    in al,0x84
    mov al,%2
    out 0x71,al
    mov al,%1 | 0x80
    out 0x70,al
    in al,0x84
    in al,0x71
    cmp al,%2
    je %%done
    mov al,0xFB
    out 0x80,al
    jmp hard_halt
%%done:
%endmacro

; Like Presario, an interrupted POST is not a detected RAM failure.
; Service-resume entries bypass this normal-reset owner.
%macro pb430_timing_recover 0
    mov al,0xB6
    out 0x70,al
    in al,0x84
    in al,0x71
    cmp al,0xAB
    jne %%done
    ram_test_startup_state
    pb430_trial_write 0x36,ah
%%done:
%endmacro

%macro pb430_restore_field 4
    mov al,%1
    out 0xF2,al
    out 0xED,al
    in al,0xF3
    and al,(~(%2))&255
    or al,%3
    mov ah,al
    out 0xF3,al
    out 0xED,al
    in al,0xF3
    xor al,ah
    test al,%2
    jz %%done
    mov al,%4
    out 0x80,al
    jmp hard_halt
%%done:
%endmacro

%macro pb430_timing_restore 0
    ; Return to the jumper-selected source divider before stock cache owners.
    in al,0x78
    and al,7
    mov bl,0x13
    cmp al,5
    jne %%clock
    mov bl,0x17
%%clock:
    mov al,6
    out 0xF2,al
    out 0xED,al
    in al,0xF3
    and al,0x1F
    cmp al,bl
    je %%clock_done
    pb430_restore_field 6,0x1F,bl,0xFE
%%clock_done:
    pb430_restore_field 0x18,1,0,0xF3
    pb430_restore_field 4,0x10,0x10,0xF7
    mov al,0xB7
    out 0x70,al
    in al,0x84
    in al,0x71
    mov bl,al
    and al,0xF0
    cmp al,0xB0
    jne %%ordinary_cookie
    test bl,4
    jz %%refresh_mode
    mov bh,bl
    and bl,3
    pb430_restore_field 0x37,3,bl,0xFC
    mov bl,bh
%%refresh_mode:
    and bl,8
    shl bl,3
    pb430_restore_field 3,0x40,bl,0xFD
    pb430_trial_write 0x37,0xA7
    mov bl,0xA7
%%ordinary_cookie:
    mov al,bl
    cmp al,0xA7
    jne %%legacy
    ; Lengthen CAS before removing the advance used by the Fast profile.
    pb430_restore_field 0x0B,0xFF,0x15,0xF1
    pb430_restore_field 0x16,0x7F,0,0xF2
    pb430_restore_field 0x18,0xF3,0,0xF3
    pb430_restore_field 0x19,0xF7,0,0xF4
    pb430_restore_field 0x12,0xC0,0,0xF5
    pb430_restore_field 0x14,0x58,0,0xF6
    pb430_restore_field 4,0xF8,0x10,0xF7
    pb430_restore_field 5,3,0,0xF8
    mov al,1
    out 0xF2,al
    out 0xED,al
    mov al,0x93
    out 0xF3,al
    out 0xED,al
    in al,0xF3
    and al,0xD3
    cmp al,0x93
    jne %%failed
    mov al,0xB7
    out 0x70,al
    in al,0x84
    xor al,al
    out 0x71,al
    mov al,0xB7 ; A data access need not retain the RTC address latch.
    out 0x70,al
    in al,0x84
    in al,0x71
    test al,al
    jz %%legacy
    mov al,0xFA ; Recovery marker could not be cleared.
    out 0x80,al
    jmp hard_halt
%%legacy:
    ; Also accept a running image from before the timing-cookie extension.
    in al,0x78
    and al,7
    cmp al,5
    jne %%ras
    mov al,0x0B
    out 0xF2,al
    out 0xED,al
    in al,0xF3
    cmp al,4
    jne %%ras
    pb430_restore_field 0x0B,0xFF,0x15,0xF1
%%ras:
    mov al,1
    out 0xF2,al
    out 0xED,al
    in al,0xF3
    and al,0xD3
    cmp al,0x83
    jne %%done
    mov al,0x93
    out 0xF3,al
    out 0xED,al
    in al,0xF3
    and al,0xD3
    cmp al,0x93
    je %%done
%%failed:
    mov al,0xF9 ; RAS timeout restoration failed.
    out 0x80,al
    jmp hard_halt
%%done:
%endmacro
