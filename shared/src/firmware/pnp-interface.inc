; P1 public interface. Normal ROMs deliberately have no installation signature.
; BiosSelector covers physical0400..103FF; all public temporaries use caller SS.
PNP_PAYLOAD equ 0xAD
PNP_BASE equ PNP_PAYLOAD+66
PNP_RAM_END equ PNP_BASE+8
PNP_ISA equ PNP_RAM_END+4
PNP_STATUS equ PNP_ISA+3
PNP_PROVENANCE equ PNP_STATUS+1
times -(PNP_PROVENANCE != 0xFF) db 0
PNP_FRAME equ 216
PNP_NODE_MAX equ 80
PNP_NODE equ -96
PNP_PORTS equ PNP_NODE-8
PNP_WORK equ PNP_PORTS-74
%ifdef BOARD_SETUP_READONLY_PAGES
PNP_MAX_SIZE equ 42
%elif BOARD_ATA_DEVICE_COUNT = 4
PNP_MAX_SIZE equ 76
%else
PNP_MAX_SIZE equ 61
%endif
PNP_CHIP equ PNP_WORK-24
PNP_VIEW equ PNP_CHIP-1
%ifdef PB430_PORT
%define PNP_AUX 1
%elifdef BOARD_PNP_NV6_LATE
%define PNP_AUX 1
%endif
times -(PNP_VIEW < -PNP_FRAME) db 0
times -(PNP_NODE+PNP_NODE_MAX > -8) db 0

%ifdef EMULATOR_PNP_TEST
align 16,db 0xFF
pnp_installation:
    db '$PnP',0x10,0x21
    dw 0
    db (-(0x24+0x50+0x6E+0x50+0x10+0x21+0xF0+0x0F+0x40+4+((pnp_real_entry-$$) & 255)+((pnp_real_entry-$$) >> 8)+((pnp_pm_entry-$$) & 255)+((pnp_pm_entry-$$) >> 8))) & 255
    dd 0
    dw pnp_real_entry,0xF000,pnp_pm_entry
    dd 0xF0000,0
    dw 0x40
    dd 0x400
times -(($-pnp_installation) != 0x21) db 0
%endif

; POST only: freeze applied policy after final routing/memory/cache application.
pnp_publish:
    pushf
    cli
    pushad
    push es
    push fs
    call load_bios_state
    sub sp,98
    mov bp,sp
    mov di,bp
    mov cx,66
.zero:
    mov byte [ss:di],0
    inc di
    loop .zero
    xor dx,dx
    mov si,C_IDE
    call settings_nv6_pack_component
    mov dx,8
    mov si,C_PORTS
    call settings_nv6_pack_component
    mov dx,24
    mov si,C_PNP
    call settings_nv6_pack_component
    ; Preserve live effective state while the existing owner decodes raw saved
    ; policy. Recovery selects hardware settings, not a destructive migration.
    xor si,si
.save_chip:
    mov al,[fs:C_CHIP+si]
    mov [ss:bp+si+74],al
    inc si
    cmp si,CHIP_SIZE
    jb .save_chip
    push word [fs:C_VALID]
    call chipset_settings_load_raw
    mov dx,16
    mov si,C_CHIP
    call settings_nv6_pack_component
    xor si,si
.restore_chip:
    mov al,[ss:bp+si+74]
    mov [fs:C_CHIP+si],al
    inc si
    cmp si,CHIP_SIZE
    jb .restore_chip
    pop word [fs:C_VALID]
    lea di,[bp+66]
    call settings_base_active_pack
    mov ax,0x40
    mov es,ax
    mov di,PNP_PAYLOAD
    mov si,bp
    mov cx,74
.copy:
    mov al,[ss:si]
    mov [es:di],al
    inc si
    inc di
    loop .copy
    memory_extended_kib eax
    add eax,1024
    shl eax,10
    mov [es:PNP_RAM_END],eax
    mov word [es:PNP_ISA],0
    mov byte [es:PNP_ISA+2],0
    mov word [es:PNP_STATUS],0x01A5
%ifdef BOARD_SETUP_READONLY_PAGES
    in al,0x5F
    mov [es:PNP_PROVENANCE],al
%endif
    mov al,4                  ; Existing onboard controller capability.
%if BOARD_ATA_DEVICE_COUNT = 4
    cmp byte [fs:HW_IDE_USABLE],1
    je .ide_policy
    xor al,al
    jmp .ide_done
%endif
.ide_policy:
%ifdef BOARD_SETUP_READONLY_PAGES
    test byte [es:PNP_PROVENANCE],0x10
    jnz .ide_done
%else
    cmp byte [fs:C_IDE],0
    je .ide_done
%endif
    or al,1
%if BOARD_ATA_DEVICE_COUNT = 4
    test byte [fs:C_CHIP+23],0x10
    jnz .ide_done
    or al,2
%endif
.ide_done:
    or al,0x80
%if BOARD_ATA_DEVICE_COUNT = 4
    test byte [fs:C_CHIP+22],2
    jz .dma_frozen
    or al,0x10
.dma_frozen:
%endif
    mov [es:PNP_STATUS],al
    lea sp,[bp+98]
    pop fs
    pop es
    popad
    popf
    ret

pnp_real_entry:
    pushfd
    pushad
    movzx ebp,sp
    jmp pnp_enter
pnp_pm_entry:
    pushfd
    pushad
    mov ax,ss
    lar eax,eax
    test eax,0x400000
    mov ebp,esp
    jnz pnp_enter
    movzx ebp,bp
pnp_enter:
    push ds
    push es
    push fs
    push gs
    sub esp,208
    cld
    cli
    mov ax,ss
    mov fs,ax
    mov ax,[ss:ebp+40]
    cmp ax,0
    je pnp_count
    cmp ax,1
    je pnp_get
    cmp ax,2
    je pnp_set
    cmp ax,0x0B
    je pnp_apm
    cmp ax,0x40
    je pnp_isa
    cmp ax,0x0A
    jbe pnp_unsupported
    sub ax,0x41
    cmp ax,2
    jbe pnp_unsupported
    mov ax,0x81
    jmp pnp_return
pnp_unsupported:
    mov ax,0x82
    jmp pnp_return
pnp_bad_parameter:
    mov ax,0x84
    jmp pnp_return
pnp_bad_handle:
    mov ax,0x83
    jmp pnp_return
pnp_set_failed:
    mov ax,0x85
    jmp pnp_return
pnp_success:
    xor ax,ax
pnp_return:
    mov [ss:ebp+28],ax
    add esp,208
    pop gs
    pop fs
    pop es
    pop ds
    popad
    popfd
    retf

; Every far output offset is a WORD; widen before using a 32-bit buffer core.
pnp_count:
    mov es,[ss:ebp+44]
    movzx edi,word [ss:ebp+42]
    mov byte [es:edi],PNP_NODE_COUNT
    mov es,[ss:ebp+48]
    movzx edi,word [ss:ebp+46]
    mov word [es:edi],PNP_MAX_SIZE
    jmp pnp_success
pnp_apm:
    mov es,[ss:ebp+44]
    movzx edi,word [ss:ebp+42]
    mov word [es:edi],0
    jmp pnp_success
pnp_isa:
    mov gs,[ss:ebp+46]
    mov es,[ss:ebp+44]
    movzx edi,word [ss:ebp+42]
    mov dword [es:edi],1
    mov al,[gs:PNP_ISA]
    mov [es:edi+1],al
    mov ax,[gs:PNP_ISA+1]
    mov [es:edi+2],ax
    mov word [es:edi+4],0
    jmp pnp_success
pnp_get:
    mov ax,[ss:ebp+50]
    dec ax
    cmp ax,1
    ja pnp_bad_parameter
    mov bx,[ss:ebp+52]
    mov gs,bx
    mov es,[ss:ebp+44]
    movzx edi,word [ss:ebp+42]
    movzx ebx,byte [es:edi]
    cmp bl,PNP_NODE_COUNT
    jae pnp_bad_handle
    push es
    push edi
    push bx
    call pnp_load_work
    call pnp_build_node
    pop bx
    pop edi
    pop es
    inc bl
    cmp bl,PNP_NODE_COUNT
    jb .next
    mov bl,0xFF
.next:
    mov [es:edi],bl
    mov es,[ss:ebp+48]
    movzx edi,word [ss:ebp+46]
    lea esi,[ebp+PNP_NODE]
    movzx ecx,word [ss:esi]
.copy:
    mov al,[ss:esi]
    mov [es:edi],al
    inc esi
    inc edi
    loop .copy
    jmp pnp_success

; AX=0 current or1 next, BX=node. Preserve both across storage operations.
pnp_load_work:
    pushad
    mov [ss:ebp+PNP_VIEW],al
    lea edi,[ebp+PNP_WORK]
    test ax,ax
    jz .frozen
    call settings_nv6_read32
    jc .frozen
    xor ebx,ebx
.base:
    call settings_base_index
    call rtc_read
    mov [ss:edi+ebx+66],al
    inc bx
    cmp bx,8
    jb .base
    jmp .unpack
.frozen:
    xor ebx,ebx
.copy:
    mov dl,[gs:PNP_PAYLOAD+ebx]
    mov [ss:edi+ebx],dl
    inc bx
    cmp bx,74
    jb .copy
.unpack:
%if BOARD_ATA_DEVICE_COUNT = 4
    push edi
    lea esi,[ebp+PNP_CHIP]
    add edi,NV6_CHIP
    mov bx,NV6_CHIP_MASK
    mov cx,CHIP_SIZE
    call settings_unpack32
    pop edi
%endif
    lea esi,[ebp+PNP_PORTS]
    add edi,NV6_PORT
    mov bx,ports_packed_masks
    mov cx,8
    call settings_unpack32
%ifdef BOARD_SETUP_READONLY_PAGES
    ; Freeze the physical SW3 readback observed at POST, not saved CMOS defaults.
    mov al,[gs:PNP_PROVENANCE]
    shr al,2
    mov dl,al
    xor al,1
    and al,1
    mov [ss:esi],al
    mov al,dl
    shr al,1
    xor al,1
    and al,1
    shl al,1
    mov [ss:esi+1],al
    mov dl,[gs:PNP_PROVENANCE]
    and dl,3
    movzx ebx,dl
    mov al,[cs:pnp_mp_lpt+ebx]
    mov [ss:esi+3],al
    mov al,[gs:PNP_PROVENANCE]
    shr al,6
    xor al,1
    and al,1
    mov [ss:esi+5],al
%endif
    popad
    ret
%ifdef BOARD_SETUP_READONLY_PAGES
; Source inference: supplied SW3 LPT1/2/3 names plus OEM's3BC/378/278 order.
; This decodes the physical selector; it is not an independent bench result.
pnp_mp_lpt db 1,2,3,0
%endif

; Template table entries keep stable handles, including two equal UART IDs.
pnp_build_node:
    pushad
    movzx edx,bl
    shl dx,1
    movzx esi,word [cs:pnp_nodes+edx]
    lea edi,[ebp+PNP_NODE]
    movzx ecx,byte [cs:esi]
    inc esi
    mov ax,cx
    add ax,9                   ; Shared size/handle/vendor and two empty blocks.
    mov [ss:edi],ax
    mov [ss:edi+2],bl
    mov word [ss:edi+3],0xD041
    add edi,5
.copy:
    mov al,[cs:esi]
    mov [ss:edi],al
    inc esi
    inc edi
    loop .copy
    mov dword [ss:edi],0x00790079
    call pnp_resources
    cmp bl,6
    jne .routing
    mov eax,[gs:PNP_RAM_END]
    sub eax,0x100000
    mov [ss:ebp+PNP_NODE+32],eax
.routing:
%ifndef BOARD_SETUP_READONLY_PAGES
    call pnp_route_field
    jc .done
    ; Possible configurations are independent alternatives from this same encoder.
    mov dl,[ss:esi]
    push dx
    mov dh,al
    mov byte [ss:esi],0
    lea edi,[ebp+PNP_NODE+12]
    add edi,ecx
    add edi,2                  ; Skip allocated End tag.
.alternative:
    inc byte [ss:esi]
    cmp [ss:esi],dh
    ja .alternatives_done
%if BOARD_ATA_DEVICE_COUNT = 4
    ; UM8663 has fixed primary/secondary UART identity and no3BC LPT decode.
    cmp bl,PNP_LPT
    je .lpt_choice
    mov al,[ss:esi]
    xor al,bl
    test al,1
    jz .alternative
    jmp .choice_ok
.lpt_choice:
    cmp byte [ss:esi],1
    je .alternative
.choice_ok:
%endif
    mov byte [ss:edi],0x30
    inc edi
    call pnp_resources
    push edx
    lea edx,[ebp+PNP_NODE+12]
    push ecx
.resource_copy:
    mov al,[ss:edx]
    mov [ss:edi],al
    inc edx
    inc edi
    loop .resource_copy
    pop ecx
    pop edx
    mov byte [ss:edi],0x38
    inc edi
    jmp .alternative
.alternatives_done:
    mov dword [ss:edi],0x00790079
    add edi,4
    sub edi,ebp
    sub edi,PNP_NODE
    mov [ss:ebp+PNP_NODE],di
    pop dx
    mov [ss:esi],dl
    call pnp_resources        ; Restore the allocated block after alternatives.
.done:
%endif
    popad
    ret

; BX=stable node. Return its saved routing byte and domain, CF=fixed node.
pnp_route_field:
    lea esi,[ebp+PNP_PORTS]
    mov al,4
    cmp bl,8
    je .good
%ifndef BOARD_PNP_NV6_LATE
    inc esi
    cmp bl,9
    je .good
    dec esi
%endif
    add esi,3
    mov al,3
    cmp bl,PNP_LPT
    je .good
    add esi,2
    mov al,1
    cmp bl,PNP_FDC
    je .good
%ifdef PNP_AUX
    inc esi
    cmp bl,PNP_MOUSE
    je .good
%endif
    jmp .fixed
.good:
    mov ecx,7                 ; Allocated lengths exclude possible alternatives.
    cmp bl,PNP_LPT
    jne .fdc_length
%if BOARD_ATA_DEVICE_COUNT = 4
    mov cx,18
%endif
.fdc_length:
    cmp bl,PNP_FDC
    jne .routed
    mov cx,14
.routed:
%ifdef PNP_AUX
    cmp bl,PNP_MOUSE
    jne .route_done
    mov cx,3
.route_done:
%endif
    clc
    ret
.fixed:
    stc
    ret

; Patch allocated descriptors only. No controller probing or register writes.
pnp_resources:
    pushad
    call pnp_route_field
    jc .ide
    lea edi,[ebp+PNP_NODE+12]
    mov al,[ss:esi]
    test al,al
    jz .disabled
%ifdef PNP_AUX
    cmp bl,PNP_MOUSE
    jne .not_mouse
    mov word [ss:edi+1],0x1000
    jmp .done
.not_mouse:
%endif
    cmp bl,PNP_FDC
    je .fdc_enabled
    cmp bl,PNP_LPT
    je .lpt
    movzx edx,al
    shl dx,1
    cmp dl,6
    jb .uart_fixed
    sub dx,6
    push eax
    movzx eax,byte [ss:ebp+PNP_PORTS+2]
    shl ax,2
    add dx,ax
    pop eax
    movzx edx,dx
    mov dx,[cs:ports_pairs+edx]
    jmp .uart
.uart_fixed:
    mov dx,[cs:ports_fixed+edx]
.uart:
    mov [ss:edi+1],dx
    mov byte [ss:edi+3],8
    mov dx,8
    test al,1
    jz .irq
    shl dx,1
    jmp .irq
.lpt:
    movzx edx,al
    shl dx,1
    mov dx,[cs:ports_parallel+edx]
    mov [ss:edi+1],dx
    mov byte [ss:edi+3],3
    mov dx,0x80
%ifdef PB430_PORT
    mov dx,0x20              ; ACC3221 DE source2 routes primary parallel to PIRQ5.
%endif
%if BOARD_ATA_DEVICE_COUNT = 4
    ; ports_apply establishes the complete OEM C1/C3 tuple for each address.
    cmp al,2
    je .lpt_dma
    mov dx,0x20
.lpt_dma:
    mov ah,[ss:ebp+PNP_PORTS+4]
    cmp ah,2
    sete byte [ss:ebp+PNP_NODE+6]
    cmp ah,1
    jne .lpt_standard
    mov byte [ss:edi+3],8      ; EPP address/data registers occupy offsets3..7.
.lpt_standard:
    mov word [ss:edi+8],0x0800
    mov byte [ss:edi+11],1
    mov dword [ss:edi+12],0
    mov word [ss:edi+16],0
    cmp ah,2
    jne .irq
    ; Microsoft/HP ECP ISA Interface Standard1.14 Table8: offsets400..402.
    ; https://pic.hallikainen.org/techref/io/parallel/1284/ecp_reg.pdf
    mov ax,[ss:edi+1]
    add ax,0x400
    mov [ss:edi+12],ax
    mov [ss:edi+14],ax
    mov byte [ss:edi+17],3
    mov al,8
    cmp byte [ss:ebp+PNP_VIEW],0
    jne .saved_dma
    test byte [gs:PNP_STATUS],0x10
    jmp .dma_choice
.saved_dma:
    test byte [ss:ebp+PNP_CHIP+22],2
.dma_choice:
    jz .dma
    mov al,2
.dma:
    mov [ss:edi+8],al
%endif
.irq:
    mov [ss:edi+5],dx
    jmp .done
.fdc_enabled:
    mov dword [ss:edi+1],0x4B0603F0
    mov word [ss:edi+5],0x03F7
    mov byte [ss:edi+7],1
    mov word [ss:edi+9],0x40
    mov word [ss:edi+12],0x0804
    jmp .done
.disabled:
    ; Keep resource tag bytes but zero every address, length and IRQ/DMA mask.
    xor edx,edx
.zero:
    mov al,[ss:edi+edx]
    and al,7
    movzx ebx,al
    inc edx
.zero_byte:
    mov byte [ss:edi+edx],0
    inc edx
    dec ebx
    jnz .zero_byte
    cmp edx,ecx
    jb .zero
    jmp .done
.ide:
    cmp bl,PNP_IDE
    jne .done
%ifdef BOARD_SETUP_READONLY_PAGES
    test byte [gs:PNP_STATUS],1
    jnz .done
%else
    cmp byte [ss:ebp+PNP_VIEW],0
    jne .next_ide
    test byte [gs:PNP_STATUS],1
    jz .ide_disabled
%if BOARD_ATA_DEVICE_COUNT = 4
    test byte [gs:PNP_STATUS],2
    jnz .done
    jmp .secondary_disabled
%else
    jmp .done
%endif
.next_ide:
    test byte [gs:PNP_STATUS],4
    jz .ide_disabled
    test byte [ss:ebp+PNP_WORK],1
    jz .ide_disabled
%if BOARD_ATA_DEVICE_COUNT = 4
    test byte [ss:ebp+PNP_CHIP+23],0x10
    jz .done
.secondary_disabled:
    lea edi,[ebp+PNP_NODE+23]
    mov cx,11
    jmp .disabled
%else
    jmp .done
%endif
%endif
.ide_disabled:
    lea edi,[ebp+PNP_NODE+12]
    mov cx,11
%if BOARD_ATA_DEVICE_COUNT = 4
    mov cx,22
%endif
    jmp .disabled
.done:
    popad
    ret

; Validate the complete allocated request; metadata and subsequent blocks are not
; settings. Static publication patches only the selected logical routing byte.
pnp_set:
    mov ax,[ss:ebp+48]
    dec ax
    cmp ax,2
    ja pnp_bad_parameter
    movzx ebx,byte [ss:ebp+42]
    cmp bl,PNP_NODE_COUNT
    jae pnp_bad_handle
    mov gs,[ss:ebp+50]
    mov es,[ss:ebp+46]
    movzx edx,word [ss:ebp+44]
    cmp ax,1
    je .static
    ; Current or Both: an unchanged effective configuration needs no hot change.
    xor ax,ax
    call pnp_load_work
    call pnp_build_node
    call pnp_compare_allocated
    cmp ax,2
    je pnp_bad_parameter
    test ax,ax
    jnz pnp_set_failed
    cmp word [ss:ebp+48],1
    je pnp_success
.static:
    mov ax,1
    call pnp_load_work
    call pnp_build_node
    call pnp_route_field
    jc .fixed
%ifdef BOARD_SETUP_READONLY_PAGES
    jmp .fixed
%else
    push ax                  ; Domain limit, not a persisted value.
    mov byte [ss:esi],0
.candidate:
    call pnp_resources
    call pnp_compare_allocated
    test ax,ax
    jz .selected
    cmp ax,2
    je .bad_pop
    inc byte [ss:esi]
    pop ax
    push ax
    cmp [ss:esi],al
    jbe .candidate
    jmp .bad_pop
.selected:
    pop ax
    lea esi,[ebp+PNP_PORTS]
    call ports_valid32
    jc pnp_bad_parameter
    lea edi,[ebp+PNP_WORK+NV6_PORT]
    mov word [ss:edi],0
    mov bx,ports_packed_masks
    mov cx,8
    call settings_pack32
    jmp .commit
.bad_pop:
    pop ax
    jmp pnp_bad_parameter
%endif
.fixed:
    call pnp_compare_allocated
    cmp ax,2
    je pnp_bad_parameter
    test ax,ax
    jnz pnp_set_failed
.commit:
    lea edi,[ebp+PNP_WORK]
    push ebp
    xor ebp,ebp
    call settings_commit32
    pop ebp
    jc pnp_set_failed
    jmp pnp_success

; Return0 equal,1 different resources,2 malformed ordering. End-tag checksum is
; optional per ISA PnP; all three blocks remain generated by the single encoder.
pnp_compare_allocated:
    push bx
    push esi
    push dx
    lea esi,[ebp+PNP_NODE+12]
    lea edi,[edx+12]
    xor bx,bx                ; BL=differences/order, BH=request numeric resources.
    xor dx,dx                ; DL=expected numeric resources; request already in EDI.
.descriptor:
    mov al,[ss:esi]
    mov ah,al
    cmp al,[es:edi]
    je .tag
    or bl,2
.tag:
    inc esi
    inc edi
    cmp al,0x79
    je .end
    test al,0x80
    jz .small
    movzx ecx,word [ss:esi]
    cmp cx,[es:edi]
    je .large
    or bl,2
.large:
    add esi,2
    add edi,2
    jmp .bytes
.small:
    and al,7
    movzx ecx,al
.bytes:
    mov al,[ss:esi]
    cmp al,[es:edi]
    je .same
    or bl,1
.same:
    cmp ah,0x2A
    jne .io_info
    cmp cx,1                 ; DMA flags are attributes, not a channel mask.
    je .next
.io_info:
    cmp ah,0x47
    jne .memory_info
    cmp cx,7
    je .next
.memory_info:
    cmp ah,0x86
    jne .numeric
    cmp cx,9
    je .next
.numeric:
    or dl,al
    or bh,[es:edi]
.next:
    inc esi
    inc edi
    loop .bytes
    jmp .descriptor
.end:
    cmp byte [es:edi-1],0x79
    jne .malformed
    xor ax,ax
    test bh,bh
    jnz .nonzero
    test dl,dl
    setnz al                 ; Zero requests ignore tag/attributes, even if enabled.
    jmp .return
.nonzero:
    test bl,2
    jnz .malformed
    mov al,bl
    jmp .return
.malformed:
    mov ax,2
.return:
    pop dx
    pop esi
    pop bx
    ret

%macro pnp_node 5
%define pnp_node_end %1 %+ _end
%define pnp_node_body %1 %+ _body
%1:
    db pnp_node_end-pnp_node_body
pnp_node_body:
    db (%3 >> 8),(%3 & 255)
%deftok %%type %4
    db %%type
    dw %5
%endmacro
%macro pnp_end 0
    db 0x79,0
pnp_node_end:
%endmacro

%ifdef BOARD_PNP_NV6_LATE
PNP_LPT equ 9
%else
PNP_LPT equ 10
%endif
PNP_FDC equ PNP_LPT+1
PNP_IDE equ PNP_LPT+2
PNP_EXTRA equ PNP_IDE+1
%ifdef PB430_PORT
PNP_MOUSE equ PNP_EXTRA+1
PNP_NODE_COUNT equ PNP_EXTRA+2
%elifdef BOARD_PNP_NV6_LATE
PNP_MOUSE equ PNP_EXTRA+1
PNP_NODE_COUNT equ PNP_EXTRA+2
%elif BOARD_ATA_DEVICE_COUNT = 4
PNP_NODE_COUNT equ PNP_EXTRA+1
%else
PNP_NODE_COUNT equ PNP_EXTRA
%endif

%macro pnp_io 2-3 10
%if %1 >= 0x400 || %3 = 16
    db 0x47,1
    dw %1,%1
    db 0,%2
%else
    db 0x4B
    dw %1
    db %2
%endif
%endmacro
%macro pnp_irq 1
    db 0x22
    dw %1
%endmacro
pnp_nodes:
    dw pnp_pic,pnp_timer,pnp_dma,pnp_keyboard,pnp_rtc,pnp_speaker,pnp_board,pnp_isa_bus,pnp_uart_a
%ifndef BOARD_PNP_NV6_LATE
    dw pnp_uart_a
%endif
    dw pnp_lpt,pnp_fdc,pnp_ide
%ifdef PB430_PORT
    dw pnp_vga,pnp_mouse
%elifdef BOARD_PNP_NV6_LATE
    dw pnp_vga,pnp_mouse
%elif BOARD_ATA_DEVICE_COUNT = 4
    dw pnp_pci_bus
%endif

pnp_node pnp_pic,0,0x0000,"0x08,0x00,0x00",3
    pnp_io 0x20,2
    pnp_io 0xA0,2
    pnp_irq 4
pnp_end
pnp_node pnp_timer,1,0x0100,"0x08,0x02,0x00",3
    pnp_io 0x40,4
    pnp_irq 1
pnp_end
pnp_node pnp_dma,2,0x0200,"0x08,0x01,0x00",3
    pnp_io 0,16
    pnp_io 0x80,16
    pnp_io 0xC0,32
    db 0x2A,0x10,2
pnp_end
%ifdef PNP_AUX
pnp_node pnp_keyboard,3,0x0303,"0x09,0x00,0x00",0x0B
%else
pnp_node pnp_keyboard,3,0x0301,"0x09,0x00,0x00",0x0B
%endif
    pnp_io 0x60,1
    pnp_io 0x64,1
    pnp_irq 2
pnp_end
pnp_node pnp_rtc,4,0x0B00,"0x08,0x03,0x00",3
    pnp_io 0x70,2
    pnp_irq 0x100
pnp_end
pnp_node pnp_speaker,5,0x0800,"0x04,0x01,0x00",3
    pnp_io 0x61,1
pnp_end
pnp_node pnp_board,6,0x0C01,"0x08,0x80,0x00",3
    db 0x86,9,0,1
    dd 0,0xA0000
    db 0x86,9,0,1
    dd 0x100000,0
pnp_end
pnp_node pnp_isa_bus,7,0x0A00,"0x06,0x01,0x00",3
pnp_end
%ifdef BOARD_SETUP_READONLY_PAGES
%define PNP_ROUTING_ATTRIBUTE 3
%else
%define PNP_ROUTING_ATTRIBUTE 0
%endif
pnp_node pnp_uart_a,8,0x0500,"0x07,0x00,0x00",PNP_ROUTING_ATTRIBUTE
    pnp_io 0,8
    pnp_irq 0
pnp_end
%if BOARD_ATA_DEVICE_COUNT = 4
pnp_node pnp_lpt,PNP_LPT,0x0401,"0x07,0x01,0x00",PNP_ROUTING_ATTRIBUTE
%else
pnp_node pnp_lpt,PNP_LPT,0x0400,"0x07,0x01,0x00",PNP_ROUTING_ATTRIBUTE
%endif
    pnp_io 0,3
    pnp_irq 0
%if BOARD_ATA_DEVICE_COUNT = 4
    db 0x2A,0,8
    pnp_io 0,0,16
%endif
pnp_end
pnp_node pnp_fdc,PNP_FDC,0x0700,"0x01,0x02,0x00",PNP_ROUTING_ATTRIBUTE | 0x10
    pnp_io 0x3F0,6
    pnp_io 0x3F7,1
    pnp_irq 0x40
    db 0x2A,4,8
pnp_end
pnp_node pnp_ide,PNP_IDE,0x0600,"0x01,0x01,0x00",0x13
    pnp_io 0x1F0,8
    pnp_io 0x3F6,1
    pnp_irq 0x4000
%if BOARD_ATA_DEVICE_COUNT = 4
    pnp_io 0x170,8
    pnp_io 0x376,1
    pnp_irq 0x8000
%endif
pnp_end
%ifdef PB430_PORT
%define PNP_EMBEDDED_VGA 1
%elifdef BOARD_PNP_NV6_LATE
%define PNP_EMBEDDED_VGA 1
%endif
%ifdef PNP_EMBEDDED_VGA
pnp_node pnp_vga,PNP_EXTRA,0x0900,"0x03,0x00,0x00",7
    pnp_io 0x3B0,12
    pnp_io 0x3C0,32
    db 0x86,9,0,1
    dd 0xA0000,0x20000
pnp_end
pnp_node pnp_mouse,PNP_MOUSE,0x0F13,"0x09,0x02,0x00",0
    pnp_irq 0x1000
pnp_end
%elif BOARD_ATA_DEVICE_COUNT = 4
pnp_node pnp_pci_bus,PNP_EXTRA,0x0A03,"0x06,0x00,0x00",3
    pnp_io 0xCF8,8
pnp_end
%endif
