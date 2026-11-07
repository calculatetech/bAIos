; ISA PnP 1.0a sections3.3,4.4,4.5 and Appendix A/B.
; POST-only byte transport. The caller owns CSN census, resource parsing and
; read-port selection; no persistent settings or public snapshot are modified.
; DX is an admitted xx3 read port in0203h..03FFh. ES:DI is a nine-byte identity
; buffer for serial isolation. Internal entry points preserve unspecified regs.

; AL=register, AH=value; preserve AX/DX.
pnp_isa_write:
    push ax
    push dx
    mov dx,0x279
    out dx,al
    mov dx,0xA79
    mov al,ah
    out dx,al
    pop dx
    pop ax
    ret

; AL=selected logical register, DX=read port; AL=value.
pnp_isa_read:
    push dx
    mov dx,0x279
    out dx,al
    pop dx
    in al,dx
    ret

pnp_isa_key:
    push ax
    push cx
    push dx
    mov dx,0x279
    xor ax,ax
    out dx,al
    out dx,al
    mov al,0x6A
    mov cx,32
.byte:
    out dx,al
    mov ah,al
    shr al,1
    xor ah,al
    and ah,1
    shl ah,7
    or al,ah
    loop .byte
    pop dx
    pop cx
    pop ax
    ret

pnp_isa_reset:
    call pnp_isa_key
    push ax
    mov ax,0x0502             ; Reset CSNs and logical-device power-up state.
    call pnp_isa_write
    pop ax
    jmp pnp_delay_2ms

pnp_isa_wake_zero:
    push ax
    mov ax,3
    call pnp_isa_write
    pop ax
    ret

; Write the full port bits9:2, not its low byte.
pnp_isa_read_port:
    push ax
    mov ax,dx
    shr ax,2
    mov ah,al
    xor al,al
    call pnp_isa_write
    pop ax
    ret

; CF=invalid/no identity. AH=1 if any exact55/AA response, otherwise0.
; A silent64-bit identifier needs no checksum reads (ISA3.3.2).
pnp_isa_isolate:
    pushad
    mov bp,di
    xor ax,ax
    mov cx,9
    rep stosb
    mov di,bp
    push dx
    mov dx,0x279
    mov al,1
    out dx,al
    pop dx
    call pnp_delay_1ms        ; At least1ms before the first pair.
    mov bx,0x006A            ; BL checksum, BH records any exact55/AA pair.
    xor si,si
    mov cx,72
.bit:
    in al,dx
    mov ah,al
    in al,dx
    cmp ah,0x55
    jne .zero
    cmp al,0xAA
    jne .zero
    mov ah,1
    mov bh,1
    jmp .value
.zero:
    xor ah,ah
.value:
    cmp si,64
    jae .store
    mov al,bl
    shr al,1
    xor al,bl
    xor al,ah
    and al,1
    shr bl,1
    shl al,7
    or bl,al
.store:
    shr ah,1
    rcr byte [es:di],1        ; Stream order is bit0 first, across all72 bits.
    inc si
    test si,7
    jnz .delay
    inc di
.delay:
    cmp si,64
    jne .continue
    test bh,bh
    jz .bad
.continue:
    dec cx
    jz .isolated
    call pnp_delay_250us
    jmp .bit
.isolated:
    test bh,bh
    jz .bad
    cmp bl,[es:di-1]
    jne .bad
    call .response
    popad
    clc
    ret
.bad:
    call .response
    popad
    stc
    ret
.response:
    mov bp,sp
    mov [ss:bp+31],bh         ; Saved EAX.AH, accounting for this CALL's return.
    ret

; AL=byte, CF=per-byte readiness timeout.
pnp_isa_resource_byte:
    push cx
    mov cx,100               ;200ms hardware timeout, never a stream-size bound.
.status:
    push dx
    mov dx,0x279
    mov al,5
    out dx,al
    pop dx
    in al,dx
    test al,1
    jnz .ready
    call pnp_delay_2ms
    loop .status
    stc
    pop cx
    ret
.ready:
    push dx
    mov dx,0x279
    mov al,4
    out dx,al
    pop dx
    in al,dx
    clc
    pop cx
    ret

; AL=assigned CSN; skip nine bytes, not its checksum.
pnp_isa_reopen:
    push ax
    push cx
    mov ah,al
    mov al,3
    call pnp_isa_write
    mov cx,9
.prefix:
    call pnp_isa_resource_byte
    jc .done
    loop .prefix
.done:
    pop cx
    pop ax
    ret

pnp_isa_wait_key:
    push ax
    mov ax,0x0202
    call pnp_isa_write
    pop ax
    ret
pnp_delay_250us:
    push dx
    mov dx,299              ; ceil(1193182*250us).
    jmp pnp_delay_entry
pnp_delay_1ms:
    push dx
    mov dx,1194
    jmp pnp_delay_entry
pnp_delay_2ms:
    push dx
    mov dx,2387
pnp_delay_entry:
    call pnp_delay_ticks
    pop dx
    ret

; Same latched PIT subtraction algorithm as the existing house KBC owner;
; private PnP durations do not change the unrelated KBC wait implementation.
pnp_delay_ticks:
    push ax
    push bx
    push cx
    push dx
    call pnp_pit_sample
    mov bx,ax
.wait:
    call pnp_pit_sample
    mov cx,bx
    sub bx,ax
    jb .wrapped
    sub dx,bx
    jmp .sampled
.wrapped:
    sub dx,cx
.sampled:
    mov bx,ax
    jae .wait
    pop dx
    pop cx
    pop bx
    pop ax
    ret
pnp_pit_sample:
    pushf
    cli
    xor al,al
    out 0x43,al
    in al,0x40
    mov ah,al
    in al,0x40
    xchg al,ah
    ; All board timer owners select mode3 (36h): count falls by two per
    ; input clock. Return its half-count phase, including the normal wrap.
    shr ax,1
    popf
    ret
pnp_isa_code_end:
