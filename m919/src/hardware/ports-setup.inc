; UM8663-specific capabilities; generic Setup owns the rendering and editing.
u_epp db 'EPP',0
u_ecp db 'ECP',0

; BX=displayed field. Return the existing owner or normalized enum scratch.
board_ports_parameters:
    push ax
    push dx
    mov dx,bx
    movzx cx,byte [cs:board_ports_counts+bx]
    shl bx,1
    mov si,[cs:u_ports_values+bx]
    mov bx,[cs:board_ports_pointers+bx]
    cmp bx,U_CHIP_VALUE
    jne .done
    cmp dx,3
    je .mode
    mov al,[fs:U_CHIP+22]
    shr al,1
    and al,1
    xor al,1
    jmp .scratch
.mode:
    mov al,2
    sub al,[fs:U_PORTS+4]
.scratch:
    mov [fs:U_CHIP_VALUE],al
.done:
    pop dx
    pop ax
    ret
board_ports_commit:
    pushf
    mov [fs:bx],al
    cmp byte [fs:U_FIELD],3
    je .mode
    cmp byte [fs:U_FIELD],4
    jne .done
    push ax
    xor al,1
    shl al,1
    and byte [fs:U_CHIP+22],0xFD
    or [fs:U_CHIP+22],al
    pop ax
.done:
    popf
    ret
.mode:
    push ax
    mov ah,2
    sub ah,al
    mov [fs:U_PORTS+4],ah
    pop ax
    jmp .done
board_ports_help:
    mov bx,5
    cmp byte [fs:U_FOCUS],0
    je .topic
    movzx bx,byte [fs:U_FIELD]
.topic:
    imul bp,bx,6
    mov si,[cs:board_ports_help_topics+bp]
    mov di,18*160+25*2
    mov bh,0x1E
    call setup_text
    mov si,[cs:board_ports_help_topics+bp+2]
    mov di,19*160+25*2
    call setup_text
    mov si,[cs:board_ports_help_topics+bp+4]
    mov di,20*160+25*2
    call setup_text
    ret
board_ports_counts db 5,5,4,3,2
board_ports_pointers dw U_PORTS,U_PORTS+1,U_PORTS+3,U_CHIP_VALUE,U_CHIP_VALUE
board_ports_help_topics:
    dw u_uart_a,u_help_uart1,u_help_uart2
    dw u_uart_b,u_help_uart1,u_help_uart2
    dw u_parallel,u_help_parallel1,u_help_parallel2
    dw u_parallel_mode,u_help_mode1,u_help_mode2
    dw u_ecp_dma,u_ecp_dma_help1,u_ecp_dma_help2
    dw u_devices,u_help_devices1,u_help_devices2
u_ecp_dma db 'Parallel ECP DMA Channel',0
u_ecp_dma_help1 db 'DMA channel used by the parallel port in ECP mode.',0
u_ecp_dma_help2 db '3 is the default. Avoid other devices using it.',0
u_ecp_dma_values dw chip_wait_1,chip_wait_3
