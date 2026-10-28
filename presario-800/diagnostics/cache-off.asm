; Diagnostic only: disable the 486 L1 cache until reboot. No disk writes.
; Keep the fast CPU clock, chipset cache policy, and bus timing unchanged.
bits 16
org 0x100
start:
    smsw ax
    test al, 1
    jnz .protected
%ifdef EXPECT_PROTECTED
    jmp test_failed
%endif
    mov dx, before
    call print
    mov eax, cr0
    mov [saved_cr0], eax
    call hex32
    mov dx, regions
    call print
    pushf
    cli
    out 0xFB, al
    mov cl, 0x13
.region:
    mov al, cl
    out 0xEC, al
    in al, 0xED
    movzx si, cl
    mov [si + cache_regions - 0x13], al
    inc cl
    cmp cl, 0x19
    jb .region
    out 0xF9, al
    popf
    mov si, cache_regions
    mov cx, 6
.show:
    lodsb
    call hex8
    mov dl, ' '
    call character
    loop .show
    pushf
    cli
    wbinvd
    mov eax, cr0
    or eax, 0x60000000
    mov cr0, eax
    wbinvd
    popf
    mov dx, after
    call print
    mov eax, cr0
    call hex32
    mov dx, disabled
    call print
%ifdef EMULATOR_TEST
    mov eax, cr0
    mov edx, [saved_cr0]
    or edx, 0x60000000
    cmp eax, edx
    jne test_failed
    ; Restore the test VM; the normal utility leaves caching off until reset.
    pushf
    cli
    wbinvd
    mov eax, [saved_cr0]
    mov cr0, eax
    popf
    jmp test_passed
%endif
    mov ax, 0x4C00
    int 0x21
.protected:
    mov dx, refused
    call print
%ifdef EMULATOR_TEST
%ifdef EXPECT_PROTECTED
    jmp test_passed
%else
    jmp test_failed
%endif
%endif
    mov ax, 0x4C01
    int 0x21

print:
    mov ah, 9
    int 0x21
    ret
hex32:
    pushad
    mov cx, 4
.byte:
    rol eax, 8
    call hex8
    loop .byte
    popad
    ret
hex8:
    pushad
    mov bl, al
    shr al, 4
    call .digit
    mov al, bl
    and al, 15
    call .digit
    popad
    ret
.digit:
    add al, '0'
    cmp al, '9'
    jbe .emit
    add al, 7
.emit:
    mov dl, al
character:
    push ax
    mov ah, 2
    int 0x21
    pop ax
    ret

%ifdef EMULATOR_TEST
test_failed:
    mov bl, 0x68
    jmp test_exit
test_passed:
    mov bl, 0x67
test_exit:
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
tester: db '86Box',1,5
tester_end:
%endif
before: db 'CR0 before: $'
regions: db 13,10,'Cache regions 13..18: $'
after: db 13,10,'CR0 after:  $'
disabled: db 13,10,'L1 cache OFF until reboot. CPU clock and bus settings unchanged.',13,10,'$'
refused: db 'No change: protected/V86 mode. Boot clean DOS without EMM386.',13,10,'$'
saved_cr0: dd 0
cache_regions: times 6 db 0
