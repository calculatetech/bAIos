; Observe rebuilt BIOS vectors after real warm POST, before DOS can hook them.
core_warm_post_state:
    pushf
    pushad
    push ds
    push fs
    xor ax,ax
    mov ds,ax
    call load_bios_state
    mov al,0x37
    call rtc_read
    cmp al,0x5A
    jne .done
    cmp word [0x9*4],int09
    jne .fail
    cmp word [0x9*4+2],0xF000
    jne .fail
    cmp word [0x16*4],int16
    jne .fail
    cmp word [0x16*4+2],0xF000
    jne .fail
    cmp word [0x1A*4],int1a
    jne .fail
    cmp word [0x1A*4+2],0xF000
    jne .fail
    mov word [fs:0x1FFC],0xC0DE ; Test witness in unused reserved hardware space.
.done:
    pop fs
    pop ds
    popad
    popf
    ret
.fail:
    mov al,0x6E
    call emulator_exit
    jmp hard_halt
