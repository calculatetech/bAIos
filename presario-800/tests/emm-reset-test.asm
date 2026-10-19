; Run only on a disposable DOS/HIMEM/EMM386 VHD made by memory-fixture.py.
; First boot injects real IRQ1 Ctrl+Alt+Del. Second boot must remain stable.
bits 16
org 0x100

start:
%ifdef EXPECTED_NUMLOCK
    call check_numlock
%endif
    smsw ax
    test ax, 1                  ; Require EMM386, not an accidental clean boot.
    mov al, 0x6A
    jz exit
    mov dx, marker
    mov ax, 0x3D00
    int 0x21
    jc .first
    mov bx, ax
    mov dx, phase
    mov cx, 1
    mov ah, 0x3F
    int 0x21
    jc io_error
    cmp ax, 1
    jne io_error
    mov ah, 0x3E
    int 0x21
    jc io_error
    cmp byte [phase], 1
    mov al, 0x69                ; A second spontaneous reset is a failure.
    jne exit
    mov byte [phase], 2
    call save_phase
    xor ax, ax
    mov es, ax
    test byte [es:0x0417], 0x0F
    mov al, 0x6B
    jnz exit
    mov bx, [es:0x046C]
.stable:
    sti
    hlt
    mov ax, [es:0x046C]
    sub ax, bx
    cmp ax, 91                 ; Five seconds after DOS/EMM386 reload.
    jb .stable
%ifdef EXPECTED_NUMLOCK
    call check_numlock
%endif
    mov al, 0x67
    jmp exit
.first:
    cmp ax, 2                  ; Only file-not-found means first boot.
    jne io_error
    mov byte [phase], 1
    call save_phase
    mov ax, 0x3509
    int 0x21
    mov [old_irq1], bx
    mov [old_irq1 + 2], es
    mov dx, observed_irq1
    mov ax, 0x2509
    int 0x21
    mov bl, 0x1D
    call inject
    mov bl, 0x38
    call inject
%ifndef KEYPAD_DELETE
    mov bl, 0xE0
    call inject
%endif
    mov bl, 0x53
    call inject
    mov al, 0x6C                ; Delete must not return to the DOS caller.
    jmp exit

save_phase:
    mov dx, marker
    xor cx, cx
    mov ah, 0x3C
    int 0x21
    jc io_error
    mov bx, ax
    mov dx, phase
    mov cx, 1
    mov ah, 0x40
    int 0x21
    jc io_error
    cmp ax, 1
    jne io_error
    mov ah, 0x3E
    int 0x21
    jc io_error
    mov ah, 0x0D               ; Flush DOS before leaving it via warm POST.
    int 0x21
    ret
io_error:
    mov al, 0x6D
    jmp exit

inject:
    in al, 0x21
    push ax
    or al, 1                   ; Require IRQ1, not the BIOS timer fallback.
    out 0x21, al
    mov si, [cs:irq_count]
    call input_clear
    mov al, 0xD2
    out 0x64, al
    call input_clear
    mov al, bl
    out 0x60, al
    mov ecx, 0x100000
.wait:
    sti
    nop
    cmp si, [cs:irq_count]
    jne .done
    dec ecx
    jnz .wait
    mov al, 0x6E
    jmp exit
.done:
    pop ax
    out 0x21, al
    ret
input_clear:
    mov ecx, 0x100000
.wait:
    in al, 0x64
    test al, 2
    jz .done
    dec ecx
    jnz .wait
    mov al, 0x6F
    jmp exit
.done:
    ret
observed_irq1:
    pushf
    call far [cs:old_irq1]
    inc word [cs:irq_count]
    iret

exit:
    mov bl, al
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

marker: db 'C:\RESET.CNT', 0
phase: db 0
old_irq1: dd 0
irq_count: dw 0

%ifdef EXPECTED_NUMLOCK
check_numlock:
    push es
    xor ax, ax
    mov es, ax
    mov al, [es:0x0417]
    and al, 0x20
    cmp al, EXPECTED_NUMLOCK * 0x20
    jne .bad
    mov al, [es:0x049B]         ; Real keyboard LED ACK state, not desired state.
    and al, 2
    cmp al, EXPECTED_NUMLOCK * 2
    jne .bad
    pop es
    ret
.bad:
    mov al, 0x70
    jmp exit
%endif
