; UM8663-specific capabilities; generic Setup owns the rendering and editing.
u_epp db 'EPP',0
u_ecp db 'ECP',0
u_m919_uart_a_values dw u_com3,u_com1,u_disabled
u_m919_uart_b_values dw u_com4,u_com2,u_disabled
u_m919_parallel_values dw u_lpt2,u_lpt1,u_disabled
; Display order is independent of the saved COM/LPT encodings.
board_ports_encoding db 3,1,0, 4,2,0, 3,2,0

; BX=displayed field. Return the existing owner or normalized enum scratch.
board_ports_parameters:
    push ax
    push dx
    mov dx,bx
    movzx cx,byte [cs:board_ports_counts+bx]
    shl bx,1
    mov si,[cs:u_ports_values+bx]
    mov bx,[cs:board_ports_pointers+bx]
    cmp dx,3
    jb .address
    cmp bx,U_CHIP_VALUE
    jne .done
    cmp dx,3
    je .mode
    mov al,[fs:U_CHIP+22]
    shr al,1
    and al,1
    xor al,1
    jmp .scratch
.address:
    mov al,[fs:bx]
    push si
    imul si,dx,3
    xor bx,bx
.lookup:
    cmp al,[cs:board_ports_encoding+si+bx]
    je .found
    inc bx
    cmp bx,2
    jb .lookup
.found:
    mov al,bl
    pop si
    mov bx,U_CHIP_VALUE
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
    pushad
    mov [fs:bx],al
    movzx bx,byte [fs:U_FIELD]
    cmp bx,3
    jae .other
    shl bx,1
    mov dx,[cs:board_ports_pointers+bx]
    shr bx,1
    imul bx,3
    movzx si,al
    add bx,si
    mov al,[cs:board_ports_encoding+bx]
    mov bx,dx
    mov [fs:bx],al
    jmp .done
.other:
    cmp byte [fs:U_FIELD],3
    je .mode
    cmp byte [fs:U_FIELD],4
    jne .done
    xor al,1
    shl al,1
    and byte [fs:U_CHIP+22],0xFD
    or [fs:U_CHIP+22],al
.done:
    popad
    popf
    ret
.mode:
    mov ah,2
    sub ah,al
    mov [fs:U_PORTS+4],ah
    jmp .done
board_ports_choice_valid:
    ; The two UARTs have disjoint address sets, so no sibling can conflict.
    push bx
    movzx bx,byte [fs:U_FIELD]
    cmp al,[cs:board_ports_counts+bx]
    cmc
    pop bx
    ret
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
board_ports_counts db 3,3,3,3,2
board_ports_pointers dw U_PORTS,U_PORTS+1,U_PORTS+3,U_CHIP_VALUE,U_CHIP_VALUE
board_ports_help_topics:
    dw u_uart_a,u_help_uart1,u_help_uart2
    dw u_uart_b,u_help_uart1,u_help_uart2
    dw u_parallel,u_help_parallel1,u_help_parallel2
    dw u_parallel_mode,u_help_mode1,u_help_mode2
    dw u_ecp_dma,u_ecp_dma_help1,u_ecp_dma_help2
    dw u_devices,u_help_devices1,u_help_devices2
u_ecp_dma db 'Parallel ECP DMA Channel',0
u_ecp_dma_help1:
    ui_string 'DMA channel used by the parallel port in ECP mode.', u_ecp_dma_help1
u_ecp_dma_help2:
    ui_string '3 is the default. Avoid other devices using it.', u_ecp_dma_help2
u_ecp_dma_values dw chip_wait_1,chip_wait_3
