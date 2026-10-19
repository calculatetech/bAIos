; Cold/warm x87 state, arithmetic, and real IRQ13 -> BIOS -> INT02 delivery.
; Runs before an OS or extender can repair the BIOS state. Failure code 56h.
    pushf
    cli
    mov eax, cr0
    test eax, 0x2E
    mov al, 0x56
    jnz fail
    int 0x11
    test ax, 2
    mov al, 0x56
    jz fail
    in al, 0xA1
    test al, 0x20
    mov al, 0x56
    jnz fail
    in al, 0x21
    test al, 4
    mov al, 0x56
    jnz fail
    fnstsw ax
    test ax, ax
    mov al, 0x56
    jnz fail
    fnstcw [cs:fpu_check_word]
    cmp word [cs:fpu_check_word], 0x037F
    jne fail
    fild word [cs:fpu_check_six]
    fild word [cs:fpu_check_seven]
    fmulp st1, st0
    fistp word [cs:fpu_check_word]
    fwait
    cmp word [cs:fpu_check_word], 42
    jne fail

    mov eax, [0x0008]
    mov [cs:fpu_check_old02], eax
    mov word [0x0008], fpu_check_int02
    mov word [0x000A], cs
    mov byte [cs:fpu_check_irqs], 0
    fnstcw [cs:fpu_check_word]
    and word [cs:fpu_check_word], 0xFFFB ; Unmask divide-by-zero only.
    fldcw [cs:fpu_check_word]
    fld1
    fldz
    fdivp st1, st0
    mov dx, [0x046C]
    sti
fpu_check_wait:
    cmp byte [cs:fpu_check_irqs], 1
    je fpu_check_delivered
    mov ax, [0x046C]
    sub ax, dx
    cmp ax, 9
    mov al, 0x56
    jae fail
    jmp fpu_check_wait
fpu_check_delivered:
    cli
    fninit
    mov eax, [cs:fpu_check_old02]
    mov [0x0008], eax
    mov al, 0x0B
    out 0xA0, al
    in al, 0xA0
    test al, 0x20               ; BIOS must EOI IRQ13, not just clear x87.
    mov al, 0x56
    jnz fail
    mov al, 0x0B
    out 0x20, al
    in al, 0x20
    test al, 4
    mov al, 0x56
    jnz fail
    popf
    jmp fpu_check_done
fpu_check_int02:
    inc byte [cs:fpu_check_irqs]
    fnclex
    iret
fpu_check_word: dw 0
fpu_check_six: dw 6
fpu_check_seven: dw 7
fpu_check_old02: dd 0
fpu_check_irqs: db 0
fpu_check_done:
