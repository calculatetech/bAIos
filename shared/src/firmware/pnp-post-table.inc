; Actual devices only. Text uses the retained console, including normal scrolling.
pnp_post_table:
    pushf
    pushad
    push ds
    push es
    push gs
    mov bp,sp
    sub sp,20
    mov eax,[fs:PNP_JOURNAL_FIRST]
    mov [ss:bp-16],eax
    mov byte [ss:bp-17],0
    push word 0x40
    pop ds
    mov ax,[0x50]              ; Page-zero console cursor: column, row.
    mov [ss:bp-20],ax
    mov byte [ss:bp-18],0
    mov si,pnp_table_title
    call pnp_table_text
%ifdef M919_BOARD_DEFINITION
    mov si,pnp_table_pci_header
    call pnp_table_text
    xor ebx,ebx
.pci:
    cmp bx,CFG_PLATFORM_HOST_PCI_DEVICE << 3
    je .next_pci
    cmp bx,CFG_PLATFORM_ISA_PCI_DEVICE << 3
    je .next_pci
    mov eax,ebx
    shl eax,8
    or eax,0x80000000
    call pnp_module_pci_read
    cmp ax,0xFFFF
    je .next_pci
    test ax,ax
    jz .next_pci
    mov [ss:bp-4],eax
    mov eax,ebx
    shl eax,8
    or eax,0x80000008
    call pnp_module_pci_read
    shr eax,16
    mov [ss:bp-8],ax
    mov eax,ebx
    shl eax,8
    or eax,0x80000004
    call pnp_module_pci_read
    mov [ss:bp-10],ax
    mov eax,ebx
    shl eax,8
    or eax,0x8000003C
    call pnp_module_pci_read
    mov [ss:bp-12],ax
    mov si,pnp_table_pci_prefix
    call pnp_table_text
    movzx eax,bx
    shr eax,3
    mov cx,2
    call pnp_table_hex
    mov al,'.'
    call pnp_table_char
    movzx eax,bx
    and al,7
    mov cx,1
    call pnp_table_hex
    call pnp_table_space
    mov eax,[ss:bp-4]
    mov cx,4
    call pnp_table_hex
    mov al,':'
    call pnp_table_char
    mov eax,[ss:bp-4]
    shr eax,16
    call pnp_table_hex
    call pnp_table_space
    mov al,[ss:bp-7]
    call pnp_table_pci_class
    mov cx,15
    call pnp_table_field
    cmp byte [ss:bp-11],0
    je .no_irq
    cmp byte [ss:bp-12],0xFF
    je .no_irq
    movzx eax,byte [ss:bp-12]
    call pnp_table_decimal
    jmp .pci_state
.no_irq:
    mov si,pnp_table_none
    call pnp_table_text
.pci_state:
    call pnp_table_space
    mov si,pnp_table_disabled
    test word [ss:bp-10],3
    jz .pci_state_text
    mov si,pnp_table_enabled
.pci_state_text:
    call pnp_table_text
    call pnp_table_newline
.next_pci:
    call pnp_module_pci_next
    cmp bx,256
    jb .pci
%endif
    mov si,pnp_table_isa_header
    call pnp_table_text
    mov eax,[ss:bp-16]
    test eax,eax
    jz .incomplete
    call pnp_pointer
    mov ax,[gs:si+PNP_ROOT_READ_PORT]
    mov [ss:bp-12],ax
    mov edi,[gs:si+PNP_ROOT_LDNS]
    test edi,edi
    jnz .ldn
    cmp byte [gs:si+PNP_ROOT_CSN_COUNT],0
    jne .cards
    cmp byte [gs:si+PNP_ROOT_STATUS],0
    jne .incomplete
    mov si,pnp_table_no_cards
    call pnp_table_text
    jmp .isa_done
.ldn:
    mov eax,edi
    call pnp_pointer
    mov eax,[gs:si+PNP_LDN_NEXT]
    mov [ss:bp-4],eax
    mov eax,[gs:si+PNP_LDN_ID]
    call pnp_table_id
    call pnp_table_space
    mov eax,edi
    call pnp_pointer
    mov eax,[gs:si+PNP_LDN_ID]
    call pnp_table_isa_class
    mov cx,12
    call pnp_table_field
    mov eax,edi
    call pnp_pointer
    mov eax,[gs:si+PNP_LDN_CARD]
    call pnp_pointer
    movzx eax,byte [gs:si+PNP_CARD_CSN]
    mov cx,2
    call pnp_table_hex
    mov ah,al
    mov al,3
    call pnp_isa_key
    call pnp_isa_write
    mov byte [ss:bp-17],1
    mov al,':'
    call pnp_table_char
    mov eax,edi
    call pnp_pointer
    movzx eax,byte [gs:si+PNP_LDN_INDEX]
    call pnp_table_hex
    mov ah,al
    mov al,7
    call pnp_isa_write
    call pnp_table_space
    mov eax,edi
    call pnp_pointer
    mov ax,[gs:si+PNP_LDN_STATUS]
    mov si,pnp_table_invalid
    test al,0x80
    jnz .inactive
    mov si,pnp_table_inactive
    test al,1
    jz .inactive
    mov dx,[ss:bp-12]
    mov al,0x30
    call pnp_isa_read
    test al,1
    jz .inactive
    mov si,pnp_table_active
    mov cx,11
    call pnp_table_field
    mov eax,edi
    call pnp_pointer
    mov al,[gs:si+PNP_LDN_NDOM]
    mov [ss:bp-10],al
    lea eax,[edi+PNP_LDN_DOMAINS]
    mov [ss:bp-8],eax
    mov byte [ss:bp-9],0
.domain:
    cmp byte [ss:bp-10],0
    je .domains_done
    mov eax,[ss:bp-8]
    call pnp_pointer
    test byte [gs:si+3],1
    jnz .next_domain
    mov byte [ss:bp-9],1
    cmp byte [gs:si],1
    je .memory
    cmp byte [gs:si],2
    je .io
    cmp byte [gs:si],3
    je .irq
    mov si,pnp_table_dma
    call pnp_table_text
    mov eax,[ss:bp-8]
    call pnp_pointer
    mov al,[gs:si+1]
    add al,0x74
    jmp .byte_resource
.irq:
    mov si,pnp_table_irq
    call pnp_table_text
    mov eax,[ss:bp-8]
    call pnp_pointer
    mov al,[gs:si+1]
    shl al,1
    add al,0x70
.byte_resource:
    mov dx,[ss:bp-12]
    call pnp_isa_read
    movzx eax,al
    call pnp_table_decimal
    jmp .resource_done
.io:
    mov si,pnp_table_io
    call pnp_table_text
    mov eax,[ss:bp-8]
    call pnp_pointer
    mov al,[gs:si+1]
    shl al,1
    add al,0x60
    mov cx,2
    call pnp_table_read_field
    mov ebx,eax
    mov cx,4
    jmp .range
.memory:
    mov si,pnp_table_memory
    call pnp_table_text
    mov eax,[ss:bp-8]
    call pnp_pointer
    mov al,[gs:si+1]
    mov cx,2
    test byte [gs:si+3],4
    jnz .memory32
    shl al,3
    add al,0x40
    call pnp_table_read_field
    shl eax,8
    jmp .memory_base
.memory32:
    movzx bx,al
    mov al,[cs:pnp_memory32_registers+bx]
    mov cx,4
    call pnp_table_read_field
.memory_base:
    mov ebx,eax
    mov cx,8
.range:
    call pnp_table_hex
    mov al,'-'
    call pnp_table_char
    mov eax,[ss:bp-8]
    call pnp_pointer
    mov eax,ebx
    add eax,[gs:si+16]
    dec eax
    call pnp_table_hex
.resource_done:
    call pnp_table_space
.next_domain:
    add dword [ss:bp-8],32
    dec byte [ss:bp-10]
    jmp .domain
.domains_done:
    cmp byte [ss:bp-9],0
    jne .end_ldn
    mov si,pnp_table_none
    call pnp_table_text
    jmp .end_ldn
.inactive:
    mov cx,11
    call pnp_table_field
    mov si,pnp_table_none
    call pnp_table_text
.end_ldn:
    call pnp_table_newline
    mov edi,[ss:bp-4]
    test edi,edi
    jnz .ldn
.cards:
    mov eax,[ss:bp-16]
    call pnp_pointer
    mov edi,[gs:si+PNP_ROOT_CARDS]
.card:
    test edi,edi
    jz .isa_done
    mov eax,edi
    call pnp_pointer
    mov eax,[gs:si+PNP_CARD_NEXT]
    mov [ss:bp-4],eax
    cmp dword [gs:si+PNP_CARD_FIRST_LDN],0
    jne .next_card
    mov eax,[gs:si+PNP_CARD_ID]
    call pnp_table_id
    mov si,pnp_table_no_ldn
    call pnp_table_text
.next_card:
    mov edi,[ss:bp-4]
    jmp .card
.isa_done:
    cmp byte [ss:bp-17],0
    je .warnings
    call pnp_isa_wait_key
.warnings:
    mov eax,[ss:bp-16]
    test eax,eax
    jz .warning_flags
    call pnp_pointer
    cmp byte [gs:si+PNP_ROOT_STATUS],0
    je .warning_flags
    mov si,pnp_table_incomplete
    call pnp_table_text
.warning_flags:
    cmp byte [fs:C_ERROR],0
    je .done
    mov si,pnp_table_warning
    call pnp_table_text
    xor bx,bx
.warning:
    bt [fs:C_ERROR],bx
    jnc .next_warning
    push bx
    shl bx,1
    mov si,[cs:pnp_table_warnings+bx]
    call pnp_table_text
    pop bx
.next_warning:
    inc bx
    cmp bx,7
    jb .warning
    call pnp_table_newline
    jmp .done
.incomplete:
    mov si,pnp_table_incomplete
    call pnp_table_text
.done:
    cmp byte [ss:bp-18],2
    ja .base_console
    mov ax,2
    sub al,[ss:bp-18]
    imul ax,160
    add ax,(58+BOARD_POST_SUMMARY_SHIFT)*2
    mov [ss:bp+6],ax
    jmp .return
.base_console:
    ; Leave a final visible memory field for the resident promotion epilogue.
    ; Console scrolling may already have removed the original Summary cell.
    mov si,pnp_table_base
    call pnp_table_text
    movzx ax,byte [ss:bp-19]
    cmp al,24
    jne .base_row
    dec ax                    ; The following CR/LF scrolls this line once.
.base_row:
    imul ax,160
    movzx dx,byte [ss:bp-20]
    shl dx,1
    add ax,dx
    mov [ss:bp+6],ax           ; Return DI, after the private RETF, to F000.
    mov si,pnp_table_base_tail
    call pnp_table_text
.return:
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    popf
    ret

; The descriptor supplies size; address/channel comes from actual registers.
pnp_table_read_field:
    push bx
    push edi
    push cx
    mov bl,al
    xor edi,edi
.byte:
    mov al,bl
    mov dx,[ss:bp-12]
    call pnp_isa_read
    shl edi,8
    movzx eax,al
    or edi,eax
    inc bl
    loop .byte
    mov eax,edi
    pop cx
    pop edi
    pop bx
    ret
pnp_table_char:
    push ax
    push bx
    cmp al,13
    je .carriage
    cmp al,10
    je .line
    inc byte [ss:bp-20]
    cmp byte [ss:bp-20],80
    jb .emit
.carriage:
    mov byte [ss:bp-20],0
    cmp al,13
    je .emit
.line:
    cmp byte [ss:bp-19],24
    jb .next_row
    cmp byte [ss:bp-18],3
    jae .emit
    inc byte [ss:bp-18]
    jmp .emit
.next_row:
    inc byte [ss:bp-19]
.emit:
    mov ah,0x0E
    mov bx,7
    call CFG_ROM_CODE_SEGMENT:pnp_console_callback
    pop bx
    pop ax
    ret
pnp_table_text:
    pushad
.next:
    cs lodsb
    test al,al
    jz .done
    call pnp_table_char
    jmp .next
.done:
    popad
    ret
pnp_table_field:
    pushad
.next:
    cs lodsb
    test al,al
    jz .pad
    call pnp_table_char
    dec cx
    jmp .next
.pad:
    mov al,' '
    jcxz .done
    call pnp_table_char
    loop .pad
.done:
    popad
    ret
pnp_table_space:
    push ax
    mov al,' '
    call pnp_table_char
    pop ax
    ret
pnp_table_newline:
    push si
    mov si,pnp_table_crlf
    call pnp_table_text
    pop si
    ret
pnp_table_hex:
    pushad
    mov edx,eax
    push cx
    mov al,8
    sub al,cl
    shl al,2
    mov cl,al
    shl edx,cl
    pop cx
.digit:
    rol edx,4
    mov al,dl
    and al,15
    add al,'0'
    cmp al,'9'
    jbe .print
    add al,7
.print:
    call pnp_table_char
    loop .digit
    popad
    ret
pnp_table_decimal:
    pushad
    xor cx,cx
    mov ebx,10
.divide:
    xor edx,edx
    div ebx
    push dx
    inc cx
    test eax,eax
    jnz .divide
.print:
    pop ax
    add al,'0'
    call pnp_table_char
    loop .print
    popad
    ret
pnp_table_id:
    pushad
    mov edi,eax
    mov dx,ax
    rol dx,8
    mov ax,dx
    shr ax,10
    and al,31
    add al,'@'
    call pnp_table_char
    mov ax,dx
    shr ax,5
    and al,31
    add al,'@'
    call pnp_table_char
    mov al,dl
    and al,31
    add al,'@'
    call pnp_table_char
    mov eax,edi
    shr eax,16
    rol ax,8
    mov cx,4
    call pnp_table_hex
    popad
    ret
pnp_table_isa_class:
    mov si,pnp_table_isa_name
    cmp ax,0xD041
    jne .done
    shr eax,16
    cmp ax,0x0005
    je .serial
    cmp ax,0x0105
    je .serial
    cmp ax,0x0004
    je .parallel
    cmp ax,0x0104
    je .parallel
    cmp ax,0x0007
    jne .done
    mov si,pnp_table_floppy_name
    ret
.parallel:
    mov si,pnp_table_parallel_name
    ret
.serial:
    mov si,pnp_table_serial_name
.done:
    ret
%ifdef M919_BOARD_DEFINITION
pnp_table_pci_class:
    mov si,pnp_table_pci_name
    cmp al,1
    jne .network
    mov si,pnp_table_storage_name
    ret
.network:
    cmp al,2
    jne .display
    mov si,pnp_table_network_name
    ret
.display:
    cmp al,3
    jne .audio
    mov si,pnp_table_display_name
    ret
.audio:
    cmp al,4
    jne .done
    mov si,pnp_table_audio_name
.done:
    ret
pnp_table_pci_header db 'Bus Dev.Fn Vendor:Dev  Device Class   IRQ Status',13,10,0
pnp_table_pci_prefix db 'PCI 00:',0
pnp_table_pci_name db 'PCI Device',0
pnp_table_storage_name db 'Storage',0
pnp_table_network_name db 'Network',0
pnp_table_display_name db 'Display',0
pnp_table_audio_name db 'Multimedia',0
pnp_table_enabled db 'Enabled',0
pnp_table_disabled db 'Disabled',0
%endif
pnp_table_title db 'PnP/PCI Device Listing',13,10,0
pnp_table_base db 'Base memory: ',0
pnp_table_base_tail db '     KB',13,10,0
pnp_table_isa_header db 'Device ID  Device Class CSN:LDN Status     Resources',13,10,0
pnp_table_isa_name db 'ISA PnP',0
pnp_table_parallel_name db 'Parallel',0
pnp_table_serial_name db 'Serial',0
pnp_table_floppy_name db 'Floppy',0
pnp_table_active db 'Active',0
pnp_table_invalid db 'Invalid',0
pnp_table_inactive db 'Inactive',0
pnp_table_none db '--',0
pnp_table_no_cards db 'ISA PnP: None',13,10,0
pnp_table_no_ldn db '  Card has no logical devices',13,10,0
pnp_table_incomplete db 'ISA PnP configuration incomplete',13,10,0
pnp_table_irq db 'IRQ',0
pnp_table_dma db 'DMA',0
pnp_table_io db 'IO ',0
pnp_table_memory db 'MEM ',0
pnp_table_warning db 'POST warnings: ',0
pnp_table_warnings dw pnp_table_w_clock,pnp_table_w_floppy,pnp_table_w_settings,pnp_table_w_keyboard,pnp_table_w_rom,pnp_table_w_other,pnp_table_w_pnp
pnp_table_w_clock db 'Clock ',0
pnp_table_w_floppy db 'Floppy ',0
pnp_table_w_settings db 'Settings ',0
pnp_table_w_keyboard db 'Keyboard ',0
pnp_table_w_rom db 'ROM ',0
pnp_table_w_other db 'Other ',0
pnp_table_w_pnp db 'PnP ',0
pnp_table_crlf db 13,10,0
