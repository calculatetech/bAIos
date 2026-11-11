    pushf
    cli
    pushad
    push ds
    call load_bios_state
    mov ax, 0x40
    mov ds, ax
    and byte [KB_FLAGS], 0xDF
    cmp byte [fs:C_NUMLOCK], 0
    je .led
    or byte [KB_FLAGS], 0x20
.led:
    mov byte [KB_LED_APPLIED], 0xFF
    cmp byte [KB_LED_PHASE], 0xFF
    jne .tick
    mov byte [KB_LED_PHASE], 0
.tick:
    call keyboard_led_tick
    pop ds
    popad
    popf
    ret

