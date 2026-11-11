int08:
    push ax
    push ds
    mov ax, 0x0040
    mov ds, ax
    inc word [0x006C]
    jnz .rollover
    inc word [0x006E]
.rollover:
    cmp dword [0x006C], 0x001800B0
    jb .eoi
    mov dword [0x006C], 0
    mov byte [0x0070], 1
.eoi:
    mov al, 0x60               ; Specific IRQ0 EOI; polling never owns IRQ0.
    out 0x20, al
    ; A polled Pause may wait inside IRQ1. IRQ0 must no longer block the
    ; lower-priority keyboard interrupt that supplies the resume key.
    ; A masked IRQ1 may belong to an OS keyboard transaction. Do not steal
    ; its scan byte or send an LED command from the background timer.
    in al,0x21
    test al,2
    jnz .keyboard_owned
    ; Runtime keyboard drivers own scan delivery, even before their virtual
    ; IRQ is pending. Keep fallback scans in POST and explicit INT16 reads.
    cmp byte [KB_POST_STATE],0
    je .keyboard_leds
    call keyboard_poll
.keyboard_leds:
    call keyboard_led_tick
.keyboard_owned:
    call floppy_motor_tick
    ; Logitech 6.23 waits on INT1Ch during startup calibration (765Ah).
    ; Preserve the interrupted program across the installed timer hook.
    pushad
    push es
    push fs
    push gs
    int 0x1C
    cli
    pop gs
    pop fs
    pop es
    popad
    pop ds
    pop ax
    iret
