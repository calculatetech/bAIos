; ISA PnP1.0a section6 resource framing. POST only; ES:DI owns a21-byte
; streaming event: tag0, running checksum1, length2, known payload4..20.
; DX is the selected ISA read port. Clear checksum before the first event.
; Metadata is consumed by its full declared length and is never cached.
; CF means malformed framing, bad nonzero End checksum, or hardware timeout.
; The allocation/census owner interprets complete events before activation.

pnp_stream_byte:
    call pnp_isa_resource_byte
    jc .done
    add [es:di+1],al
    clc
.done:
    ret

pnp_resource_next:
    push bx
    push cx
    push esi
    push edi
    movzx edi,di
    call pnp_stream_byte
    jc .bad
    mov [es:di],al
    xor cx,cx
    test al,0x80
    jnz .large
    mov cl,al
    and cl,7
    mov bl,al
    and bl,0xF8
    cmp bl,0x70              ; Vendor-defined small metadata.
    je .metadata
    jmp .length
.large:
    call pnp_stream_byte
    jc .bad
    mov cl,al
    call pnp_stream_byte
    jc .bad
    mov ch,al
    mov al,[es:di]
    cmp al,0x82              ; ANSI and vendor strings have full16-bit lengths.
    je .metadata
    cmp al,0x84
    je .metadata
    cmp al,0x83
    jne .length
    cmp cx,2                 ; Unicode includes a language identifier word.
    jb .bad
    test cl,1
    jnz .bad
.metadata:
    mov [es:di+2],cx
    xor bx,bx
    jmp .data
.length:
    mov al,[es:di]
    mov si,pnp_resource_lengths
.find:
    mov bl,[cs:si]
    test bl,bl
    jz .bad
    cmp al,bl
    je .matched
    add si,2
    jmp .find
.matched:
    cmp cl,[cs:si+1]
    jne .bad
    test ch,ch
    jnz .bad
    mov [es:di+2],cx
    mov bx,1
.data:
    xor esi,esi
    jcxz .complete
.byte:
    call pnp_stream_byte
    jc .bad
    test bx,bx
    jz .skip
    mov [es:edi+esi+4],al
.skip:
    inc si
    loop .byte
.complete:
    cmp byte [es:di],0x79
    jne .good
    cmp byte [es:di+4],0
    je .good                 ; Zero checksum explicitly opts out of validation.
    cmp byte [es:di+1],0
    jne .bad
.good:
    mov al,[es:di]
    pop edi
    pop esi
    pop cx
    pop bx
    clc
    ret
.bad:
    pop edi
    pop esi
    pop cx
    pop bx
    stc
    ret

; Exact known payload lengths. Distinct optional forms remain distinct tags.
pnp_resource_lengths:
    db 0x0A,2,0x15,5,0x16,6,0x1C,4,0x22,2,0x23,3,0x2A,2
    db 0x30,0,0x31,1,0x38,0,0x47,7,0x4B,3,0x79,1
    db 0x81,9,0x85,17,0x86,9,0

; Normalize one known resource event at ES:DI into the fixed24-byte domain
; at GS:SI. Fields: kind/ordinal/info/flags, minimum, maximum, alignment,
; length, selected value. Kinds1/2/3/4=memory/I/O/IRQ/DMA; kind0=metadata.
; Flags bit0=null filler, bit2=32-bit memory register family. Null descriptors
; still owe their hardware ordinal. Unsupported host capabilities are resolved
; by selection, not falsely classified as malformed descriptor framing here.
pnp_normalize_event:
    pushad
    xor eax,eax
    xor bx,bx
.zero:
    mov [gs:si+bx],eax
    add bx,4
    cmp bx,24
    jb .zero
    mov al,[es:di]
    cmp al,0x47
    je .io
    cmp al,0x4B
    je .fixed_io
    cmp al,0x22
    je .irq
    cmp al,0x23
    je .irq
    cmp al,0x2A
    je .dma
    cmp al,0x81
    je .memory
    cmp al,0x85
    je .memory
    cmp al,0x86
    je .memory
    jmp .good
.io:
    mov al,[es:di+4]
    test al,0xFE
    jnz .bad
    mov [gs:si+2],al
    movzx eax,word [es:di+5]
    movzx ebx,word [es:di+7]
    movzx ecx,byte [es:di+9]
    movzx edx,byte [es:di+10]
    jmp .io_range
.fixed_io:
    movzx eax,word [es:di+4]
    cmp ax,0x400
    jae .bad
    mov ebx,eax
    mov ecx,1
    movzx edx,byte [es:di+6]
.io_range:
    mov byte [gs:si],2
    jmp .range
.irq:
    mov byte [gs:si],3
    movzx eax,word [es:di+4]
    mov [gs:si+4],eax
    test eax,eax
    jz .null_irq
    mov al,1                 ; Omitted information means high-true edge.
    cmp word [es:di+2],3
    jne .irq_info
    mov al,[es:di+6]
.irq_info:
    test al,0xF0
    jnz .bad
    jmp .channel_info
.dma:
    mov byte [gs:si],4
    movzx eax,byte [es:di+4]
    mov [gs:si+4],eax
    mov dword [gs:si+20],4    ; Documented unassigned DMA encoding.
    test eax,eax
    jz .null_channel
    mov al,[es:di+5]
    test al,0x80
    jnz .bad
    mov ah,al
    and ah,3
    cmp ah,3
    je .bad
.channel_info:
    mov [gs:si+2],al
    cmp dword [gs:si+4],0
    jne .good
    mov byte [gs:si+3],1
    jmp .good
.null_irq:
    mov byte [gs:si+2],1     ; Clarification: null IRQ always programs type02.
.null_channel:
    mov byte [gs:si+3],1     ; Mask zero ignores every other descriptor field.
    jmp .good
.memory:
    mov byte [gs:si],1
    cmp al,0x81
    jne .null_wide_check
    cmp word [es:di+11],0
    je .null_range
    jmp .memory_info
.null_wide_check:
    mov byte [gs:si+3],4
    cmp al,0x86
    jne .null_variable_check
    cmp dword [es:di+9],0
    je .null_range
    jmp .memory_info
.null_variable_check:
    cmp dword [es:di+17],0
    je .null_range
.memory_info:
    mov bl,[es:di+4]
    test bl,0x80
    jnz .bad
    mov [gs:si+2],bl
    cmp al,0x81
    jne .wide_memory
    and bl,0x18
    cmp bl,0x18              ;24-bit information has no32-bit transfer mode.
    je .bad
    movzx eax,word [es:di+5]
    shl eax,8
    movzx ebx,word [es:di+7]
    shl ebx,8
    movzx ecx,word [es:di+9] ; Alignment is bytes, not256-byte units.
    test ecx,ecx
    jnz .mem24_alignment
    mov ecx,0x10000
.mem24_alignment:
    movzx edx,word [es:di+11]
    shl edx,8
    jmp .range
.wide_memory:
    mov byte [gs:si+3],4
    mov eax,[es:di+5]
    cmp byte [es:di],0x86
    je .fixed_memory
    mov ebx,[es:di+9]
    mov ecx,[es:di+13]
    mov edx,[es:di+17]
    jmp .range
.fixed_memory:
    mov ebx,eax
    mov ecx,1
    mov edx,[es:di+9]
.range:
    cmp eax,ebx
    ja .bad
    test ecx,ecx
    jnz .alignment
    inc ecx
.alignment:
    mov [gs:si+4],eax
    mov [gs:si+8],ebx
    mov [gs:si+12],ecx
    mov [gs:si+16],edx
    test edx,edx
    jnz .good
    or byte [gs:si+3],1
    jmp .good
.null_range:
    or byte [gs:si+3],1
    mov dword [gs:si+12],1
.good:
    mov al,[gs:si]
    mov bp,sp
    mov [ss:bp+28],al
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

; ES:DI points to an EISA product ID. Only the three compressed letters are
; constrained; duplicate product IDs remain distinct card/LDN identities.
pnp_eisa_id_valid:
    push ax
    push bx
    push cx
    mov ax,[es:di]
    xchg al,ah
    test ax,0x8000
    jnz .bad
    mov cx,3
.letter:
    mov bx,ax
    and bx,31
    dec bx
    cmp bx,25
    ja .bad
    shr ax,5
    loop .letter
    pop cx
    pop bx
    pop ax
    clc
    ret
.bad:
    pop cx
    pop bx
    pop ax
    stc
    ret
pnp_resource_code_end:
