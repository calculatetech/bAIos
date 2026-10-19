bits 16
%ifdef RTC_BOOT_TEST
org 0x7C00
start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti
    cld
    mov si, stage_dap
    mov ax, 0x4200
    mov dl, 0x80
    int 0x13
    mov al, 0x71
    jc fail
    jmp 0:stage2
stage_dap:
    db 16,0
    dw 15,stage2,0
    dq 1
fail:
    cli
    mov bl, al
    mov [0x512], al
    push bx
    mov si, phase_dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    pop bx
    cli
    mov dx, 0x80
    mov al, '8'
    out dx, al
    mov al, '6'
    out dx, al
    mov al, 'B'
    out dx, al
    mov al, 'o'
    out dx, al
    mov al, 'x'
    out dx, al
    mov al, 1
    out dx, al
    mov al, 5
    out dx, al
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
.halt:
    cli
    hlt
    jmp .halt
times 510-($-$$) db 0
dw 0xAA55

stage2:
    mov si, phase_dap
    mov ax, 0x4200
    mov dl, 0x80
    int 0x13
    mov al, 0x72
    jc fail
    cmp byte [0x500], 0
    jne .seeded
    ; Establish a known clock in this disposable VM, then exercise actual POST.
    mov ah, 5
    mov cx, 0x2026
    mov dx, 0x0930
    int 0x1A
    mov al, 0x73
    jc fail
    mov ah, 3
    mov cx, 0x1321
    mov dx, 0x1000
    int 0x1A
    mov al, 0x74
    jc fail
    mov byte [0x500], 1
    call save_phase
    jmp 0xF000:0             ; Real reset entry, not an init_rtc helper fixture.
.seeded:
    call check_post_clock
    cmp byte [0x500], 4
    je .warm_verified
    cmp byte [0x500], 2
    jne .warm_request
    mov ah, 3
    xor cx, cx
    xor dx, dx
    int 0x1A
    mov al, 0x74
    jc fail
    mov byte [0x500], 3
    call save_phase
    jmp 0xF000:0
.warm_request:
    inc byte [0x500]         ; Phases1/3: nonzero/midnight software warm POST.
    call save_phase
    cli
    mov ax, [0x24]
    mov [old_irq1], ax
    mov ax, [0x26]
    mov [old_irq1+2], ax
    mov word [0x24], observed_irq1
    mov word [0x26], 0
    sti
    ; Production IRQ1/keyboard_poll owns the software-warm transition.
    mov al, 0x1D
    call send_scan
    mov al, 0x38
    call send_scan
    mov al, 0x53
    call send_scan
    mov cx, 180
.reset_wait:
    hlt
    loop .reset_wait
    mov al, 0x75
    jmp fail
.warm_verified:
    cli
    mov word [0x128], alarm_hook
    mov word [0x12A], 0
    sti
    mov word [alarm_count], 0
    call set_test_time
    mov ah, 6
    mov cx, 0x1234
    mov dx, 0x5200
    int 0x1A
    mov al, 0x76
    jc fail
    mov ah, 5
    mov cx, 0x2000
    mov dx, 0x0229
    int 0x1A
    mov al, 0x77
    jc fail
    mov bx, 1
    call wait_alarm
    call set_test_time        ; Setter must preserve the already armed alarm.
    mov bx, 2
    call wait_alarm
    mov ah, 7
    int 0x1A
    mov al, 0x78
    jc fail
    call set_test_time
    mov cx, 80
.canceled_wait:
    hlt
    loop .canceled_wait
    cmp word [alarm_count], 2
    mov al, 0x79
    jne fail
    cli
    mov ah, 1
    mov cx, 0x18
    mov dx, 0xAE
    int 0x1A
    sti
    mov bx, 90
.midnight:
    hlt
    xor ah, ah
    int 0x1A
    test al, al
    jnz .rolled
    dec bx
    jnz .midnight
    mov al, 0x7A
    jmp fail
.rolled:
    test cx, cx
    mov al, 0x7B
    jnz fail
    cmp dx, 4
    ja fail
    xor ah, ah
    int 0x1A
    test al, al
    mov al, 0x7C
    jnz fail
    mov ah, 4
    int 0x1A
    mov al, 0x7D
    jc fail
    cmp cx, 0x2000
    jne fail
    cmp dx, 0x0229
    jne fail
    mov al, 0x67
    jmp fail                 ; Unit tester exits with the pass code.

check_post_clock:
    mov ah, 2
    int 0x1A
    mov al, 0x40
    jc fail
    mov bx, 0x1321
    cmp byte [0x500], 3
    jb .expected_hour
    xor bx, bx
.expected_hour:
    cmp cx, bx
    jne fail
    mov [0x510], dx
    mov al, dh
    call from_bcd
    ; Use a 64-bit product, independently of the tick service's output.
    movzx eax, al
    cmp byte [0x500], 3
    jae .product
    add eax, 13*3600+21*60
.product:
    mov ebx, 1193182
    mul ebx
    shrd eax, edx, 16
    mov ebx, eax
    mov [0x504], ebx
    xor ah, ah
    int 0x1A
    movzx eax, cx
    shl eax, 16
    mov ax, dx
    mov [0x508], eax
    sub eax, ebx
    mov [0x50C], eax
    cmp eax, 40              ; Snapshot may trail by a second during boot.
    jbe .date
    cmp eax, -40
    mov al, 0x41
    jb fail
.date:
    mov ah, 4
    int 0x1A
    mov al, 0x42
    jc fail
    cmp cx, 0x2026
    jne fail
    cmp dx, 0x0930
    jne fail
    ret
from_bcd:
    mov ah, al
    and al, 15
    shr ah, 4
    aad
    ret
save_phase:
    mov si, phase_dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 0x43
    jc fail
    ret
phase_dap:
    db 16,0
    dw 1,0x500,0
    dq 32
set_test_time:
    mov ah, 3
    mov cx, 0x1234
    mov dx, 0x5000
    int 0x1A
    mov al, 0x44
    jc fail
    ret
wait_alarm:
    mov cx, 180
.wait:
    cmp [alarm_count], bx
    je .done
    hlt
    loop .wait
    mov al, 0x45
    jmp fail
.done:
    ret
alarm_hook:
    inc word [cs:alarm_count]
    iret
alarm_count dw 0
old_irq1 dw 0,0
irq1_count dw 0
observed_irq1:
    pushf
    call far [cs:old_irq1]
    inc word [cs:irq1_count]
    iret
send_scan:
    push bx
    push cx
    push si
    mov bl, al
    in al, 0x21
    push ax
    or al, 1
    out 0x21, al
    mov si, [irq1_count]
    call wait_kbc
    mov al, 0xD2
    out 0x64, al
    call wait_kbc
    mov al, bl
    out 0x60, al
    ; Observe completion, not OBF sampled before the response is ready.
    mov cx, 0xFFFF
.drain:
    sti
    nop
    cmp si, [irq1_count]
    jne .done
    loop .drain
    mov al, 0x46
    jmp fail
.done:
    pop ax
    out 0x21, al
    pop si
    pop cx
    pop bx
    ret
wait_kbc:
    mov cx, 0xFFFF
.wait:
    in al, 0x64
    test al, 2
    jz .done
    loop .wait
    mov al, 0x47
    jmp fail
.done:
    ret
times 8192-($-$$) db 0

%elifdef RTC_SPEEDSYS_TEST
org 0x100
start:
    push cs
    pop ds
    push cs
    pop es
    cld
    mov di, 0x49FD
    mov cx, 0x25
    xor al, al
    rep stosb
    mov dword [0x4A02], 0x01012000
    mov dword [0x4A06], 0x12311999
    mov dword [0x4A0A], 0x59002359
    mov dx, probe_banner
    mov ah, 9
    int 0x21
    call speedsys_y2k
    pushf
    pop ax
    and al, 1
    mov [result], al
    mov dx, cf_text
    mov ah, 9
    int 0x21
    mov al, [result]
    call print_bcd
    mov dx, y2k_text
    mov ah, 9
    int 0x21
    mov al, [0x49FD]
    call print_bcd
    mov dx, dates_text
    mov ah, 9
    int 0x21
    mov si, 0x4A0E
    call print_date
    mov dl, ' '
    call putc
    mov si, 0x4A16
    call print_date
    mov dx, end_text
    mov ah, 9
    int 0x21
%ifdef RTC_SPEEDSYS_EMULATOR
    mov bl, 0x67
    cmp byte [result], 0
    jne .failed
    cmp byte [0x49FD], 0
    jne .failed
    cmp dword [0x4A16], 0x01012000
    je .exit
.failed:
    mov bl, 0x68
.exit:
    mov dx, 0x80
    mov si, tester
.enable:
    lodsb
    out dx, al
    test al, al
    jnz .enable
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
tester db '86Box',1,5,0
%else
    mov ax, 0x4C00
    int 0x21
%endif
print_date:
    mov al, [si+1]
    call print_bcd
    mov al, [si]
    call print_bcd
    mov dl, '-'
    call putc
    mov al, [si+3]
    call print_bcd
    mov dl, '-'
    call putc
    mov al, [si+2]
    jmp print_bcd
putc:
    push ax
    mov ah, 2
    int 0x21
    pop ax
    ret
print_bcd:
    push dx
    push ax
    mov dl, al
    shr dl, 4
    add dl, '0'
    call putc
    pop ax
    mov dl, al
    and dl, 15
    add dl, '0'
    call putc
    pop dx
    ret
result db 0
probe_banner db 'Speedsys 4.78 RTC sequence: temporarily tests 1999 rollover, restores clock.',13,10,'$'
cf_text db 'Return CF=', '$'
y2k_text db ' Y2K mismatch=', '$'
dates_text db 13,10,'Saved / rollover date: ', '$'
end_text db 13,10,'$'

; Original 9B90..9BCA and 9C10..9C7F, with their original relative layout.
; Absolute references address the original 49FD..4A21 workspace above.
speedsys_y2k:
    db 0xE8,0x7D,0,0x72,0x35,0xA0,0x15,0x4A,0x3C,0x59,0x74,0xF4,0x04,0x01,0x27,0xA2
    db 0x15,0x4A,0xE8,0xC0,0,0x72,0x20,0xE8,0x9E,0,0x72,0x1B,0x80,0x3E,0x1D,0x4A
    db 0x59,0x74,0xF4,0x66,0xA1,0x16,0x4A,0x66,0x39,0x06,0x02,0x4A,0x74,0x09,0xC6,0x06
    db 0xFD,0x49,0x01,0x66,0xA3,0xFE,0x49,0xE8,0x63,0,0xC3
    times 0x80-($-speedsys_y2k) db 0
    db 0xB4,0x02,0xCD,0x1A,0x72,0x16,0x89,0x0E,0x12,0x4A,0x89,0x16,0x14,0x4A,0xB4,0x04
    db 0xCD,0x1A,0x72,0x08,0x89,0x16,0x10,0x4A,0x89,0x0E,0x0E,0x4A,0xC3,0x8B,0x0E,0x12
    db 0x4A,0x8B,0x16,0x14,0x4A,0xB4,0x03,0xCD,0x1A,0x72,0x0C,0x8B,0x16,0x10,0x4A,0x8B
    db 0x0E,0x0E,0x4A,0xB4,0x05,0xCD,0x1A,0xC3,0xB4,0x02,0xCD,0x1A,0x72,0x16,0x89,0x0E
    db 0x1A,0x4A,0x89,0x16,0x1C,0x4A,0xB4,0x04,0xCD,0x1A,0x72,0x08,0x89,0x16,0x18,0x4A
    db 0x89,0x0E,0x16,0x4A,0xC3,0x8B,0x0E,0x0A,0x4A,0x8B,0x16,0x0C,0x4A,0xB4,0x03,0xCD
    db 0x1A,0x72,0x0C,0x8B,0x16,0x08,0x4A,0x8B,0x0E,0x06,0x4A,0xB4,0x05,0xCD,0x1A,0xC3
%else
org 0x100
start:
    push cs
    pop ds
    mov ah, 4
    int 0x1A
    jc unavailable
    mov [date], cx
    mov [date+2], dx
    mov ah, 2
    int 0x1A
    jc unavailable
    mov [time], cx
    mov [time+2], dx
    mov dx, banner
    mov ah, 9
    int 0x21
    mov al, [date+1]
    call print_bcd
    mov al, [date]
    call print_bcd
    mov dl, '-'
    call putc
    mov al, [date+3]
    call print_bcd
    mov dl, '-'
    call putc
    mov al, [date+2]
    call print_bcd
    mov dl, ' '
    call putc
    mov al, [time+1]
    call print_bcd
    mov dl, ':'
    call putc
    mov al, [time]
    call print_bcd
    mov dl, ':'
    call putc
    mov al, [time+3]
    call print_bcd
    xor ah, ah
    int 0x1A
    mov [ticks], dx
    mov [ticks+2], cx
    mov dx, prompt
    mov ah, 9
    int 0x21
    mov ah, 8
    int 0x21                 ; User wait: no dependency on a possibly bad timer.
    mov ah, 2
    int 0x1A
    jc unavailable
    cmp cx, [time]
    jne .advanced
    cmp dh, [time+3]
    je unchanged
.advanced:
    xor ah, ah
    int 0x1A
    cmp cx, [ticks+2]
    jne .pass
    cmp dx, [ticks]
    je unchanged
.pass:
    mov dx, passed
    mov ah, 9
    int 0x21
    mov ax, 0x4C00
    int 0x21
unavailable:
    mov dx, unavailable_text
    jmp error
unchanged:
    mov dx, unchanged_text
error:
    mov ah, 9
    int 0x21
    mov ax, 0x4C01
    int 0x21
putc:
    push ax
    mov ah, 2
    int 0x21
    pop ax
    ret
print_bcd:
    push dx
    push ax
    mov dl, al
    shr dl, 4
    add dl, '0'
    call putc
    pop ax
    mov dl, al
    and dl, 15
    add dl, '0'
    call putc
    pop dx
    ret
date dw 0,0
time dw 0,0
ticks dw 0,0
banner db 'Read-only BIOS clock check: ', '$'
prompt db 13,10,'Wait a few seconds, then press a key.',13,10,'$'
passed db 'RTC and BIOS tick counter both advance.',13,10,'$'
unavailable_text db 'RTC is invalid or unavailable. Set DOS DATE and TIME, then retry.',13,10,'$'
unchanged_text db 'Clock did not advance. Wait longer and retry.',13,10,'$'
%endif
