; Presario-only clean-DOS experiment, not a resident driver or BIOS fix.
; Reproduce OEM F000:F5A4 (D1/DD, FF), also clear the fast A20 source.
; No disk writes. Refuse XMS and protected/V86 mode before changing hardware.
bits 16
org 0x100
start:
    smsw ax
    test al, 1
    jnz refused
    mov ax, 0x4300
    int 0x2F
    cmp al, 0x80
    je refused
%ifdef EXPECT_REFUSED
    jmp failed
%endif
    call a20_state
    add al, '0'
    mov [before_digit], al
    pushf
    cli
    wbinvd
    call input_ready
    jc .timeout
    mov al, 0xD1
    out 0x64, al
    call input_ready
    jc .timeout
    mov al, 0xDD
    out 0x60, al
    call input_ready
    jc .timeout
    mov al, 0xFF
    out 0x64, al
    call input_ready
    jc .timeout
    in al, 0x92
    and al, 0xFC                 ; Never write the fast-reset bit as one.
    out 0x92, al
    wbinvd
    popf
    call a20_state
    test al, al
    jnz failed
    mov dx, success_message
    xor bl, bl
    jmp report
.timeout:
    popf
failed:
    mov dx, failed_message
    mov bl, 1
    jmp report
refused:
    mov dx, refused_message
    mov bl, 2
report:
    mov ah, 9
    int 0x21
%ifdef EMULATOR_TEST
%ifdef EXPECT_REFUSED
    cmp bl, 2
%else
    cmp bl, 0
%endif
    mov bl, 0x68
    jne .test_exit
    mov bl, 0x67
.test_exit:
    mov dx, 0x80
    mov si, tester
.enable:
    lodsb
    out dx, al
    cmp si, tester_end
    jb .enable
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
    jmp $
%endif
    mov al, bl
    mov ah, 0x4C
    int 0x21

input_ready:
    mov cx, 0xFFFF
.wait:
    in al, 0x64
    test al, 2
    jz .ready
    loop .wait
    stc
    ret
.ready:
    clc
    ret

; Return AL=0 for aliasing (disabled), AL=1 for enabled. Preserve all RAM.
; A complementary pattern avoids mistaking coincidentally equal bytes for
; aliasing. Interrupts stay masked until the low-memory word is restored.
a20_state:
    pushf
    cli
    push bx
    push dx
    push es
    push fs
    xor ax, ax
    mov es, ax
    dec ax
    mov fs, ax
    mov bx, [es:0x500]
    mov dx, [fs:0x510]           ; Physical 100500h if A20 is enabled.
    not dx
    mov [es:0x500], dx
    xor al, al
    cmp [fs:0x510], dx
    setne al
    mov [es:0x500], bx
    pop fs
    pop es
    pop dx
    pop bx
    popf
    ret

%ifdef EMULATOR_TEST
tester: db '86Box', 1, 5
tester_end:
%endif
success_message: db 'A20 before: '
before_digit: db '?', ' (1=on, 0=off). A20 now OFF, alias verified.',13,10
    db 'Run the original failing program now. Reboot between comparisons.',13,10,'$'
failed_message: db 'A20 change failed. Reboot before further tests.',13,10,'$'
refused_message: db 'No change: requires clean real-mode DOS without HIMEM/EMM386.',13,10,'$'
