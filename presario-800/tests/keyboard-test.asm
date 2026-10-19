bits 16
org 0x7C00

%define EBDA_SEG             0x9FC0
%define S_WARM_BOOT          0x003A
%define S_RESET_IDT_LIMIT    0x003B
%define PHASE_LBA            32
%define WORK_BUFFER          0x0500
%define KBC_DATA             0x60
%define KBC_STATUS           0x64
%define KBC_COMMAND          0x64

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
    mov al, 0x01
    jc fail
    jmp 0x0000:stage2

stage_dap:
    db 0x10, 0
    dw 15
    dw stage2, 0
    dq 1

fail:
    out 0x80, al
    mov bl, al
    mov dx, 0x0080
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
    mov al, 0x01
    out dx, al
    mov al, 0x05
    out dx, al
    mov dx, 0x0501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
.halt:
    cli
    hlt
    jmp .halt

times 510 - ($ - $$) db 0
dw 0xAA55

stage2:
    mov al, 0x8F
    out 0x70, al
    in al, 0x84
    in al, 0x71
    test al, al
    mov al, 0x57
    jnz fail
    xor al, al
    out 0x70, al
    ; Recheck every reset phase, including both warm indicators on CPU reset.
%include "memory-check.inc"
%include "bus-check.inc"
%include "fpu-check.inc"
    ; Full-speed state is required after every cold and warm boot phase.
    mov eax, cr0
    test eax, 0x60000000
    mov al, 0x6A
    jnz fail
    out 0xFB, al
    mov al, 5
    out 0xEC, al
    in al, 0xED
    test al, 0xE0
    mov al, 0x6B
    jnz fail
    mov al, 7
    out 0xEC, al
    in al, 0xED
    test al, 8
    mov al, 0x6C
    jz fail
    mov cl, 0x13
.cache_regions:
    mov al, cl
    out 0xEC, al
    in al, 0xED
    cmp al, 0x55
    mov al, 0x6D
    jne fail
    inc cl
    cmp cl, 0x18
    jb .cache_regions
    mov al, 0x18
    out 0xEC, al
    in al, 0xED
    cmp al, 0xAA
    mov al, 0x6D
    jne fail
    out 0xF9, al
    ; A guest-owned observer records completed calls to the real BIOS IRQ1.
    ; This replaces the removed production first-scan diagnostic byte.
    cli
    mov ax, [0x0024]
    mov [cs:old_int09], ax
    mov ax, [0x0026]
    mov [cs:old_int09 + 2], ax
    mov word [0x0024], observed_irq1
    mov word [0x0026], 0
    sti
    mov byte [cs:led_section], 1
    ; Scan/lock cases use Num Off. POST follows the saved boot policy;
    ; normalize the guest through actual key events and LED acknowledgements.
    test byte [0x0417], 0x20
    jz .locks_ready
    mov bl, 0x45
    call inject_scan
    mov bl, 0xC5
    call inject_scan
.locks_ready:
    call read_phase
    mov al, 0x02
    jc fail
    mov al, [WORK_BUFFER]
    cmp al, 8
    ja .bad_phase
    xor ah, ah
    shl ax, 1
    mov bx, ax
    jmp word [cs:phase_table + bx]
.bad_phase:
    mov al, 0x03
    jmp fail

phase0:
    call require_cold_reset_value
    call keyboard_checks
    mov al, 1
    call write_phase
    mov al, 0x10
    jc fail
    mov word [0x0472], 0
    lidt [cs:idtr_07ff]
    jmp 0xF000:0x0000

phase1:
    call require_cold
    call get_reset_idt_limit
    cmp ax, 0x07FF
    mov al, 0x11
    jne fail
    mov al, 2
    call write_phase
    mov al, 0x12
    jc fail
    xor bx, bx
    call raw_reset

phase2:
    call require_cold_reset_value
    mov al, 3
    call write_phase
    mov al, 0x13
    jc fail
    mov bx, 0x0100
    call raw_reset

phase3:
    call require_cold_reset_value
    mov al, 4
    call write_phase
    mov al, 0x14
    jc fail
    mov bx, 0x0001
    call raw_reset

phase4:
    call require_cold_reset_value
    mov al, 5
    call write_phase
    mov al, 0x15
    jc fail
    mov bx, 0x0101
    call raw_reset

phase5:
    call require_warm_reset_value
    cmp word [0x0472], 0
    mov al, 0x16
    jne fail
    mov al, 6
    call write_phase
    mov al, 0x17
    jc fail
    xor bx, bx
    call raw_reset

phase6:
    call require_cold_reset_value
    ; Warm entry must recover from a graphics mode left by a DOS program.
    mov ax, 0x0013
    int 0x10
    mov al, 7
    call write_phase
    mov al, 0x18
    jc fail
    lidt [cs:idtr_07ff]
    call seed_slow_cpu
    call seed_warm_state
    mov bl, 0x1D
    call inject_scan_async
    mov bl, 0x38
    call inject_scan_async
    mov bl, 0xE0
    call inject_scan_async
    mov bl, 0x53
    call inject_scan_async
    mov al, 0x19
    jmp fail

phase7:
phase8:
    mov ah, 0x0F
    int 0x10
    and al, 0x7F
    cmp al, 3
    mov al, 0x72
    jne fail
    cmp word [0x044A], 80
    jne fail
    cmp byte [0x0484], 24
    jne fail
    cmp word [0x0485], 16
    jne fail
    mov ah, 2
    xor bx, bx
    xor dx, dx
    int 0x10
    mov ax, 0x0E56           ; Render V through the newly installed public entry.
    int 0x10
    push es
    mov ax, 0xB800
    mov es, ax
    cmp byte [es:0], 'V'
    mov al, 0x72
    jne fail
    pop es
    push es
    mov ax, 0x2000             ; Cold probe writes here; shadow staging does not.
    mov es, ax
    cmp dword [es:0], 0x31415926
    pop es
    mov al, 0x71
    jne fail
    call require_warm_reentry_value
    cmp word [0x0472], 0
    mov al, 0x1A
    jne fail
    mov ah, 0x02
    int 0x16
    test al, al
    mov al, 0x1B
    jnz fail
    cmp byte [0x0496], 0x10     ; Enhanced-keyboard capability survives reset.
    jne fail
    cmp byte [0x0497], 0
    jne fail
    cmp byte [0x0499], 0
    jne fail
    cmp byte [0x049B], 0
    jne fail
    mov ah, 0x01
    int 0x16
    mov al, 0x1C
    jnz fail
    mov bl, 0x1E
    call inject_scan
    mov ah, 0x00
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x1D
    jne fail
    call read_phase
    mov al, 0x1E
    jc fail
    cmp byte [WORK_BUFFER], 8
    je .passed
    mov al, 8
    call write_phase
    mov al, 0x1F
    jc fail
    lidt [cs:idtr_07ff]
    call seed_warm_state
    mov bl, 0x1D
    call inject_scan_async
    mov bl, 0x38
    call inject_scan_async
    mov bl, 0x53
    call inject_scan_async
    mov al, 0x25
    jmp fail
.passed:
    mov al, 0x66
    jmp fail

require_cold_reset_value:
    call require_cold
    call get_reset_idt_limit
    cmp ax, 0x03FF
    mov al, 0x20
    jne fail
    ret

require_warm_reset_value:
    mov ax, EBDA_SEG
    mov es, ax
    cmp byte [es:S_WARM_BOOT], 1
    mov ax, 0
    mov es, ax
    mov al, 0x21
    jne fail
    call get_reset_idt_limit
    cmp ax, 0x03FF
    mov al, 0x22
    jne fail
    ret

require_warm_reentry_value:
    mov ax, EBDA_SEG
    mov es, ax
    cmp byte [es:S_WARM_BOOT], 1
    mov ax, 0
    mov es, ax
    mov al, 0x21
    jne fail
    call get_reset_idt_limit
    cmp ax, 0x07FF
    mov al, 0x22
    jne fail
    ret

require_cold:
    mov ax, EBDA_SEG
    mov es, ax
    cmp byte [es:S_WARM_BOOT], 0
    mov ax, 0
    mov es, ax
    mov al, 0x23
    jne fail
    ret

get_reset_idt_limit:
    push es
    mov ax, EBDA_SEG
    mov es, ax
    mov ax, [es:S_RESET_IDT_LIMIT]
    pop es
    ret

keyboard_checks:
    mov byte [cs:led_section], 2
    call intercept_checks
    cmp word [cs:old_int09 + 2], 0xF000
    mov al, 0x2D
    jne fail
    cli
    mov al, 0x20
    call guest_command
    call guest_read
    mov dl, al
    sti
    test dl, 0x01
    mov al, 0x2E
    jz fail
    test dl, 0x10
    mov al, 0x2F
    jnz fail
    ; AT protocol must remain selected after runtime arming and warm reset.
    test dl, 0x20
    mov al, 0x27
    jnz fail

    ; Initialization replies must not appear as keys.
    mov ah, 0x01
    int 0x16
    mov al, 0x30
    jnz fail

    ; Status must set and clear the returned ZF and must not consume.
    call status_contrasts
    mov bl, 0x1E
    call inject_scan
    mov bx, [0x041A]
    cmp bx, [0x041C]
    jne .queue_present
    mov al, 0x2C
    jmp fail
.queue_present:
    or ax, 1
    mov ah, 0x01
    int 0x16
    jnz .status1_ready
    mov al, 0x32
    jmp fail
.status1_ready:
    cmp ax, 0x1E61
    mov al, 0x33
    jne fail
    mov ah, 0x11
    int 0x16
    jnz .status11_ready
    mov al, 0x34
    jmp fail
.status11_ready:
    cmp ax, 0x1E61
    mov al, 0x35
    jne fail
    mov ah, 0x10
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x36
    jne fail

    call pending_irq_ownership
    mov byte [cs:check_irq1_owner], 1
    mov bl, 0x1E
    call inject_scan
    cmp byte [cs:check_irq1_owner], 2
    mov al, 0x72
    jne fail
    mov byte [cs:check_irq1_owner], 0
    xor ah, ah
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x72
    jne fail
    mov ah, 1
    int 0x16
    mov al, 0x72
    jnz fail
    ; A missing edge is not a masked, pending IRQ. Disable generation at
    ; the controller for the polling tests, then restore its command byte.
    cli
    mov al, 0x20
    call guest_command
    call guest_read
    mov [cs:poll_command_byte], al
    and al, 0xFE
    mov cl, al
    mov al, 0x60
    call guest_command
    mov al, cl
    call guest_data
    sti
    ; INT 16h must poll controller output when physical IRQ1 is unavailable.
    in al, 0x21
    mov dl, al
    or al, 0x03
    out 0x21, al
    mov al, 0xD2
    call guest_command
    mov al, 0x30
    call guest_data
    call wait_controller_output
    mov ah, 0x01
    int 0x16
    jnz .poll_status_ready
    mov al, 0x5F
    jmp fail
.poll_status_ready:
    cmp ax, 0x3062
    mov al, 0x5F
    jne fail
    mov ah, 0x00
    int 0x16
    cmp ax, 0x3062
    mov al, 0x5F
    jne fail
    ; A second scan must be consumed by the blocking-read polling entry.
    mov al, 0xD2
    call guest_command
    mov al, 0x1E
    call guest_data
    call wait_controller_output
    mov ah, 0x00
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x5F
    jne fail
    mov al, dl
    out 0x21, al

    ; Timer polling must deliver a key without IRQ1 or an INT 16h poll.
    in al, 0x21
    mov dl, al
    or al, 0x02
    out 0x21, al
    mov al, 0xD2
    call guest_command
    mov al, 0x2E
    call guest_data
    mov cx, 4
.timer_poll_wait:
    sti
    hlt
    mov bx, [0x041A]
    cmp bx, [0x041C]
    jne .timer_poll_ready
    loop .timer_poll_wait
    mov al, 0x5E
    jmp fail
.timer_poll_ready:
    mov ah, 0x00
    int 0x16
    cmp ax, 0x2E63
    mov al, 0x5D
    jne fail
    mov al, dl
    out 0x21, al
    cli
    mov al, 0x60
    call guest_command
    mov al, [cs:poll_command_byte]
    call guest_data
    sti

    ; Every declared text key has an independent normal and Shift result.
    mov si, text_cases
.normal_case:
    lodsb
    test al, al
    jz .shift_cases
    mov bl, al
    lodsw
    mov dx, ax
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, dx
    mov al, 0x37
    jne fail
    jmp .normal_case

.shift_cases:
    mov bl, 0x2A
    call inject_scan
    mov si, shift_cases
.shift_case:
    lodsb
    test al, al
    jz .shift_done
    mov bl, al
    lodsw
    mov dx, ax
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, dx
    mov al, 0x38
    jne fail
    jmp .shift_case
.shift_done:
    mov bl, 0xAA
    call inject_scan
    mov ah, 0x02
    int 0x16
    test al, 0x02
    mov al, 0x39
    jnz fail
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x3A
    jne fail

    ; Both sides remain independent for Shift, Ctrl, and Alt.
    mov bl, 0x2A
    call inject_scan
    mov bl, 0x36
    call inject_scan
    mov bl, 0xAA
    call inject_scan
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E41
    mov al, 0x3B
    jne fail
    mov bl, 0xB6
    call inject_scan

    mov bl, 0x1D
    call inject_scan
    mov bl, 0xE0
    call inject_scan
    mov bl, 0x1D
    call inject_scan
    mov bl, 0x9D
    call inject_scan
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E01
    mov al, 0x3C
    jne fail
    mov bl, 0xE0
    call inject_scan
    mov bl, 0x9D
    call inject_scan

    mov bl, 0x38
    call inject_scan
    mov bl, 0xE0
    call inject_scan
    mov bl, 0x38
    call inject_scan
    mov bl, 0xB8
    call inject_scan
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E00
    mov al, 0x3D
    jne fail
    mov bl, 0xE0
    call inject_scan
    mov bl, 0xB8
    call inject_scan

    ; Alt wins over Ctrl for ordinary keys.
    mov bl, 0x1D
    call inject_scan
    mov bl, 0x38
    call inject_scan
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E00
    mov al, 0x3E
    jne fail
    mov bl, 0x9D
    call inject_scan
    mov bl, 0xB8
    call inject_scan

    ; Caps toggles once per physical press and XORs with Shift.
    mov bl, 0x3A
    call inject_scan
    mov bl, 0x3A
    call inject_scan
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E41
    mov al, 0x3F
    jne fail
    mov al, 4
    call require_leds
    mov bl, 0x2A
    call inject_scan
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x40
    jne fail
    mov bl, 0xAA
    call inject_scan
    mov bl, 0xBA
    call inject_scan
    mov bl, 0x3A
    call inject_scan
    mov bl, 0xBA
    call inject_scan

    ; Function, navigation, Pause, PrintScreen, and response filtering.
    call lock_checks
    call reverse_modifiers
    call keypad_operator_checks
    call extended_cases
    mov bl, 0x3B
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x3B00
    mov al, 0x41
    jne fail
    mov bl, 0x57
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x8500
    mov al, 0x42
    jne fail
    mov bl, 0xE0
    call inject_scan
    mov bl, 0x48
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x4800
    mov al, 0x43
    jne fail
    mov si, ignored_sequence
.ignored:
    lodsb
    test al, al
    jz .ignored_done
    mov bl, al
    call inject_scan
    jmp .ignored
.ignored_done:
    call runtime_pause
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x44
    jne fail
    mov ah, 0x01
    int 0x16
    mov al, 0x45
    jnz fail

    ; FIFO keeps duplicates, wraps, and drops only the excess entry.
    mov bl, 0x1E
    call inject_scan
    call inject_scan
    mov bl, 0x30
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x46
    jne fail
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x47
    jne fail
    mov ah, 0
    int 0x16
    cmp ax, 0x3062
    mov al, 0x48
    jne fail

    mov bl, 0x2A
    call inject_scan
    mov cx, 15
.fill:
    mov bl, 0x1E
    call inject_scan
    loop .fill
    mov bl, 0x30
    call inject_scan
    mov bl, 0xAA
    call inject_scan
    mov si, [0x041A]
    mov di, [0x041C]
    mov ah, 0
    int 0x16
    cmp ax, 0x1E41
    mov al, 0x49
    jne fail
    add si, 2
    cmp si, 0x3E
    jb .head_expected
    mov si, 0x1E
.head_expected:
    cmp si, [0x041A]
    jne fail
    cmp di, [0x041C]
    jne fail
    mov bl, 0x30
    call inject_scan
    add di, 2
    cmp di, 0x3E
    jb .tail_expected
    mov di, 0x1E
.tail_expected:
    cmp di, [0x041C]
    mov al, 0x49
    jne fail
    mov cx, 14
.drain:
    mov ah, 0
    int 0x16
    cmp ax, 0x1E41
    mov al, 0x49
    jne fail
    loop .drain
    mov ah, 0
    int 0x16
    cmp ax, 0x3062
    mov al, 0x49
    jne fail
    mov ah, 0x01
    int 0x16
    mov al, 0x4A
    jnz fail
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x4B
    jne fail

    ; A timer IRQ supplies input only after the blocking read begins.
    cli
    mov ax, [0x0020]
    mov [cs:old_int08], ax
    mov ax, [0x0022]
    mov [cs:old_int08 + 2], ax
    mov word [0x0020], delayed_irq
    mov word [0x0022], 0
    mov byte [cs:delay_ticks], 2
    sti
    mov ah, 0
    int 0x16
    cmp ax, 0x2E63
    mov al, 0x4C
    jne fail
    cli
    mov ax, [cs:old_int08]
    mov [0x0020], ax
    mov ax, [cs:old_int08 + 2]
    mov [0x0022], ax
    sti

    ; Delete contrasts must not reset.
    mov si, delete_contrasts
.delete_case:
    lodsb
    test al, al
    jz .delete_done
    mov cl, al
.delete_bytes:
    lodsb
    mov bl, al
    call inject_scan
    loop .delete_bytes
    call drain_one_if_present
    jmp .delete_case
.delete_done:
    ret

drain_one_if_present:
    mov ah, 0x01
    int 0x16
    jz .done
    mov ah, 0x00
    int 0x16
.done:
    ret

; Both status aliases must overwrite either incoming ZF without consuming.
status_contrasts:
    mov si, 0x041A
    mov dx, [si]
    mov cx, 2
.empty_alias:
    mov bh, 0x01
    cmp cx, 2
    je .empty_flags
    mov bh, 0x11
.empty_flags:
    or ax, 1
    mov ah, bh
    int 0x16
    jnz .failed
    xor ax, ax
    mov ah, bh
    int 0x16
    jnz .failed
    cmp dx, [si]
    jne .failed
    loop .empty_alias
    mov bl, 0x1E
    call inject_scan
    mov cx, 2
.available_alias:
    mov bh, 0x01
    cmp cx, 2
    je .available_flags
    mov bh, 0x11
.available_flags:
    xor ax, ax
    mov ah, bh
    int 0x16
    jz .failed
    cmp ax, 0x1E61
    jne .failed
    or ax, 1
    mov ah, bh
    int 0x16
    jz .failed
    cmp ax, 0x1E61
    jne .failed
    cmp dx, [si]
    jne .failed
    loop .available_alias
    mov ah, 0
    int 0x16
    ret
.failed:
    mov al, 0x31
    jmp fail

wait_controller_output:
    push cx
    mov cx, 0xFFFF
.wait:
    in al, KBC_STATUS
    test al, 1
    jnz .done
    loop .wait
    mov al, 0x5F
    jmp fail
.done:
    pop cx
    ret

extended_cases:
    mov si, function_cases
.function:
    lodsw
    test ax, ax
    jz .navigation
    mov bl, al
    mov dh, ah
    xor dl, dl
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, dx
    jne .failed
    jmp .function
.navigation:
    mov dx, 0x4700
.nav:
    mov bl, 0xE0
    call inject_scan
    mov bl, dh
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, dx
    jne .failed
    inc dh
    cmp dh, 0x53
    jbe .nav
    xor cx, cx
.text_state:
    mov si, e0_text_cases
.text:
    lodsw
    test ax, ax
    jz .next_text_state
    mov dx, ax
    mov bl, 0xE0
    call inject_scan
    mov bl, dh
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, dx
    jne .failed
    jmp .text
.next_text_state:
    cmp cl, 2
    je .release_right
    mov bl, 0xAA
    call inject_scan
    mov bl, 0x2A
    test cl, cl
    jz .press_shift
    mov bl, 0x36
.press_shift:
    call inject_scan
    inc cl
    jmp .text_state
.release_right:
    mov bl, 0xB6
    call inject_scan
.done:
    ret
.failed:
    mov al, 0x43
    jmp fail

keypad_operator_checks:
    mov si, keypad_operator_cases
.case:
    lodsb
    test al, al
    jz .done
    xor ch, ch
    mov cl, al
.scan:
    lodsb
    mov bl, al
    call inject_scan
    loop .scan
    lodsw
    mov dx, ax
    mov ah, 0
    int 0x16
    cmp ax, dx
    jne .failed
    jmp .case
.done:
    ret
.failed:
    mov al, 0x3E
    jmp fail

reverse_modifiers:
    mov si, reverse_modifier_cases
.case:
    lodsb
    test al, al
    jz .done
    xor ch, ch
    mov cl, al
.scan:
    lodsb
    mov bl, al
    call inject_scan
    loop .scan
    lodsb
    mov dl, al
    mov ah, 2
    int 0x16
    and al, 0x0F
    cmp al, dl
    jne .failed
    jmp .case
.done:
    ret
.failed:
    mov al, 0x3E
    jmp fail

delayed_irq:
    push ax
    push dx
    dec byte [cs:delay_ticks]
    jnz .eoi
    mov dx, KBC_COMMAND
.wait_command:
    in al, dx
    test al, 2
    jnz .wait_command
    mov al, 0xD2
    out dx, al
.wait_data:
    in al, dx
    test al, 2
    jnz .wait_data
    mov al, 0x2E
    out KBC_DATA, al
.eoi:
    mov al, 0x20
    out 0x20, al
    pop dx
    pop ax
    iret

; Wait for real keyboard ACKs to the BIOS LED transaction. Never inject an
; ACK. No controller writes may race the EDh/data pair in this test driver.
require_leds:
    mov [cs:led_expected], al
    push cx
    mov cx, 36
.wait:
    cmp byte [0x0499], 0
    jne .tick
    cmp [0x049B], al
    je .done
.tick:
    sti
    hlt
    loop .wait
    mov al, [cs:led_section]
    shl al, 3
    add al, 0x40
    or al, [cs:led_expected] ; Section plus lamp mask, below host exit limit.
    jmp fail
.done:
    pop cx
    ret

lock_checks:
    mov byte [cs:led_section], 3
    ; Caps is now off. Num Lock changes keypad output; Shift reverses it.
    xor al, al
    call require_leds
    mov bl, 0x45
    call inject_scan
    call inject_scan
    mov al, 2
    call require_leds
    mov bl, 0x47
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x4737
    mov al, 0x29
    jne fail
    mov bl, 0x2A
    call inject_scan
    mov bl, 0x47
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x4700
    mov al, 0x2A
    jne fail
    mov bl, 0xAA
    call inject_scan
    mov bl, 0xC5
    call inject_scan
    mov bl, 0x45
    call inject_scan
    mov bl, 0xC5
    call inject_scan
    xor al, al
    call require_leds
    mov bl, 0x47
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x4700
    mov al, 0x2B
    jne fail
    mov bl, 0x2A
    call inject_scan
    mov bl, 0x47
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x4737
    mov al, 0x2B
    jne fail
    mov bl, 0xAA
    call inject_scan
    ; Scroll Lock is a BDA/application state, not a global video pause.
    mov bl, 0x46
    call inject_scan
    call inject_scan
    mov al, 1
    call require_leds
    mov ah, 2
    int 0x16
    test al, 0x10
    mov al, 0x26
    jz fail
    mov bl, 0xC6
    call inject_scan
    mov bl, 0x46
    call inject_scan
    mov bl, 0xC6
    call inject_scan
    xor al, al
    call require_leds
    call led_interleaving
    ret

; Freeze a real EDh exchange after its first ACK. Return the original PIC
; mask in AL; IRQ1 stays live while IRQ0 cannot send the pending option byte.
wait_led_data:
    mov cx, 36
.wait:
    cli
    cmp byte [0x0499], 3
    je .ready
    sti
    hlt
    loop .wait
    mov al, 0x78
    jmp fail
.ready:
    in al, 0x21
    mov ah, al
    or al, 1
    out 0x21, al
    mov al, ah
    sti
    ret

seed_slow_cpu:
    ; A warm restart must actively restore speed/cache controls, not merely
    ; inherit a fast setting from the previous boot. Keep refresh bits intact.
    wbinvd
    mov eax, cr0
    or eax, 0x6000002E         ; Also poison MP/EM/TS/NE before warm POST.
    mov cr0, eax
    wbinvd
    out 0xFB, al
    out 0xF4, al
    mov al, 5
    out 0xEC, al
    in al, 0xED
    or al, 0xE0
    out 0xED, al
    mov al, 7
    out 0xEC, al
    in al, 0xED
    and al, 0xF7
    out 0xED, al
    mov al, 0x18
    out 0xEC, al
    xor al, al
    out 0xED, al
    out 0xF9, al
    ret

seed_warm_state:
    mov byte [cs:led_section], 5
    push es
    mov ax, 0x2000
    mov es, ax
    mov dword [es:0], 0x31415926
    pop es
    mov bl, 0x1E
    call inject_scan
    mov bl, 0x45
    call inject_scan
    call wait_led_data
    mov bl, 0xC5
    call inject_scan_async
    ; Leave unread A, Num Lock, and an acknowledged command awaiting data.
    ret

led_interleaving:
    mov byte [cs:led_section], 4
    ; Deliver both real LED ACKs while an E0 prefix is retained.
    in al, 0x21
    push ax
    or al, 1
    out 0x21, al
    mov bl, 0x45
    call inject_scan_async
    mov bl, 0xC5
    call inject_scan_async
    mov bl, 0xE0
    call inject_scan_async
    pop ax
    out 0x21, al
    mov al, 2
    call require_leds
    mov bl, 0x48
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x4800 ; Without E0 this becomes Num Lock keypad '8'.
    jne .failed
    mov bl, 0x45
    call inject_scan
    mov bl, 0xC5
    call inject_scan
    xor al, al
    call require_leds

    ; The same command replies must not consume any E1/Pause tail byte.
    mov byte [cs:led_section], 6
    in al, 0x21
    push ax
    or al, 1
    out 0x21, al
    mov bl, 0x45
    call inject_scan_async
    mov bl, 0xC5
    call inject_scan_async
    pop ax
    out 0x21, al
    call runtime_pause
    mov al, 2
    call require_leds
    mov bl, 0x1E
    call inject_scan
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    jne .failed
    mov ah, 1
    int 0x16
    jnz .failed
    mov bl, 0x45
    call inject_scan
    mov bl, 0xC5
    call inject_scan
    xor al, al
    call require_leds

    ; Change the desired lock state and accept text before the old option
    ; byte is sent. The owner must finish, then apply the newer state.
    mov byte [cs:led_section], 7
    mov bl, 0x45
    call inject_scan
    call wait_led_data
    push ax
    mov bl, 0x30
    call inject_scan_async
    mov bl, 0xC5
    call inject_scan_async
    mov bl, 0x45
    call inject_scan_async
    mov bl, 0xC5
    call inject_scan_async
    pop ax
    out 0x21, al
    xor al, al
    call require_leds
    mov ah, 0
    int 0x16
    cmp ax, 0x3062
    jne .failed
    ret
.failed:
    mov al, 0x79
    jmp fail

; A latched IRQ1 owns its scan, even while masked. Neither the timer nor
; INT16 may consume it and leave a stale scan for the eventual real IRQ.
pending_irq_ownership:
    cli
    in al, 0x21
    push ax
    or al, 2
    out 0x21, al
    mov al, 0xD2
    call guest_command
    mov al, 0x1E
    call guest_data
    call wait_controller_output
    mov al, 0x0A
    out 0x20, al
    in al, 0x20
    test al, 2
    mov al, 0x5C
    jz fail
    mov cx, 2
.timer:
    sti
    hlt
    cli
    mov bx, [0x041A]
    cmp bx, [0x041C]
    mov al, 0x5C
    jne fail
    loop .timer
    mov ah, 1
    int 0x16
    mov al, 0x5C
    jnz fail
    in al, KBC_STATUS
    test al, 1
    mov al, 0x5C
    jz fail
    pop ax
    out 0x21, al
    sti
    mov ah, 0
    int 0x16
    cmp ax, 0x1E61
    mov al, 0x5C
    jne fail
    mov ah, 1
    int 0x16
    mov al, 0x5C
    jnz fail
    ret
poll_command_byte: db 0

; Check the raw INT15/AH4F contract before all normal keyboard/reset tests.
intercept_checks:
    cli
    mov eax, [0x0054]
    mov [cs:old_int15], eax
    mov word [0x0054], scan_intercept
    mov word [0x0056], 0
    sti
    mov bl, 0x1E               ; Hook replaces A with B.
    call inject_scan
    mov ah, 1
    int 0x16
    jz .failed
    cmp ax, 0x3062
    jne .failed
    xor ah, ah
    int 0x16
    ; CF-clear must suppress a full Ctrl+Alt+E0/Delete, not reset or queue it.
    mov bl, 0x1D
    call inject_scan
    mov bl, 0x38
    call inject_scan
    mov bl, 0xE0
    call inject_scan
    mov bl, 0x53
    call inject_scan
    cmp byte [cs:delete_intercepted], 1
    jne .failed
    test byte [0x0496], 2
    jnz .failed
    mov ah, 1
    int 0x16
    jnz .failed
    mov bl, 0x9D
    call inject_scan
    mov bl, 0xB8
    call inject_scan
    cli
    mov eax, [cs:old_int15]
    mov [0x0054], eax
    sti
    ret
.failed:
    mov al, 0x70
    jmp fail

scan_intercept:
    cmp ah, 0x4F
    jne .chain
    push bp
    mov bp, sp
    test word [ss:bp + 6], 1  ; BIOS must provide CF-set default acceptance.
    jz intercept_checks.failed
    cmp al, 0x53
    je .consume
    cmp al, 0x1E
    jne .accept
    mov al, 0x30
.accept:
    pop bp
    iret
.consume:
    inc byte [cs:delete_intercepted]
    and word [ss:bp + 6], 0xFFFE
    pop bp
    iret
.chain:
    jmp far [cs:old_int15]
old_int15: dd 0
delete_intercepted: db 0

inject_scan:
    push ax
    mov al, [0x0417]
    shr al, 4
    and al, 7
    call require_leds
    pop ax
inject_scan_async:
    push ax
    push cx
    push dx
    push si
    ; Observe real handler completion, not a BIOS debug byte. Mask IRQ0
    ; so this helper proves IRQ1 delivery rather than the timer fallback.
    in al, 0x21
    push ax
    or al, 1
    out 0x21, al
    mov si, [cs:irq1_count]
    mov dx, KBC_COMMAND
    mov cx, 0xFFFF
.wait_command:
    in al, dx
    test al, 2
    jz .command_ready
    loop .wait_command
    mov al, 0x60
    jmp fail
.command_ready:
    mov al, 0xD2
    out dx, al
    mov cx, 0xFFFF
.wait_data:
    in al, dx
    test al, 2
    jz .data_ready
    loop .wait_data
    mov al, 0x61
    jmp fail
.data_ready:
    mov al, bl
    out KBC_DATA, al
    mov cx, 0xFFFF
.wait_consumed:
    sti
    nop
    cmp si, [cs:irq1_count]
    jne .done
    loop .wait_consumed
    mov al, 0x62
    jmp fail
.done:
    pop ax
    out 0x21, al
    pop si
    pop dx
    pop cx
    pop ax
    ret

raw_reset:
    cli
    test bh, 1
    jz .clear_marker
    mov word [0x0472], 0x1234
    jmp .marker_ready
.clear_marker:
    mov word [0x0472], 0
.marker_ready:
    mov al, 0xAD
    call guest_command
    call guest_drain
    mov al, 0x20
    call guest_command
    call guest_read
    test bl, 1
    jz .clear_flag
    or al, 0x04
    jmp .flag_ready
.clear_flag:
    and al, 0xFB
.flag_ready:
    mov cl, al
    mov al, 0x60
    call guest_command
    mov al, cl
    call guest_data
    ; A stale CMOS resume request must not redirect a SYS-clear cold entry.
    test bl, 1
    jnz .shutdown_seeded
    mov word [0x0467], .unexpected_resume
    mov word [0x0469], cs
    mov al, 0x8F
    out 0x70, al
    in al, 0x84
    mov al, 0x0A
    out 0x71, al
.shutdown_seeded:
    lidt [cs:idtr_07ff]
    mov al, 0xFE
    call guest_command
.wait_reset:
    sti
    hlt
    jmp .wait_reset
.unexpected_resume:
    mov al, 0x57
    jmp fail

guest_command:
    push ax
    call guest_input_clear
    pop ax
    jc .failed
    out KBC_COMMAND, al
    ret
.failed:
    mov al, 0x64
    jmp fail

guest_data:
    push ax
    call guest_input_clear
    pop ax
    jc guest_command.failed
    out KBC_DATA, al
    ret

guest_input_clear:
    push cx
    mov cx, 0xFFFF
.wait:
    in al, KBC_STATUS
    test al, 2
    jz .ready
    loop .wait
    stc
    jmp .done
.ready:
    clc
.done:
    pop cx
    ret

guest_read:
    push cx
    mov cx, 0xFFFF
.wait:
    in al, KBC_STATUS
    test al, 1
    jnz .ready
    loop .wait
    pop cx
    mov al, 0x65
    jmp fail
.ready:
    in al, KBC_DATA
    pop cx
    ret

guest_drain:
    push cx
    mov cx, 0xFFFF
.next:
    in al, KBC_STATUS
    test al, 1
    jz .done
    in al, KBC_DATA
    loop .next
.done:
    pop cx
    ret

read_phase:
    mov word [phase_dap + 2], 1
    mov word [phase_dap + 4], WORK_BUFFER
    mov word [phase_dap + 6], 0
    mov dword [phase_dap + 8], PHASE_LBA
    mov dword [phase_dap + 12], 0
    mov si, phase_dap
    mov ax, 0x4200
    mov dl, 0x80
    int 0x13
    ret

write_phase:
    push ax
    mov di, WORK_BUFFER
    xor ax, ax
    mov cx, 256
    rep stosw
    pop ax
    mov [WORK_BUFFER], al
    mov word [phase_dap + 2], 1
    mov word [phase_dap + 4], WORK_BUFFER
    mov word [phase_dap + 6], 0
    mov dword [phase_dap + 8], PHASE_LBA
    mov dword [phase_dap + 12], 0
    mov si, phase_dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    ret

phase_table:
    dw phase0, phase1, phase2, phase3, phase4, phase5, phase6, phase7, phase8

idtr_07ff:
    dw 0x07FF
    dd 0

observed_irq1:
    cmp byte [cs:check_irq1_owner], 1
    jne .chain
    push ax
    push bx
    mov byte [cs:check_irq1_owner], 2
    mov al, 0x0A
    out 0x20, al
    in al, 0x20
    test al, 2                 ; The real interrupt acknowledged the pending edge.
    mov al, 0x72
    jnz fail
    mov ah, 1
    int 0x16                  ; Must not recursively consume this IRQ's scan.
    mov al, 0x72
    jnz fail
    ; Let a real higher-priority timer interrupt exercise its polling path too.
    in al, 0x21
    push ax
    and al, 0xFE               ; inject_scan masks IRQ0 until its IRQ1 completes.
    out 0x21, al
    mov bx, [0x046C]
.timer:
    sti
    hlt
    cli
    cmp bx, [0x046C]
    je .timer
    mov bx, [0x041A]
    cmp bx, [0x041C]
    mov al, 0x72
    jne fail
    in al, KBC_STATUS
    test al, 1
    mov al, 0x72
    jz fail
    mov al, 0x0B
    out 0x20, al
    in al, 0x20
    test al, 2                 ; Timer EOI must not retire the active IRQ1.
    mov al, 0x72
    jz fail
    mov al, 0x0A
    out 0x20, al
    pop ax
    out 0x21, al
    pop bx
    pop ax
.chain:
    pushf
    call far [cs:old_int09]
    inc word [cs:irq1_count]
    iret

old_int09: dd 0
irq1_count: dw 0
check_irq1_owner: db 0
old_int08: dd 0
delay_ticks: db 0
led_section: db 0
led_expected: db 0

; IRQ1 suspends the caller. An independent timer supplies the remaining
; Pause bytes, a release, an ACK, and finally a consumed resume make.
runtime_pause:
    pushad
    cli
    mov eax, [0x0070]
    mov [cs:pause_old_int1c], eax
    mov word [0x0070], runtime_pause_tick
    mov word [0x0072], 0
    mov byte [cs:pause_ticks], 0
    mov al, 0xD2
    call guest_command
    mov al, 0xE1
    call guest_data
    call wait_controller_output
    sti
    nop
    cmp byte [cs:pause_ticks], 8
    mov al, 0x75
    jne fail
    mov ah, 1
    int 0x16
    mov al, 0x75
    jnz fail
    cli
    mov eax, [cs:pause_old_int1c]
    mov [0x0070], eax
    sti
    popad
    ret

runtime_pause_tick:
    push ax
    push bx
    push ds
    xor ax, ax
    mov ds, ax
    cmp byte [cs:pause_ticks], 8
    jae .done
    cmp byte [cs:pause_ticks], 0
    jne .started
    cmp byte [0x04A7], 1
    jne .done
.started:
    cmp byte [0x04A7], 1
    mov al, 0x75
    jne fail
    ; Let real LED replies finish before injecting another controller byte.
    cmp byte [0x0499], 2
    je .done
    cmp byte [0x0499], 4
    je .done
    in al, KBC_STATUS
    test al, 3
    jnz .done
    inc byte [cs:pause_ticks]
    xor bx, bx
    mov bl, [cs:pause_ticks]
    mov al, 0xD2
    call guest_command
    mov al, [cs:pause_events + bx - 1]
    call guest_data
.done:
    pop ds
    pop bx
    pop ax
    iret

pause_old_int1c: dd 0
pause_ticks: db 0
pause_events: db 0x1D,0x45,0xE1,0x9D,0xC5,0x9E,0xFA,0x1E

phase_dap:
    db 0x10, 0
    dw 1
    dw WORK_BUFFER, 0
    dq PHASE_LBA

text_cases:
    db 0x01
    dw 0x011B
    db 0x02
    dw 0x0231
    db 0x03
    dw 0x0332
    db 0x04
    dw 0x0433
    db 0x05
    dw 0x0534
    db 0x06
    dw 0x0635
    db 0x07
    dw 0x0736
    db 0x08
    dw 0x0837
    db 0x09
    dw 0x0938
    db 0x0A
    dw 0x0A39
    db 0x0B
    dw 0x0B30
    db 0x0C
    dw 0x0C2D
    db 0x0D
    dw 0x0D3D
    db 0x0E
    dw 0x0E08
    db 0x0F
    dw 0x0F09
    db 0x10
    dw 0x1071
    db 0x11
    dw 0x1177
    db 0x12
    dw 0x1265
    db 0x13
    dw 0x1372
    db 0x14
    dw 0x1474
    db 0x15
    dw 0x1579
    db 0x16
    dw 0x1675
    db 0x17
    dw 0x1769
    db 0x18
    dw 0x186F
    db 0x19
    dw 0x1970
    db 0x1A
    dw 0x1A5B
    db 0x1B
    dw 0x1B5D
    db 0x1C
    dw 0x1C0D
    db 0x1E
    dw 0x1E61
    db 0x1F
    dw 0x1F73
    db 0x20
    dw 0x2064
    db 0x21
    dw 0x2166
    db 0x22
    dw 0x2267
    db 0x23
    dw 0x2368
    db 0x24
    dw 0x246A
    db 0x25
    dw 0x256B
    db 0x26
    dw 0x266C
    db 0x27
    dw 0x273B
    db 0x28
    dw 0x2827
    db 0x29
    dw 0x2960
    db 0x2B
    dw 0x2B5C
    db 0x2C
    dw 0x2C7A
    db 0x2D
    dw 0x2D78
    db 0x2E
    dw 0x2E63
    db 0x2F
    dw 0x2F76
    db 0x30
    dw 0x3062
    db 0x31
    dw 0x316E
    db 0x32
    dw 0x326D
    db 0x33
    dw 0x332C
    db 0x34
    dw 0x342E
    db 0x35
    dw 0x352F
    db 0x37
    dw 0x372A
    db 0x39
    dw 0x3920
    db 0

shift_cases:
    db 0x02
    dw 0x0221
    db 0x03
    dw 0x0340
    db 0x04
    dw 0x0423
    db 0x05
    dw 0x0524
    db 0x06
    dw 0x0625
    db 0x07
    dw 0x075E
    db 0x08
    dw 0x0826
    db 0x09
    dw 0x092A
    db 0x0A
    dw 0x0A28
    db 0x0B
    dw 0x0B29
    db 0x0C
    dw 0x0C5F
    db 0x0D
    dw 0x0D2B
    db 0x10
    dw 0x1051
    db 0x11
    dw 0x1157
    db 0x12
    dw 0x1245
    db 0x13
    dw 0x1352
    db 0x14
    dw 0x1454
    db 0x15
    dw 0x1559
    db 0x16
    dw 0x1655
    db 0x17
    dw 0x1749
    db 0x18
    dw 0x184F
    db 0x19
    dw 0x1950
    db 0x1A
    dw 0x1A7B
    db 0x1B
    dw 0x1B7D
    db 0x1E
    dw 0x1E41
    db 0x1F
    dw 0x1F53
    db 0x20
    dw 0x2044
    db 0x21
    dw 0x2146
    db 0x22
    dw 0x2247
    db 0x23
    dw 0x2348
    db 0x24
    dw 0x244A
    db 0x25
    dw 0x254B
    db 0x26
    dw 0x264C
    db 0x27
    dw 0x273A
    db 0x28
    dw 0x2822
    db 0x29
    dw 0x297E
    db 0x2B
    dw 0x2B7C
    db 0x2C
    dw 0x2C5A
    db 0x2D
    dw 0x2D58
    db 0x2E
    dw 0x2E43
    db 0x2F
    dw 0x2F56
    db 0x30
    dw 0x3042
    db 0x31
    dw 0x314E
    db 0x32
    dw 0x324D
    db 0x33
    dw 0x333C
    db 0x34
    dw 0x343E
    db 0x35
    dw 0x353F
    db 0x37
    dw 0x372A
    db 0

ignored_sequence:
    db 0xFA,0xFE
    db 0x54,0xD4
    db 0x38,0x54,0xD4,0xB8
    db 0xE0,0xC8
    db 0xE0,0x2A,0xE0,0x37,0xE0,0xB7,0xE0,0xAA
    db 0

delete_contrasts:
    db 1, 0x53
    db 3, 0x1D,0x53,0x9D
    db 3, 0x38,0x53,0xB8
    db 4, 0x1D,0x9D,0x38,0x53
    db 5, 0x1D,0x38,0xD3,0x9D,0xB8
    db 2, 0xE0,0x53
    db 4, 0x1D,0xE0,0x53,0x9D
    db 4, 0x38,0xE0,0x53,0xB8
    db 5, 0x1D,0x9D,0x38,0xE0,0x53
    db 6, 0x1D,0x38,0xE0,0xD3,0x9D,0xB8
    db 0

function_cases:
    dw 0x3B3B,0x3C3C,0x3D3D,0x3E3E,0x3F3F,0x4040
    dw 0x4141,0x4242,0x4343,0x4444,0x8557,0x8658,0
e0_text_cases:
    dw 0x1C0D,0x352F,0
keypad_operator_cases:
    db 1,0x4A
    dw 0x4A2D
    db 1,0x4E
    dw 0x4E2B
    db 3,0x2A,0x4A,0xAA
    dw 0x4A2D
    db 3,0x2A,0x4E,0xAA
    dw 0x4E2B
    db 3,0x1D,0x4A,0x9D
    dw 0x4A2D
    db 3,0x1D,0x4E,0x9D
    dw 0x4E2B
    db 3,0x38,0x4A,0xB8
    dw 0x4A00
    db 3,0x38,0x4E,0xB8
    dw 0x4E00
    db 5,0x1D,0x38,0x4A,0x9D,0xB8
    dw 0x4A00
    db 5,0x1D,0x38,0x4E,0x9D,0xB8
    dw 0x4E00
    db 0
reverse_modifier_cases:
    db 3,0x2A,0x36,0xB6, 2
    db 1,0xAA, 0
    db 5,0x1D,0xE0,0x1D,0xE0,0x9D, 4
    db 1,0x9D, 0
    db 5,0x38,0xE0,0x38,0xE0,0xB8, 8
    db 1,0xB8, 0
    db 0

times 16 * 512 - ($ - $$) db 0
