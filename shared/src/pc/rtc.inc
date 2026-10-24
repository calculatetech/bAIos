; AT clock services. OEM F000:9BE2/BD40/CA97 and MC146818A register rules.
; The public interface is BCD; stored binary/12-hour values remain native.

rtc_read:
    pushf
    cli
%ifdef BOARD_RTC_EXTENDED_READ
    test al,0x40
    jz .ordinary
    call BOARD_RTC_EXTENDED_READ
    popf
    ret
.ordinary:
%endif
%if RTC_NMI_SELECT_MASK != 0
    or al, RTC_NMI_SELECT_MASK
%endif
    out 0x70, al              ; OEM runtime policy: enable NMI, no readable latch.
    in al, 0x84
    in al, 0x71
    popf
    ret

rtc_write:
    pushf
    cli
%ifdef BOARD_RTC_EXTENDED_WRITE
    test al,0x40
    jz .ordinary
    call BOARD_RTC_EXTENDED_WRITE
    popf
    ret
.ordinary:
%endif
%if RTC_NMI_SELECT_MASK != 0
    or al, RTC_NMI_SELECT_MASK
%endif
    out 0x70, al
    in al, 0x84
    mov al, ah
    out 0x71, al
    popf
    ret

; D reads set VRT on the original chip. Retain loss in the AT diagnostic
; byte until both clock domains have been explicitly initialized.
rtc_check_power:
    mov al, 0x0D
    call rtc_read
    test al, 0x80
    jnz .latched
    mov byte [fs:S_RTC_REPAIRED], 0
    mov al, 0x0E
    call rtc_read
    or al, 0x80
    mov ah, al
    mov al, 0x0E
    call rtc_write
.latched:
    mov al, 0x0E
    call rtc_read
    shl al, 1                 ; CF is the power-loss diagnostic.
    ret

; AL is the repaired domain (1 time, 2 date), FS is our EBDA.
rtc_repaired:
    or [fs:S_RTC_REPAIRED], al
    cmp byte [fs:S_RTC_REPAIRED], 3
    jne .done
    mov al, 0x0D
    call rtc_read
    test al, 0x80
    jz .done                  ; Power sense still low: do not claim validity.
    mov al, 0x0E
    call rtc_read
    and al, 0x7F
    mov ah, al
    mov al, 0x0E
    call rtc_write
.done:
    ret

; BH returns register B. No tick-dependent timeout: POST has IF clear.
rtc_ready:
    call rtc_check_power
    jc .bad
    mov al, 0x0B
    call rtc_read
    mov bh, al
    test al, 0x80
    jnz .bad
    mov si, 0xFFFF
.wait:
    mov al, 0x0A
    call rtc_read
    test al, 0x80
    jz .ready
    dec si
    jnz .wait
.bad:
    stc
    ret
.ready:
    clc
    ret

rtc_from_bcd:
    mov ah, al
    and al, 0x0F
    shr ah, 4
    cmp al, 9
    ja .bad
    cmp ah, 9
    ja .bad
    aad
    clc
    ret
.bad:
    stc
    ret

rtc_to_bcd:
    aam
    shl ah, 4
    or al, ah
    ret

rtc_decode:
    test bh, 4
    jz rtc_from_bcd
    clc
    ret

rtc_encode:
    test bh, 4
    jz rtc_to_bcd
    ret

rtc_decode_hour:
    test bh, 2
    jnz .hour24
    mov ah, al
    and ah, 0x80
    push ax
    and al, 0x7F
    call rtc_decode
    pop si
    jc .bad
    cmp al, 1
    jb .bad
    cmp al, 12
    ja .bad
    cmp al, 12
    jne .pm
    xor al, al
.pm:
    test si, 0x8000
    jz .ok
    add al, 12
.ok:
    clc
    ret
.hour24:
    call rtc_decode
    jc .bad
    cmp al, 23
    ja .bad
    clc
    ret
.bad:
    stc
    ret

rtc_encode_hour:
    test bh, 2
    jnz rtc_encode
    push dx
    xor dl, dl
    cmp al, 12
    jb .am
    mov dl, 0x80
    sub al, 12
.am:
    test al, al
    jnz .encode
    mov al, 12
.encode:
    call rtc_encode
    or al, dl
    pop dx
    ret

; CH/CL/DH public BCD -> binary, invalid input returns CF before any I/O.
rtc_validate_time:
    mov al, ch
    call rtc_from_bcd
    jc .bad
    cmp al, 23
    ja .bad
    mov ch, al
    mov al, cl
    call rtc_from_bcd
    jc .bad
    cmp al, 59
    ja .bad
    mov cl, al
    mov al, dh
    call rtc_from_bcd
    jc .bad
    cmp al, 59
    ja .bad
    mov dh, al
    clc
    ret
.bad:
    stc
    ret

; SI is 1980..2099; the only century in this range (2000) is a leap year.
rtc_leap:
    test si, 3
    jnz .no
    stc
    ret
.no:
    clc
    ret

; Validate public BCD date, return weekday AL (Sunday=1), preserve inputs.
rtc_validate_date:
    pushad
    mov al, ch
    call rtc_from_bcd
    jc .bad
    cmp al, 19
    je .century
    cmp al, 20
    jne .bad
.century:
    movzx esi, al
    imul esi, 100
    mov al, cl
    call rtc_from_bcd
    jc .bad
    movzx eax, al
    add esi, eax
    cmp esi, 1980            ; DOS calendar; avoids ambiguous 1900..1979 recovery.
    jb .bad
    mov al, dh
    call rtc_from_bcd
    jc .bad
    cmp al, 1
    jb .bad
    cmp al, 12
    ja .bad
    movzx edi, al
    mov al, dl
    call rtc_from_bcd
    jc .bad
    movzx ebx, al
    test bl, bl
    jz .bad
    mov al, [cs:rtc_month_lengths + edi - 1]
    cmp di, 2
    jne .day_limit
    call rtc_leap
    jnc .day_limit
    inc al
.day_limit:
    cmp bl, al
    ja .bad
    push ebx
    mov ebp, esi
    dec ebp
    imul ecx, ebp, 365
    mov eax, ebp
    shr eax, 2
    add ecx, eax
    mov eax, ebp
    xor edx, edx
    mov ebx, 100
    div ebx
    sub ecx, eax
    mov eax, ebp
    xor edx, edx
    mov ebx, 400
    div ebx
    add ecx, eax
    movzx eax, word [cs:rtc_month_days + edi * 2 - 2]
    add ecx, eax
    cmp di, 2
    jbe .weekday
    call rtc_leap
    jnc .weekday
    inc ecx
.weekday:
    pop ebx
    add ecx, ebx
    mov eax, ecx
    xor edx, edx
    mov ecx, 7
    div ecx
    mov al, dl
    inc al
    mov di, sp
    mov [ss:di + 28], al
    popad
    clc
    ret
.bad:
    popad
    stc
    ret
rtc_month_lengths db 31,28,31,30,31,30,31,31,30,31,30,31
rtc_month_days dw 0,31,59,90,120,151,181,212,243,273,304,334

; A bounded stable-second snapshot, with a final UIP check.
; Time returns binary CH/CL/DH and DST DL, date returns public BCD CX/DX.
rtc_time_snapshot:
    mov di, 8
.retry:
    call rtc_ready
    jc .bad
    mov al, 0
    call rtc_read
    mov bl, al
    call rtc_decode
    jc .bad
    cmp al, 59
    ja .bad
    mov dh, al
    mov al, 2
    call rtc_read
    call rtc_decode
    jc .bad
    cmp al, 59
    ja .bad
    mov cl, al
    mov al, 4
    call rtc_read
    call rtc_decode_hour
    jc .bad
    mov ch, al
    mov dl, bh
    and dl, 1
    call rtc_snapshot_end
    jnc .done
    dec di
    jnz .retry
.bad:
    stc
.done:
    ret

rtc_date_snapshot:
    mov di, 8
.retry:
    call rtc_ready
    jc .bad
    mov al, 0
    call rtc_read
    mov bl, al
    mov al, 7
    call rtc_read
    call rtc_decode
    jc .bad
    cmp al, 31
    ja .bad
    call rtc_to_bcd
    mov dl, al
    mov al, 8
    call rtc_read
    call rtc_decode
    jc .bad
    cmp al, 12
    ja .bad
    call rtc_to_bcd
    mov dh, al
    mov al, 9
    call rtc_read
    call rtc_decode
    jc .bad
    cmp al, 99
    ja .bad
    call rtc_to_bcd
    mov cl, al
    mov al, RTC_CENTURY_REGISTER
    call rtc_read
    mov ch, al
    call rtc_snapshot_end
    jnc .validate
    dec di
    jnz .retry
.bad:
    stc
    ret
.validate:
    mov bh, ch
    cmp ch, 0x19
    jne .calendar
    cmp cl, 0x80
    jae .calendar
    mov ch, 0x20             ; YY rolls independently of CMOS32 (Y2K).
.calendar:
    call rtc_validate_date
    jc .bad
    cmp bh, ch
    je .valid
    mov ah, ch
    mov al, RTC_CENTURY_REGISTER
    call rtc_write           ; Century is ordinary RAM, not an updating clock byte.
.valid:
    clc
    ret

rtc_snapshot_end:
    mov al, 0
    call rtc_read
    cmp al, bl
    jne .changed
    mov al, 0x0A
    call rtc_read
    shl al, 1
    ret
.changed:
    stc
    ret

init_rtc:
    pushf
    cli
    pushad
    push ds
    push fs
    call load_bios_state
    mov byte [fs:S_RTC_REPAIRED], 0
    mov al, 0x0A
    call rtc_read
    and al, 0x0F
    or al, 0x20               ; OEM 32.768 kHz divider, retain periodic rate.
    mov ah, al
    mov al, 0x0A
    call rtc_write
    mov al, 0x0B
    call rtc_read
    and al, 7                 ; Keep native format/DST, clear stale SET/IRQs.
    mov ah, al
    mov al, 0x0B
    call rtc_write
    mov al, 0x0C
    call rtc_read
    call rtc_date_snapshot    ; Also repair a century rollover while powered off.
    call rtc_sync_ticks
    pop fs
    pop ds
    popad
    popf
    ret

; POST has long IF-clear sections (VGA, keyboard, L2). Resample before
; boot so those sections cannot leave DOS several seconds behind the RTC.
rtc_sync_ticks:
    pushf
    cli
    pushad
    push ds
    push fs
    call load_bios_state
    mov ax, 0x0040
    mov ds, ax
    mov dword [0x006C], 0
    mov byte [0x0070], 0
    call rtc_time_snapshot
    jc .done
    movzx eax, ch
    imul eax, 60
    movzx ecx, cl
    add eax, ecx
    imul eax, 60
    movzx edx, dh
    add eax, edx
    mov ecx, 1193182          ; PIT clock / 65536 ticks per second.
    mul ecx
    shrd eax, edx, 16
    mov [0x006C], eax
.done:
    pop fs
    pop ds
    popad
    popf
    ret

RTC_INTERRUPT_LABEL:
    push bp
    mov bp, sp
    pushad
    push ds
    push fs
    call load_bios_state
    mov bx, 0x0040
    mov ds, bx
    cmp ah, 0
    je .ticks_get
    cmp ah, 1
    je .ticks_set
    cmp ah, 2
    je .time_get
    cmp ah, 3
    je .time_set
    cmp ah, 4
    je .date_get
    cmp ah, 5
    je .date_set
    cmp ah, 6
    je .alarm_set
    cmp ah, 7
    je .alarm_cancel
.bad:
    or word [ss:bp + 6], 1
    jmp .return
.ok:
    mov byte [ss:bp - 3], 0   ; Documented AH=0; retain upper register halves.
    and word [ss:bp + 6], 0xFFFE
.return:
    pop fs
    pop ds
    popad
    pop bp
    iret
.ticks_get:
    mov cx, [0x006E]
    mov dx, [0x006C]
    xor al, al
    xchg al, [0x0070]
    mov [ss:bp - 4], al
    jmp .output
.ticks_set:
    mov [0x006E], cx
    mov [0x006C], dx
    mov byte [0x0070], 0
    jmp .ok
.time_get:
    call rtc_time_snapshot
    jc .bad
    mov al, ch
    call rtc_to_bcd
    mov ch, al
    mov al, cl
    call rtc_to_bcd
    mov cl, al
    mov al, dh
    call rtc_to_bcd
    mov dh, al
    jmp .output
.date_get:
    call rtc_date_snapshot
    jc .bad
.output:
    mov [ss:bp - 8], cx
    mov [ss:bp - 12], dx
    jmp .ok
.time_set:
    cmp dl, 1
    ja .bad
    call rtc_validate_time
    jc .bad
    call rtc_check_power
    call .freeze
    mov al, dh
    call rtc_encode
    mov ah, al
    mov al, 0
    call rtc_write
    mov al, cl
    call rtc_encode
    mov ah, al
    mov al, 2
    call rtc_write
    mov al, ch
    call rtc_encode_hour
    mov ah, al
    mov al, 4
    call rtc_write
    and bh, 0xFE
    or bh, dl
    call .resume
    mov al, 1
    call rtc_repaired
    jmp .ok
.date_set:
    call rtc_validate_date
    jc .bad
    mov si, ax               ; Save computed weekday through power check.
    call rtc_check_power
    call .freeze
    mov ax, si
    call rtc_encode
    mov ah, al
    mov al, 6
    call rtc_write
    mov al, dl
    call rtc_from_bcd
    call rtc_encode
    mov ah, al
    mov al, 7
    call rtc_write
    mov al, dh
    call rtc_from_bcd
    call rtc_encode
    mov ah, al
    mov al, 8
    call rtc_write
    mov al, cl
    call rtc_from_bcd
    call rtc_encode
    mov ah, al
    mov al, 9
    call rtc_write
    mov ah, ch
    mov al, RTC_CENTURY_REGISTER
    call rtc_write
    call .resume
    mov al, 2
    call rtc_repaired
    jmp .ok
.freeze:
    mov al, 0x0B
    call rtc_read
    mov bh, al
    or al, 0x80
    mov ah, al
    mov al, 0x0B
    call rtc_write
    ret
.resume:
    mov ah, bh
    and ah, 0x7F
    mov al, 0x0B
    call rtc_write
    ret
.alarm_set:
    call rtc_validate_time
    jc .bad
    call rtc_ready
    jc .bad
    test bh, 0x20
    jnz .bad
    mov al, dh
    call rtc_encode
    mov ah, al
    mov al, 1
    call rtc_write
    mov al, cl
    call rtc_encode
    mov ah, al
    mov al, 3
    call rtc_write
    mov al, ch
    call rtc_encode_hour
    mov ah, al
    mov al, 5
    call rtc_write
    mov al, 0x0C
    call rtc_read             ; Discard pre-arm AF before enabling its source.
    mov ah, bh
    or ah, 0x20
    mov al, 0x0B
    call rtc_write
    in al, 0xA1
    and al, 0xFE
    out 0xA1, al
    in al, 0x84
    in al, 0x21
    and al, 0xFB
    out 0x21, al
    in al, 0x84
    jmp .ok
.alarm_cancel:
    mov al, 0x0B
    call rtc_read
    and al, 0xDF
    mov ah, al
    mov al, 0x0B
    call rtc_write
    jmp .ok

int70:
    pushad
    push ds
    push es
    push fs
    push gs
    mov al, 0x0B
    call rtc_read
    mov bl, al
    mov al, 0x0C
    call rtc_read             ; Acknowledge all RTC causes even after cancel.
    and al, 0xA0
    cmp al, 0xA0
    jne .eoi
    test bl, 0x20
    jz .eoi
    int 0x4A                 ; Daily until AH07; callback may cancel itself.
    cli
.eoi:
    mov al, 0x60
    out 0xA0, al
    mov al, 0x62
    out 0x20, al
    pop gs
    pop fs
    pop es
    pop ds
    popad
    iret
