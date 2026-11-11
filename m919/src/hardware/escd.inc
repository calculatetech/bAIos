%macro escd_probe_stage 1
%ifdef PNP_ESCD_WRITE_PROBE
    mov byte [ss:ebx+56],%1
%endif
%endmacro
; Two independent erase blocks retain the previous committed database.
; Unlock cycles use padding in both blocks, never code, a header, or ESCD data.
ESCD_HEADER_A equ 0xA000
ESCD_DATA_A equ 0x8000
ESCD_HEADER_B equ 0xC000
ESCD_DATA_B equ 0xE000
ESCD_COMMAND equ 0xBFFE
ESCD_UNLOCK1 equ 0xD555
ESCD_UNLOCK2 equ 0xAAAA

; ES:EDI caller buffer, GS caller's E0000 selector; AX=42h/43h.
; All private working state is below the public caller's stack frame.
board_escd:
    cmp word [ss:ebp+PNP_REAL_CALL],1
    jne .protected
    smsw si
    test si,1
    jz board_escd_native
    ; V86 has no cache/CR0 privilege. Reuse the accepted software-SMI gateway.
    push fs
    push ax
    mov ax,0x40
    mov fs,ax
    mov ax,[fs:0x0E]
    mov fs,ax
    cmp byte [fs:HW_SMM_STATUS],1
    pop ax
    pop fs
    jne .unavailable
    mov si,es
    movzx esi,si
    shl esi,4
    add esi,edi
    sub ax,0x3E                ; 42h/43h -> read/write SMI commands4/5.
    m919_smm_command_code 2
    test ax,ax
    jz .return
.unavailable:
    mov ax,0x55
.return:
    ret
.protected:
    mov si,cs
    test si,3
    jnz .unavailable
board_escd_native:
    sub esp,192
    lea ebx,[ebp-PNP_FRAME-2-192]
    mov [ss:ebx],ax
    mov word [ss:ebx+2],0x55
    mov byte [ss:ebx+44],0
    mov [ss:ebx+50],dx
    mov [ss:ebx+52],cx
    mov [ss:ebx+20],edi
%ifdef PNP_ESCD_WRITE_PROBE
    mov dword [ss:ebx+56],0xFFFF0001
    mov word [ss:ebx+60],0xFFFF
%endif
    call board_escd_open
    call board_escd_select
    cmp word [ss:ebx],0x43
    je .write
    movzx esi,word [ss:ebx+26]
    movzx ecx,word [ss:ebx+28]
    cmp word [ss:ebx+24],0xFFFF
    jz .empty
    mov eax,edi
    add eax,ecx
    cmp eax,0x10000
    ja .small
.read:
    mov al,[gs:esi]
    mov [es:edi],al
    inc esi
    inc edi
    loop .read
    jmp .success
.empty:
    mov si,pnp_escd_empty
    mov cx,14
.seed:
    mov al,[cs:si]
    mov [es:edi],al
    inc si
    inc edi
    loop .seed
    jmp .success
.write:
    movzx esi,word [ss:ebx+26]
    mov ax,[ss:ebx+28]
    cmp word [ss:ebx+24],0xFFFF
    jne .compare_size
    mov ax,14
.compare_size:
    cmp ax,[ss:ebx+52]
    jne .changed
    xor edx,edx
.same_byte:
    call board_escd_input_byte
    cmp word [ss:ebx+24],0xFFFF
    je .same_seed
    cmp al,[gs:esi+edx]
    jne .changed
    jmp .same_next
.same_seed:
    cmp al,[cs:pnp_escd_empty+edx]
    jne .changed
.same_next:
    inc dx
    cmp dx,[ss:ebx+52]
    jb .same_byte
    jmp .success
.changed:
    escd_probe_stage 2
    call board_escd_identify
    test al,al
    jz .done
    mov [ss:ebx+44],al
    mov word [ss:ebx+36],ESCD_HEADER_A
    mov word [ss:ebx+38],ESCD_DATA_A
    mov word [ss:ebx+40],0x8000
    cmp word [ss:ebx+24],ESCD_HEADER_A
    jne .target
    mov word [ss:ebx+36],ESCD_HEADER_B
    mov word [ss:ebx+38],ESCD_DATA_B
    mov word [ss:ebx+40],0xC000
.target:
    mov eax,[ss:ebx+32]
    inc eax
    mov [ss:ebx+54],eax
    cmp byte [ss:ebx+44],1
    jne .invalidate
    escd_probe_stage 3
    movzx esi,word [ss:ebx+40]
    mov byte [gs:ESCD_COMMAND],0x20
    mov byte [gs:esi],0xD0
    call board_escd_erase_wait
    jc .done
    mov ecx,0x4000
.erased:
    cmp byte [gs:esi],0xFF
    jne .done
    inc esi
    loop .erased
    jmp .payload
.invalidate:
    escd_probe_stage 4
    call board_escd_blank_page
    movzx esi,word [ss:ebx+36]
    call board_escd_page
    jc .done
.payload:
    escd_probe_stage 5
    xor edx,edx
    mov word [ss:ebx+48],0
    movzx esi,word [ss:ebx+38]
.next_page:
    call board_escd_blank_page
    xor ecx,ecx
.fill:
    cmp dx,[ss:ebx+52]
    jae .filled
    call board_escd_input_byte
    mov [ss:ebx+ecx+64],al
    movzx eax,al
    add [ss:ebx+48],ax
    inc edx
    inc cx
    cmp cx,128
    jb .fill
.filled:
    push edx
    call board_escd_page
    pop edx
    jc .done
    add esi,128
    cmp dx,[ss:ebx+52]
    jb .next_page
    escd_probe_stage 6
    call board_escd_blank_page
    mov dword [ss:ebx+64],0x43534542
    mov eax,[ss:ebx+54]
    mov [ss:ebx+68],eax
    not eax
    mov [ss:ebx+72],eax
    mov ax,[ss:ebx+52]
    mov [ss:ebx+76],ax
    mov ax,[ss:ebx+48]
    mov [ss:ebx+78],ax
    mov word [ss:ebx+80],0x5AA5
    movzx esi,word [ss:ebx+36]
    call board_escd_page
    jc .done
    escd_probe_stage 7
    mov si,[ss:ebx+36]
    mov di,[ss:ebx+38]
    call board_escd_valid
    jc .done
.success:
    mov word [ss:ebx+2],0
    jmp .done
.small:
    mov word [ss:ebx+2],0x59
 .done:
    call board_escd_close
%ifdef PNP_ESCD_WRITE_PROBE
    cmp word [ss:ebx],0x43
    jne .probe_done
    smsw ax
    test al,1
    jnz .probe_done
    push fs
    mov ax,0x40
    mov fs,ax
    mov ax,[fs:0x0E]
    mov fs,ax
    mov al,[ss:ebx+56]
    mov ah,[ss:ebx+2]
    mov [fs:0x1048],ax
    mov eax,[ss:ebx+58]
    mov [fs:0x104A],eax
    mov word [fs:0x1046],0x5045
    pop fs
.probe_done:
%endif
    mov ax,[ss:ebx+2]
    add esp,192
    ret

board_escd_input_byte:
    mov ax,[ss:ebx+52]
    sub ax,2
    cmp dx,ax
    jb .ordinary
    je .low
    mov al,[ss:ebx+51]
    ret
.low:
    mov al,[ss:ebx+50]
    ret
.ordinary:
    mov edi,[ss:ebx+20]
    mov al,[es:edi+edx]
    ret

board_escd_select:
    mov dword [ss:ebx+24],0x0000FFFF
    mov word [ss:ebx+28],0
    mov dword [ss:ebx+32],0
    mov si,ESCD_HEADER_A
    mov di,ESCD_DATA_A
    call board_escd_valid
    jc .second
    mov [ss:ebx+24],si
    mov [ss:ebx+26],di
    mov [ss:ebx+28],cx
    mov [ss:ebx+32],eax
.second:
    mov si,ESCD_HEADER_B
    mov di,ESCD_DATA_B
    call board_escd_valid
    jc .done
    cmp word [ss:ebx+24],0xFFFF
    je .use
    mov edx,eax
    sub edx,[ss:ebx+32]
    jle .done
.use:
    mov [ss:ebx+24],si
    mov [ss:ebx+26],di
    mov [ss:ebx+28],cx
    mov [ss:ebx+32],eax
.done:
    mov edi,[ss:ebx+20]
    ret

; SI header, DI data; return generation EAX and length CX, CF invalid.
board_escd_valid:
    cmp dword [gs:si],0x43534542
    jne .bad
    cmp word [gs:si+16],0x5AA5
    jne .bad
    mov eax,[gs:si+4]
    mov edx,[gs:si+8]
    not edx
    cmp eax,edx
    jne .bad
    push es
    push gs
    pop es
    push eax
    movzx edi,di
    call pnp_escd_header
    test ax,ax
    pop eax
    pop es
    jne .bad
    cmp cx,[gs:si+12]
    jne .bad
    push eax
    push ecx
    push edi
    xor edx,edx
.sum:
    movzx eax,byte [gs:di]
    add dx,ax
    inc di
    loop .sum
    pop edi
    pop ecx
    pop eax
    cmp dx,[gs:si+14]
    jne .bad
    clc
    ret
.bad:
    stc
    ret

board_escd_blank_page:
    mov ecx,32
.fill:
    mov dword [ss:ebx+ecx*4+60],0xFFFFFFFF
    loop .fill
    ret

; Writes and verifies one complete page from caller SS scratch to GS:ESI.
board_escd_page:
    push esi
    cmp byte [ss:ebx+44],2
    jne .bytes
    mov byte [gs:ESCD_UNLOCK1],0xAA
    mov byte [gs:ESCD_UNLOCK2],0x55
    mov byte [gs:ESCD_UNLOCK1],0xA0
    xor edi,edi
.sst:
    mov al,[ss:ebx+edi+64]
    mov [gs:esi+edi],al
    inc edi
    cmp di,128
    jb .sst
    add esi,127
    call board_escd_poll
    jc .failed
    jmp .verify
.bytes:
    xor edi,edi
.mx:
    mov al,[ss:ebx+edi+64]
    cmp al,0xFF
    je .advance
    mov byte [gs:ESCD_COMMAND],0x40
    mov [gs:esi],al
    call board_escd_poll
    jc .failed
.advance:
    inc esi
    inc di
    cmp di,128
    jb .mx
.verify:
    pop esi
    push esi
    xor edi,edi
.compare:
    mov al,[ss:ebx+edi+64]
    cmp al,[gs:esi+edi]
    jne .failed
    inc di
    cmp di,128
    jb .compare
    pop esi
    clc
    ret
.failed:
    pop esi
    stc
    ret

; DQ6 must stop toggling before exact data readback can accept a write.
board_escd_poll:
    push ecx
    push edx
    push ebp
    ; Refresh request toggles every15us independently of CLI and CPU speed.
    mov ecx,700000
    in al,0x61
    mov dl,al
    mov ebp,0x1000000
.again:
    mov al,[gs:esi]
    mov ah,[gs:esi]
    xor al,ah
    test al,0x40
    jz .ready
    in al,0x61
    xor al,dl
    test al,0x10
    jz .no_edge
    xor dl,0x10
    dec ecx
    jz .timeout
.no_edge:
    dec ebp
    jnz .again
.timeout:
    pop ebp
    pop edx
    pop ecx
    stc
    ret
.ready:
    pop ebp
    pop edx
    pop ecx
    clc
    ret
board_escd_erase_wait:
    push ecx
    mov ecx,16
    call board_escd_delay_edges
    pop ecx
    jc .done
    jmp board_escd_poll
.done:
    ret

; Refresh bit edges give bounded waits while interrupts are disabled.
board_escd_delay_edges:
    push ax
    push edx
.delay:
    in al,0x61
    mov ah,al
    mov edx,0x100000
.edge:
    in al,0x61
    xor al,ah
    test al,0x10
    jnz .next
    dec edx
    jnz .edge
    pop edx
    pop ax
    stc
    ret
.next:
    loop .delay
    pop edx
    pop ax
    clc
    ret

board_escd_identify:
    mov byte [gs:ESCD_COMMAND],0x90
    ; The x8 flash exposes its IDs as separate byte reads at chip offsets 0 and 1.
    mov al,[gs:0]
    cmp al,0xC2
    jne .device
    ; UniFlash also resets and re-enters ID mode between Macronix ID bytes.
    mov byte [gs:ESCD_COMMAND],0xFF
    mov byte [gs:ESCD_COMMAND],0xFF
    mov ecx,68
    call board_escd_delay_edges
    jc .id_timeout
    mov byte [gs:ESCD_COMMAND],0x90
    mov ecx,5
    call board_escd_delay_edges
    jc .id_timeout
.device:
    mov ah,[gs:1]
.mx_id:
%ifdef PNP_ESCD_WRITE_PROBE
    mov [ss:ebx+58],ax
%endif
    cmp ax,0x1AC2
    jne .sst
    mov byte [gs:ESCD_COMMAND],0xFF
    mov byte [gs:ESCD_COMMAND],0xFF
    mov al,1
    ret
.id_timeout:
    mov ah,0xFF
    jmp .mx_id
.sst:
    mov byte [gs:ESCD_COMMAND],0xFF
    mov byte [gs:ESCD_COMMAND],0xFF
    mov byte [gs:ESCD_UNLOCK1],0xAA
    mov byte [gs:ESCD_UNLOCK2],0x55
    mov byte [gs:ESCD_UNLOCK1],0x90
    mov cl,[gs:0]
    mov ch,[gs:1]
%ifdef PNP_ESCD_WRITE_PROBE
    mov [ss:ebx+60],cx
%endif
    mov byte [gs:ESCD_UNLOCK1],0xAA
    mov byte [gs:ESCD_UNLOCK2],0x55
    mov byte [gs:ESCD_UNLOCK1],0xF0
    xor al,al
    cmp cx,0x07BF
    jne .done
    mov al,2
.done:
    ret

board_escd_open:
    mov dx,0xCF8
    in eax,dx
    mov [ss:ebx+4],eax
    mov eax,cr0
    mov [ss:ebx+8],eax
    ; The RTC has no readable index/NMI latch; use the existing runtime policy.
    mov al,0x80 | RTC_NMI_SELECT_MASK | 0x0D
    out 0x70,al
    smm_read SMM_SB,0xA0
    mov [ss:ebx+17],al
    xor al,al
    out dx,al
    smm_read SMM_SB,0xA3
    mov [ss:ebx+18],al
    and al,0x3F
    out dx,al
    wbinvd
    mov eax,[ss:ebx+8]
    or eax,0x60000000
    mov cr0,eax
    smm_read SMM_SB,0x47
    mov [ss:ebx+15],al
    and al,0xBF
    out dx,al
    smm_read SMM_SB,0x57
    mov [ss:ebx+16],al
    or al,0x24
    out dx,al
    smm_read SMM_HB,0x54
    mov [ss:ebx+13],al
    and al,0xFE
    out dx,al
    smm_read SMM_HB,0x55
    mov [ss:ebx+14],al
    and al,0xEF
    or al,0x40
    out dx,al
    ret

board_escd_close:
    cmp byte [ss:ebx+44],1
    jne .sst
    mov byte [gs:ESCD_COMMAND],0xFF
    mov byte [gs:ESCD_COMMAND],0xFF
    jmp .restore
.sst:
    cmp byte [ss:ebx+44],2
    jne .restore
    mov byte [gs:ESCD_UNLOCK1],0xAA
    mov byte [gs:ESCD_UNLOCK2],0x55
    mov byte [gs:ESCD_UNLOCK1],0xF0
.restore:
    smm_write SMM_HB,0x55,[ss:ebx+14]
    smm_write SMM_HB,0x54,[ss:ebx+13]
    smm_write SMM_SB,0x57,[ss:ebx+16]
    smm_write SMM_SB,0x47,[ss:ebx+15]
    wbinvd
    mov eax,[ss:ebx+8]
    mov cr0,eax
    smm_write SMM_SB,0xA0,[ss:ebx+17]
    smm_write SMM_SB,0xA3,[ss:ebx+18]
    mov al,RTC_NMI_SELECT_MASK | 0x0D
    out 0x70,al
    mov eax,[ss:ebx+4]
    mov dx,0xCF8
    out dx,eax
    ret
