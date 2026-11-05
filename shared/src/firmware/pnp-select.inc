; Replay one complete card stream into the selected LDN's reusable domains.
; ESI=LDN journal address, EDX=source alternative ordinal (FFFFFFFF=no DF).
; The raw stream is never retained, including arbitrary metadata.
P_R_EVENT equ -32
P_R_DOMAIN equ -64
P_R_LDN equ -68
P_R_ALT equ -72
P_R_INDEX equ -74
P_R_TARGET equ -75
P_R_SELECTED equ -76
P_R_CURRENT equ -80
P_R_PORT equ -82

pnp_replay:
    pushad
    push es
    push gs
    mov bp,sp
    sub sp,84
    push ss
    pop es
    mov [ss:bp+P_R_LDN],esi
    mov [ss:bp+P_R_ALT],edx
    call pnp_claim_remove_owner
    mov eax,esi
    call pnp_pointer
    mov al,[gs:si+PNP_LDN_INDEX]
    mov [ss:bp+P_R_TARGET],al
    mov eax,[gs:si+PNP_LDN_CARD]
    call pnp_pointer
    mov al,[gs:si+PNP_CARD_CSN]
    call pnp_isa_key
    push ax
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov dx,[gs:si+PNP_ROOT_READ_PORT]
    mov [ss:bp+P_R_PORT],dx
    pop ax
    call pnp_isa_reopen
    jc .bad
    mov eax,[ss:bp+P_R_LDN]
    call pnp_pointer
    mov byte [gs:si+PNP_LDN_NDOM],0
    mov dword [gs:si+PNP_LDN_COUNTS],0
    mov word [ss:bp+P_R_INDEX],0xFFFF
    mov byte [ss:bp+P_R_SELECTED],0
    mov byte [ss:bp+P_R_EVENT+1],0
.next:
    mov dx,[ss:bp+P_R_PORT]
    lea di,[bp+P_R_EVENT]
    call pnp_resource_next
    jc .bad
    cmp al,0x79
    je .complete
    cmp al,0x15
    je .ldn
    cmp al,0x16
    je .ldn
    cmp al,0x30
    je .alt
    cmp al,0x31
    je .alt
    cmp al,0x38
    je .end_df
    push ss
    pop gs
    lea si,[bp+P_R_DOMAIN]
    call pnp_normalize_event
    jc .bad
    test al,al
    jz .next
    cmp byte [ss:bp+P_R_SELECTED],0
    je .next
    cmp dword [ss:bp+P_R_CURRENT],-1
    je .include
    mov edx,[ss:bp+P_R_ALT]
    cmp edx,[ss:bp+P_R_CURRENT]
    jne .next
.include:
    mov eax,[ss:bp+P_R_LDN]
    call pnp_pointer
    movzx bx,byte [ss:bp+P_R_DOMAIN]
    dec bx
    mov cl,[gs:si+PNP_LDN_COUNTS+bx]
    cmp cl,[cs:pnp_domain_limits+bx]
    jae .bad
    inc byte [gs:si+PNP_LDN_COUNTS+bx]
    mov al,[gs:si+PNP_LDN_NDOM]
    inc byte [gs:si+PNP_LDN_NDOM]
    mov [ss:bp+P_R_DOMAIN+1],cl
    cmp byte [ss:bp+P_R_DOMAIN],3
    jne .origin
    or byte [ss:bp+P_R_DOMAIN+3],0x20
.origin:
    movzx ax,al
    shl ax,5
    add si,ax
    add si,PNP_LDN_DOMAINS
    lea di,[bp+P_R_DOMAIN]
    mov cx,6
.copy:
    mov eax,[es:di]
    mov [gs:si],eax
    add si,4
    add di,4
    loop .copy
    mov dword [gs:si],0
    mov eax,[ss:bp+P_R_LDN]
    mov [gs:si+4],eax
    jmp .next
.ldn:
    inc word [ss:bp+P_R_INDEX]
    mov byte [ss:bp+P_R_SELECTED],0
    mov al,[ss:bp+P_R_INDEX]
    cmp al,[ss:bp+P_R_TARGET]
    jne .reset_df
    mov eax,[ss:bp+P_R_LDN]
    call pnp_pointer
    mov eax,[gs:si+PNP_LDN_ID]
    cmp eax,[es:di+4]
    jne .bad
    mov byte [ss:bp+P_R_SELECTED],1
.reset_df:
    mov dword [ss:bp+P_R_CURRENT],-1
    jmp .next
.alt:
    inc dword [ss:bp+P_R_CURRENT]
    jmp .next
.end_df:
    mov dword [ss:bp+P_R_CURRENT],-1
    jmp .next
.complete:
    mov al,[ss:bp+P_R_INDEX]
    cmp al,[ss:bp+P_R_TARGET]
    jb .bad
    call pnp_isa_wait_key
    mov sp,bp
    pop gs
    pop es
    popad
    clc
    ret
.bad:
    call pnp_isa_wait_key
    mov sp,bp
    pop gs
    pop es
    popad
    stc
    ret
pnp_domain_limits: db 4,8,2,2

; EAX=one reusable domain. Iterate every admitted candidate, querying the
; complete ownership union. The started bit is transient search state only.
pnp_candidate:
    pushad
    push gs
    mov edi,eax
    call pnp_pointer
    test byte [gs:si+3],1
    jnz .null
    cmp byte [gs:si],3
    jae .channel
    mov edx,[gs:si+20]
    test byte [gs:si+3],0x80
    jz .minimum
    add edx,[gs:si+12]
    jc .bad
    jmp .range
.minimum:
    mov eax,[gs:si+4]
    xor edx,edx
    div dword [gs:si+12]
    test edx,edx
    setnz bl
    movzx ebx,bl
    add eax,ebx
    mul dword [gs:si+12]
    test edx,edx
    jnz .bad
    mov edx,eax
.range:
    cmp edx,[gs:si+8]
    ja .bad
    mov ecx,[gs:si+16]
    mov eax,ecx
    dec eax
    add eax,edx
    jc .bad
    cmp byte [gs:si],2
    jne .memory
    cmp eax,0xFFFF
    ja .bad
    jmp .query
.memory:
    test byte [gs:si+3],4
    jnz .width
    cmp eax,0xFFFFFF
    ja .bad
    test dl,dl
    jnz .advance_range       ;24-bit registers expose address bits23:8 only.
    test byte [gs:si+2],4
    jz .width
    cmp eax,0xFFFFFF
    je .bad                 ;24-bit exclusive upper limit must also fit.
.width:
    mov bl,[gs:si+2]
    and bl,0x18
    cmp bl,0x18             ; Keep EAX's inclusive endpoint intact.
    je .bad
    test byte [gs:si+2],4
    jz .mask
    cmp eax,-1
    je .bad                 ; Exclusive upper limit must remain representable.
    jmp .query
.mask:
    mov eax,ecx             ; Mask decoder requires a natural power-of-two window.
    dec eax
    test ecx,eax
    jnz .bad
    test edx,eax
    jz .query
    jmp .advance_range
.query:
    mov ah,[gs:si]
    mov al,[gs:si+2]
    call pnp_claim_query
    jnc .selected
.advance_range:
    add edx,[gs:si+12]
    jnc .range
    jmp .bad
.channel:
    xor edx,edx
    test byte [gs:si+3],0x80
    jz .channel_next
    mov edx,[gs:si+20]
    inc edx
.channel_next:
    cmp edx,16
    jae .bad
    bt [gs:si+4],edx
    jnc .skip_channel
    cmp byte [gs:si],4
    je .dma
    ; Only IRQs physically present on the ISA connector.0/1/8/13 are local.
    mov ax,0xDEFC
    bt ax,dx
    jnc .skip_channel
    and byte [gs:si+3],0xEF
    test byte [gs:si+2],1
    jnz .irq_ready
    ; ISA6.2.2.4 requires advertised high-true edge for ISA compatibility.
    ; Alternate-only types are valid data, with no established host
    ; intersection; try another complete dependent choice instead.
    jmp .skip_channel
.irq_ready:
    push edx
    cmp dl,2
    jne .physical
    mov dl,9
.physical:
    mov ax,0x0300
    mov ecx,1
    call pnp_claim_query
    pop edx
    jnc .selected
    jmp .skip_channel
.dma:
    cmp dl,8
    jae .bad
    cmp dl,4
    je .skip_channel
    mov al,[gs:si+2]
    ; Speed/bus-master describe the device, not a minimum host-cycle demand.
    ; Select compatible AT channel/count semantics without changing timing;
    ; the device driver owns transfer/cascade setup.
    mov bl,al
    and bl,3
    cmp dl,4
    ja .word_dma
    cmp bl,2
    je .skip_channel
    test al,4               ; Bus masters do not execute the8237 count mode.
    jnz .dma_query
    test al,8
    jmp .count
.word_dma:
    test bl,bl
    jz .skip_channel
    test al,4
    jnz .dma_query
    test al,16
.count:
    jz .skip_channel
.dma_query:
    mov ax,0x0400
    mov ecx,1
    call pnp_claim_query
    jnc .selected
.skip_channel:
    inc edx
    jmp .channel_next
.null:
    test byte [gs:si+3],0x80
    jnz .bad
    mov edx,[gs:si+20]       ; DMA null remains its documented unassigned4.
.selected:
    mov [gs:si+20],edx
    or byte [gs:si+3],0x80
    pop gs
    popad
    clc
    ret
.bad:
    and byte [gs:si+3],0x7F
    pop gs
    popad
    stc
    ret

; ESI=LDN. DL=0 first complete placement,1 next complete placement.
; Required-device backtracking reuses these same domains and claims.
pnp_place_ldn:
    pushad
    push gs
    mov bp,sp
    mov ebx,edx
    mov edi,esi
    mov eax,esi
    call pnp_pointer
    movzx ecx,byte [gs:si+PNP_LDN_NDOM]
    xor edx,edx
    test bl,bl
    jz .position
    test ecx,ecx
    jz .bad
    mov edx,ecx
    dec edx
.position:
    mov eax,edi
    call pnp_pointer
    mov [gs:si+PNP_LDN_POSITION],edx
.retry:
    mov esi,edi
    call pnp_claim_remove_owner
    mov eax,edi
    call pnp_pointer
    mov edx,[gs:si+PNP_LDN_POSITION]
    movzx ebx,byte [gs:si+PNP_LDN_NDOM]
    xor ecx,ecx
    lea eax,[edi+PNP_LDN_DOMAINS]
.prefix:
    cmp ecx,edx
    je .candidate
    call pnp_claim_add
    add eax,32
    inc ecx
    jmp .prefix
.candidate:
    cmp edx,ebx
    je .good
    call pnp_candidate
    jnc .forward
    test edx,edx
    jz .bad
    dec edx
    mov eax,edi
    call pnp_pointer
    mov [gs:si+PNP_LDN_POSITION],edx
    jmp .retry
.forward:
    inc edx
    mov eax,edi
    call pnp_pointer
    mov [gs:si+PNP_LDN_POSITION],edx
    jmp .retry
.good:
    pop gs
    popad
    clc
    ret
.bad:
    mov esi,edi
    call pnp_claim_remove_owner
    pop gs
    popad
    stc
    ret
; ESI=LDN, DL=0 first tuple/placement,1 next. Each failed tuple rolls back
; all of its claims before the next priority/source-ordered alternative.
pnp_try_ldn:
    pushad
    push gs
    mov edi,esi
    mov ebx,edx
    mov eax,esi
    call pnp_pointer
    test byte [gs:si+PNP_LDN_STATUS],0x80
    jnz .bad
    mov eax,[gs:si+PNP_LDN_CARD]
    call pnp_pointer
    cmp byte [gs:si+PNP_CARD_STATUS],1
    jne .bad
    mov eax,edi
    call pnp_pointer
    test bl,bl
    jnz .placement
    mov eax,[gs:si+PNP_LDN_ALTS]
    mov [gs:si+PNP_LDN_ALT],eax
.replay:
    mov edx,-1
    mov eax,edi
    call pnp_pointer
    mov eax,[gs:si+PNP_LDN_ALT]
    test eax,eax
    jz .common
    call pnp_pointer
    mov edx,[gs:si+PNP_ALT_ORDINAL]
.common:
    mov esi,edi
    call pnp_replay
    jc .advance
    xor ebx,ebx
.placement:
    mov esi,edi
    mov edx,ebx
    call pnp_place_ldn
    jnc .good
.advance:
    mov eax,edi
    call pnp_pointer
    mov eax,[gs:si+PNP_LDN_ALT]
    test eax,eax
    jz .bad
    call pnp_pointer
    mov ebx,[gs:si+PNP_ALT_NEXT]
    mov eax,edi
    call pnp_pointer
    mov [gs:si+PNP_LDN_ALT],ebx
    test ebx,ebx
    jnz .replay
.bad:
    mov esi,edi
    call pnp_claim_remove_owner
    pop gs
    popad
    stc
    ret
.good:
    pop gs
    popad
    clc
    ret

; Joint required search precedes every optional claimant. If the complete
; required set is infeasible, report individual feasible/inactive results;
; this is a processed configuration, not an incomplete census.
pnp_solve:
    pushad
    push gs
    mov bp,sp
    push word 0             ; phase0=joint,1=required fallback,2=optional.
.begin:
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov edi,[gs:si+PNP_ROOT_LDNS]
    xor edx,edx
.next:
    test edi,edi
    jz .phase_done
    mov eax,edi
    call pnp_pointer
    test byte [gs:si+PNP_LDN_BOOT],1
    setz al
    cmp word [ss:bp-2],2
    je .optional
    test al,al
    jnz .advance
    jmp .try
.optional:
    test al,al
    jz .advance
    ; OS policy leaves optional logical devices inactive.
    cmp byte [fs:C_PNP+PNP_POLICY],0
    jnz .advance
.try:
    mov esi,edi
    call pnp_try_ldn
    jc .failed
    mov eax,edi
    call pnp_pointer
    or byte [gs:si+PNP_LDN_STATUS],1
.advance:
    mov eax,edi
    call pnp_pointer
    mov edi,[gs:si+PNP_LDN_NEXT]
    xor edx,edx
    jmp .next
.failed:
    mov eax,edi
    call pnp_pointer
    and byte [gs:si+PNP_LDN_STATUS],0xFE
    cmp word [ss:bp-2],0
    jne .advance
.backtrack:
    mov edi,[gs:si+PNP_LDN_PREV]
    test edi,edi
    jz .fallback
    mov eax,edi
    call pnp_pointer
    test byte [gs:si+PNP_LDN_STATUS],1
    jz .backtrack
    and byte [gs:si+PNP_LDN_STATUS],0xFE
    mov edx,1
    jmp .try
.fallback:
    inc word [ss:bp-2]
    jmp .begin
.phase_done:
    cmp word [ss:bp-2],1
    jb .optional_begin
    cmp word [ss:bp-2],2
    je .done
.optional_begin:
    mov word [ss:bp-2],2
    jmp .begin
.done:
    mov sp,bp
    pop gs
    popad
    ret
pnp_select_code_end:
