; Intel82077AA sections5.0/5.2.7/5.2.8: VERSION90h distinguishes enhanced
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

board_floppy_summary_details:
    pushad
    ui_text 12+BOARD_ATA_DEVICE_COUNT,3,umc_floppy_details,0x0B
    mov di,(12+BOARD_ATA_DEVICE_COUNT)*160+28*2
    mov al,[fs:HW_FDC_VERSION]
    call setup_hex8
    call .separator
    mov al,[fs:F_STAGE]
    call setup_hex8
    call .separator
    mov al,[fs:F_STATUS]
    call setup_hex8
    call .separator
    mov al,[fs:F_RESULT]
    call setup_hex8
    call .separator
    mov al,[fs:F_RESULT+1]
    call setup_hex8
    popad
    ret
.separator:
    mov ax,0x072F
    call setup_color
    stosw
    ret
umc_floppy_details db 'FDC V/Stage/Err/ST0/PCN',0
