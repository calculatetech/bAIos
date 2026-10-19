; Passive observer spans the real RTC alert, gate, tones and bootstrap.
core_clock_watch_begin:
    mov word [0xB1C],0
    mov byte [0xB1E],0
    mov word [0x1C*4],core_clock_watch_tick
    mov word [0x1C*4+2],0xF000
    ret
core_clock_watch_tick:
    push ax
    push ds
    xor ax,ax
    mov ds,ax
    inc word [0xB1C]
    in al,0x61
    and al,3
    or [0xB1E],al
    pop ds
    pop ax
    iret
