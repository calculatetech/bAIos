; Standard real/protected-mode ESCD ABI; adapters own physical persistence.
pnp_use_escd:
    mov ax,0x8D
    jmp pnp_return
pnp_escd_info:
    mov es,[ss:ebp+44]
    movzx edi,word [ss:ebp+42]
    mov word [es:edi],BOARD_ESCD_CAPACITY
    mov es,[ss:ebp+48]
    movzx edi,word [ss:ebp+46]
    mov word [es:edi],BOARD_ESCD_CAPACITY
    mov es,[ss:ebp+52]
    movzx edi,word [ss:ebp+50]
    mov dword [es:edi],BOARD_ESCD_BASE
    jmp pnp_success
pnp_escd_read:
    mov es,[ss:ebp+44]
    movzx edi,word [ss:ebp+42]
    cmp edi,0xFFF2
    ja pnp_escd_buffer_small
    mov ax,0x42
    jmp pnp_escd_call
pnp_escd_write:
    mov es,[ss:ebp+44]
    movzx edi,word [ss:ebp+42]
    cmp edi,0xFFF2
    ja pnp_escd_buffer_small
    call pnp_escd_header
    test ax,ax
    jnz pnp_return
    ; Sum little-endian WORDs, with an implied zero byte for odd total size.
    push ecx
    sub ecx,2
    xor edx,edx
    xor esi,esi
.checksum:
    movzx eax,byte [es:edi+esi]
    test si,1
    jz .low
    shl ax,8
.low:
    add dx,ax
    inc esi
    loop .checksum
    neg dx
    test si,1
    jz .ready
    xchg dl,dh
.ready:
    pop ecx
    mov ax,0x43
pnp_escd_call:
    mov gs,[ss:ebp+46]
    ; Write supplies validated length CX and canonical final checksum DX.
    call board_escd
    jmp pnp_return
pnp_escd_buffer_small:
    mov ax,0x59
    jmp pnp_return

; ES:EDI header -> length CX, AX=0,56h invalid,5Ah exceeds capacity.
pnp_escd_header:
    movzx ecx,word [es:edi]
    mov ax,0x56
    cmp cx,14
    jb .done
    mov ax,0x5A
    cmp cx,BOARD_ESCD_CAPACITY
    ja .done
    mov edx,edi
    add edx,ecx
    mov ax,0x59
    cmp edx,0x10000
    ja .done
    mov ax,0x56
    cmp dword [es:edi+2],0x47464341
    jne .done
    cmp byte [es:edi+7],2
    jne .done
    xor ax,ax
.done:
    ret

pnp_escd_empty:
    dw 14
    db 'ACFG',0,2,0,0,0,0
    dw 0x736B

; POST's explicit clear request uses the same persistent public writer.
pnp_escd_clear_post:
    pushad
    sub sp,14
    mov di,sp
    mov si,pnp_escd_empty
    mov cx,14
.copy:
    mov al,[cs:si]
    mov [ss:di],al
    inc si
    inc di
    loop .copy
    sub di,14
    push word 0x40
    push word (BOARD_ESCD_BASE >> 4)
    push ss
    push di
    push word 0x43
    call CFG_ROM_CODE_SEGMENT:pnp_real_entry
    add sp,24
    test ax,ax
    popad
    jnz .failed
    clc
    ret
.failed:
    stc
    ret
