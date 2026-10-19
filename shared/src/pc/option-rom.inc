; Requires port-owned ROM state offsets and configured state segment.
; AX ROM segment. Validate all declared 512-byte units, maximum 64 KiB.
rom_validate:
    push ds
    pushad
    mov ds,ax
    cmp word [0],0xAA55
    jne .bad
    movzx ecx,byte [2]
    test ecx,ecx
    jz .bad
    cmp ecx,128
    ja .bad
    shl ecx,9
    xor esi,esi
    xor bl,bl
.sum:
    add bl,[esi]
    inc esi
    dec ecx
    jnz .sum
    test bl,bl
    jnz .bad
    popad
    pop ds
    clc
    ret
.bad:
    popad
    pop ds
    stc
    ret

; ROM may replace all registers and its stack. Restore the firmware's own
; stack from private state before consuming saved flags and register frames.
option_rom_enter:
    pushf
    pushad
    push ds
    push es
    push fs
    push gs
    mov [fs:ROM_SAVED_SS],ss
    mov [fs:ROM_SAVED_SP],sp
    call far [fs:ROM_POINTER]
    cli
    mov dx,ROM_STATE_SEG
    mov fs,dx
    mov ss,[fs:ROM_SAVED_SS]
    mov sp,[fs:ROM_SAVED_SP]
    pop gs
    pop fs
    pop es
    pop ds
    popad
    popf
    cld
    ret

scan_option_roms:
    mov ax,ROM_FIRST_SEG
    mov [fs:ROM_SCAN_SEG],ax
.scan:
    mov ax,[fs:ROM_SCAN_SEG]
    cmp ax,ROM_LIMIT_SEG
    jae .done
    mov dx,ax
    add dx,0x80
    mov [fs:ROM_SCAN_NEXT],dx
    call rom_validate
    jc .next
    mov ds,ax
    movzx dx,byte [2]
    shl dx,5
    add dx,ax
    cmp dx,ROM_LIMIT_SEG
    ja .next
    ; Rounded 2-KiB scan advance follows the declared entire image.
    add dx,0x7F
    and dx,0xFF80
    mov [fs:ROM_SCAN_NEXT],dx
    mov [fs:ROM_POINTER+2],ax
    mov word [fs:ROM_POINTER],3
    xor ax,ax
    mov ds,ax
    mov es,ax
    call option_rom_enter
    inc word [fs:ROM_COUNT]
.next:
    xor ax,ax
    mov ds,ax
    mov es,ax
    mov ax,[fs:ROM_SCAN_NEXT]
    mov [fs:ROM_SCAN_SEG],ax
    jmp .scan
.done:
    ret
