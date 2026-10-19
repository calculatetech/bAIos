; Optional live-only window. Normal ROM has no delay or scan tracing.
post_keyboard_diagnostic:
    pushad
    mov si, .intro
    call print_string
    in al, 0x21
    call .hex
    mov si, .status
    call print_string
    in al, KBC_STATUS
    call .hex
    mov di, 10
.second:
    mov cx, 500
.tick:
    call post_keyboard_wait
    call kbc_delay_2ms
    loop .tick
    mov si, .scans
    call print_string
    mov al, [0x04A4]
    call .hex
    mov si, .last
    call print_string
    mov al, [0x04A5]
    call .hex
    dec di
    jnz .second
    mov si, .done
    call print_string
    popad
    ret
.hex:
    push ax
    push bx
    push cx
    mov cl, al
    shr al, 4
    call .digit
    mov al, cl
    and al, 0x0F
    call .digit
    pop cx
    pop bx
    pop ax
    ret
.digit:
    add al, '0'
    cmp al, '9'
    jbe .emit
    add al, 'A' - '9' - 1
.emit:
    mov bx, 7
    mov ah, 0x0E
    int 0x10
    ret
.intro db 13,10,'POST keyboard window: 10 seconds. Pause / any key to resume; Ctrl+Alt+Del resets.',13,10,'PIC=',0
.status db ' status=',0
.scans db 13,10,'Keyboard scans=',0
.last db ' last=',0
.done db 13,10,'Keyboard window complete.',13,10,0
