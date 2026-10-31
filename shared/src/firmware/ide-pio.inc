; Requested limits survive discovery and reset; effective mode follows completion.
ide_pio_guard:
%ifdef BOARD_ATA_PIO_ADAPTER
    push bx
    push cx
%endif
    push fs
%ifdef BOARD_ATA_PIO_ADAPTER
    call hardware_ata_channel
    mov cl,al
    mov bl,1
    shl bl,cl
%endif
    call load_bios_state
%ifdef BOARD_ATA_PIO_ADAPTER
    test [fs:S_PIO_BLOCKED],bl
%else
    test byte [fs:S_PIO_BLOCKED],1
%endif
    pop fs
%ifdef BOARD_ATA_PIO_ADAPTER
    pop cx
    pop bx
%endif
    jz .ready
    mov byte [fs:S_STATUS],ERR_TIMEOUT
    stc
    ret
.ready:
    clc
    ret

ide_pio_identify:
    pushad
    ; Legacy mode0..2 is the fallback when the cycle fields are invalid.
    mov bl,[es:IDENTIFY_BUFFER+103]
    cmp bl,2
    jbe .validity
    xor bl,bl
.validity:
    test word [es:IDENTIFY_BUFFER+106],2
    jz .limit
    mov ax,[es:IDENTIFY_BUFFER+134]
    test ax,ax
    jz .advanced
    cmp ax,0xFFFF
    je .advanced
    xor bx,bx
    cmp ax,383
    ja .advanced
    inc bl
    cmp ax,240
    ja .advanced
    inc bl
.advanced:
    test word [es:IDENTIFY_BUFFER+98],0x0800
    jz .limit
    mov ax,[es:IDENTIFY_BUFFER+136]
    test ax,ax
    jz .limit
    cmp ax,180
    ja .limit
    test byte [es:IDENTIFY_BUFFER+128],1
    jz .mode4
    mov bl,3
.mode4:
    cmp ax,120
    ja .limit
    test byte [es:IDENTIFY_BUFFER+128],2
    jz .limit
    mov bl,4
.limit:
    mov [fs:S_PIO_LIMIT],bl
    call ide_pio_restore
    popad
    ret

ide_pio_restore:
    pushad
    mov byte [fs:S_PIO_MODE],0
    call ide_pio_guard
    jc .done
    mov bl,[fs:S_PIO_REQUEST]
    test bl,bl
    jnz .ceiling
    mov bl,5
.ceiling:
    cmp bl,5
    ja .done
%ifdef BOARD_ATA_PIO_ADAPTER
    call hardware_ata_pio_allowed
    jc .done
%endif
    dec bl
    cmp bl,[fs:S_PIO_LIMIT]
    jbe .selected
    mov bl,[fs:S_PIO_LIMIT]
.selected:
    cmp bl,BOARD_ATA_PIO_MAX
    jbe .port_limit
    mov bl,BOARD_ATA_PIO_MAX
.port_limit:
    ata_port ATA_DRIVE
    mov al,0xA0
    or al,[fs:S_ATA_DEVICE]
    out dx,al
    call ata_delay
    call ide_pio_wait_idle
    jc .failed
    ata_port ATA_ERROR
    mov al,3
    out dx,al
    ata_port ATA_COUNT
    mov al,bl
    or al,8
    out dx,al
    mov al,0xEF
    call ata_no_data_command
    jc .failed
    mov al,bl
%ifdef BOARD_ATA_PIO_ADAPTER
    call hardware_ata_pio_apply
%endif
    mov [fs:S_PIO_MODE],bl
    jmp .done
.failed:
    cmp byte [fs:S_STATUS],ERR_TIMEOUT
    je .blocked
    ata_port ATA_ERROR
    in al,dx
    test al,4
    jnz .done
.blocked:
    call hardware_ata_channel
    mov cl,al
    mov bl,1
    shl bl,cl
    push fs
    call load_bios_state
    or [fs:S_PIO_BLOCKED],bl
    pop fs
.done:
    popad
    jmp ide_pio_guard

; ERR belongs to the old command until a new command clears it (ATA Host_Idle).
ide_pio_wait_idle:
    mov ecx,0x00100000
    ata_port ATA_STATUS
.poll:
    call ata_read_status
    test al,0x88
    jz .ready
    dec ecx
    jnz .poll
    mov byte [fs:S_STATUS],ERR_TIMEOUT
    stc
    ret
.ready:
    clc
    ret

ide_pio_reset:
    pushad
    push fs
%ifdef BOARD_ATA_PIO_ADAPTER
    call hardware_ata_pio_reset
%endif
    call hardware_ata_channel
    mov cl,al
    mov bl,1
    shl bl,cl
    not bl
    call load_bios_state
    and [fs:S_PIO_BLOCKED],bl
    pop fs
    popad
    ret

%if BOARD_ATA_PIO_MAX < 0 || BOARD_ATA_PIO_MAX > 4
    %error ATA PIO ceiling must be0..4
%endif
%ifndef BOARD_ATA_PIO_ADAPTER
ide_pio_mode_text:
    mov al,[fs:S_PIO_MODE]
    add al,'0'
    mov ah,7
    call setup_color
    stosw
    ret
ide_pio_discovery:
    mov byte [fs:S_PIO_BLOCKED],0
    mov byte [fs:S_PIO_REQUEST],0
    mov byte [fs:0x200+S_PIO_REQUEST],0
    ret
ide_pio_begin:
    mov byte [fs:S_PIO_MODE],0
    mov byte [fs:S_PIO_LIMIT],0
    jmp ide_pio_guard
; Standard ATA host precondition: existing strobes honor the device's IORDY.
; No programmable timing fields or clock are inferred for a separate controller.
hardware_ata_channel:
    xor al,al
    ret
%endif
