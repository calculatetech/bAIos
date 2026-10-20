; DL=64-KiB SRAM segments. ES:DI is uncached SRAM, never live RAM.
; No stack, calls, I/O or firmware state accesses inside the test window.
; Failure leaves AX=read, BX=expected, ES:DI=bad word. SCAS needs a reread.
%macro cache_sram_patterns 1
    ; REP keeps the per-word work inside the CPU instead of fetching ROM loops.
    mov bp,0x55AA
%%pattern:
    movzx ecx,dl
    shl ecx,16
    mov bx,0x1000
%%write_segment:
    mov es,bx
    xor di,di
    mov ax,bp
    mov cx,0x8000
    rep stosw
    add bx,0x1000
    sub ecx,0x10000
    jnz %%write_segment
    movzx ecx,dl
    shl ecx,16
    mov bx,0x1000
%%read_segment:
    mov es,bx
    xor di,di
    mov ax,bp
    mov cx,0x8000
    repe scasw
    jne %%data_failed ; ZF also catches a mismatch on the segment's last word.
    add bx,0x1000
    sub ecx,0x10000
    jnz %%read_segment
    not bp
    cmp bp,0x55AA
    jne %%pattern
    ; Distinct markers at every word-address bit, retained across all segments.
    mov bx,0x1357
    movzx cx,dl
    mov ax,0x1000
    mov es,ax
%%address_write_segment:
    xor di,di
%%address_write:
    mov [es:di],bx
    inc bx
    test di,di
    jnz %%address_write_shift
    inc di
%%address_write_shift:
    shl di,1
    jnc %%address_write
    mov ax,es
    add ax,0x1000
    mov es,ax
    loop %%address_write_segment
    mov bx,0x1357
    movzx cx,dl
    mov ax,0x1000
    mov es,ax
%%address_read_segment:
    xor di,di
%%address_read:
    mov ax,[es:di]
    cmp ax,bx
    jne %1
    inc bx
    test di,di
    jnz %%address_read_shift
    inc di
%%address_read_shift:
    shl di,1
    jnc %%address_read
    mov ax,es
    add ax,0x1000
    mov es,ax
    loop %%address_read_segment
    jmp %%done
%%data_failed:
    sub di,2
    mov ax,[es:di]
    mov bx,bp
    jmp %1
%%done:
%endmacro
