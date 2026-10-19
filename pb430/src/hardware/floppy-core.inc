; Existing capability probe: Intel82077AA sections5.0/5.2.7/5.2.8: VERSION90h distinguishes enhanced
; command support. Older765/8272 returns the consumed invalid result80h.
board_floppy_configure:
    mov byte [fs:HW_FDC_ENHANCED],0
    mov al,0x10
    call fdc_write
    jc .done
    call fdc_read
    jc .done
    mov [fs:HW_FDC_VERSION],al
    cmp al,0x80
    je .legacy
    cmp al,0x90
    jne .unknown
    mov byte [fs:HW_FDC_ENHANCED],1
    ; Retain donor DMA/FIFO policy only for a confirmed enhanced controller.
    mov al,0x13
    call fdc_write
    jc .done
    xor al,al
    call fdc_write
    jc .done
    mov al,0x0C
    call fdc_write
    jc .done
    xor al,al
    jmp fdc_write
.legacy:
    ; Default conventional DMA operation needs no optional enhanced command.
    clc
.done:
    ret
.unknown:
    mov byte [fs:F_STATUS],0x20
    stc
    ret
board_floppy_perpendicular:
    cmp byte [fs:HW_FDC_ENHANCED],1
    je .enhanced
    cmp byte [fs:F_RATE],3
    je .unsupported
    clc                      ; Legacy controller's real conventional mode.
    ret
.enhanced:
    mov al,0x12
    call fdc_write
    jc .done
    mov al,0x80
    cmp byte [fs:F_RATE],3
    jne .mode
    mov al,0xBC
.mode:
    jmp fdc_write
.unsupported:
    mov byte [fs:F_STATUS],1  ; Cannot promise2.88M on a765-class controller.
    stc
.done:
    ret

