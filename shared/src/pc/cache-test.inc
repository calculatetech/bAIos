; Distinct word-address markers across DL 64-KiB segments. Same failure ABI.
%macro cache_sram_addresses 1-2
    cld
    mov bx,0x1357
    movzx cx,dl
%if %0 == 2
    mov edi,%2
%else
    mov ax,0x1000
    mov es,ax
%endif
%%address_write_segment:
    xor di,di
%%address_write:
%if %0 == 2
    mov [es:edi],bx
%else
    mov [es:di],bx
%endif
    inc bx
    test di,di
    jnz %%address_write_shift
    inc di
%%address_write_shift:
    shl di,1
    jnc %%address_write
%if %0 == 2
    add edi,0x10000
%else
    mov ax,es
    add ax,0x1000
    mov es,ax
%endif
    loop %%address_write_segment
    mov bx,0x1357
    movzx cx,dl
%if %0 == 2
    mov edi,%2
%else
    mov ax,0x1000
    mov es,ax
%endif
%%address_read_segment:
    xor di,di
%%address_read:
%if %0 == 2
    mov ax,[es:edi]
%else
    mov ax,[es:di]
%endif
    cmp ax,bx
    jne %1
    inc bx
    test di,di
    jnz %%address_read_shift
    inc di
%%address_read_shift:
    shl di,1
    jnc %%address_read
%if %0 == 2
    add edi,0x10000
%else
    mov ax,es
    add ax,0x1000
    mov es,ax
%endif
    loop %%address_read_segment
%endmacro

; Flat ES, ESI=cache bytes, EBP=installed RAM end (64-KiB aligned).
; Exercise every cache entry with RAM tags differing by one address bit.
; Only free extended POST RAM is written. Preserve ESI and EBX's upper half.
; Failure: EDI=address, EAX=expected; no stack, calls, I/O or live state.
; shortcut: live conventional RAM is excluded; add a saved low-RAM probe for tag-zero coverage.
%macro cache_tag_patterns 1
    cld
    and ebp,0xFFFF0000
    mov eax,esi
    shr eax,16
    mov bp,ax
%%bit:
    movzx edx,bp
    shl edx,16
    mov edi,0x100000
    cmp edx,0x100000
    jne %%pair
    mov edi,0x200000 ; Exercise A20 without writing conventional firmware RAM.
%%pair:
    xor edx,edi
%%bounds:
    mov eax,ebp
    and eax,0xFFFF0000
    mov ecx,edi
    add ecx,esi
    cmp ecx,eax
    ja %%next
    mov ecx,edx
    add ecx,esi
    cmp ecx,eax
    ja %%next
    mov eax,edi
    shr eax,16
    mov bx,ax
    mov eax,edi
    xor eax,0xA55A3CC3
    mov ecx,esi
    shr ecx,2
    a32 rep stosd
    mov edi,edx
    mov eax,edi
    xor eax,0xA55A3CC3
    mov ecx,esi
    shr ecx,2
    a32 rep stosd
    movzx edi,bx
    shl edi,16
    mov eax,edi
    xor eax,0xA55A3CC3
    mov ecx,esi
    shr ecx,2
    a32 repe scasd
    jne %1
    mov edi,edx
    mov eax,edi
    xor eax,0xA55A3CC3
    mov ecx,esi
    shr ecx,2
    a32 repe scasd
    jne %1
%%next:
    test bp,bp
    jz %%done
    shl bp,1
    jz %%done
    movzx ecx,bp
    shl ecx,16
    mov eax,ebp
    and eax,0xFFFF0000
    cmp ecx,eax
    jb %%bit
    ; Also compare against the last cache-sized region: all upper tag bits.
    mov edx,eax
    sub edx,esi
    lea ecx,[esi+0x100000]
    cmp edx,ecx
    jb %%done
    mov edi,0x100000
    xor bp,bp
    jmp %%bounds
%%done:
%endmacro

; DL=64-KiB SRAM segments. ES:DI is uncached SRAM, never live RAM.
; No stack, calls, I/O or firmware state accesses inside the test window.
; Optional second argument: linear base with a caller-supplied flat ES.
; Failure leaves AX=read, BX=expected, ES:DI (flat: EDI)=bad word.
%macro cache_sram_patterns 1-2
    cld
    ; REP keeps the per-word work inside the CPU instead of fetching ROM loops.
    mov bp,0x55AA
%%pattern:
%if %0 == 2
    mov dh,dl
    mov edi,%2
%else
    movzx ecx,dl
    shl ecx,16
    mov bx,0x1000
%endif
%%write_segment:
%if %0 == 1
    mov es,bx
    xor di,di
%endif
    mov ax,bp
%if %0 == 2
    mov ecx,0x8000
    a32 rep stosw
    dec dh
%else
    mov cx,0x8000
    rep stosw
    add bx,0x1000
    sub ecx,0x10000
%endif
    jnz %%write_segment
%if %0 == 2
    mov dh,dl
    mov edi,%2
%else
    movzx ecx,dl
    shl ecx,16
    mov bx,0x1000
%endif
%%read_segment:
%if %0 == 1
    mov es,bx
    xor di,di
%endif
    mov ax,bp
%if %0 == 2
    mov ecx,0x8000
    a32 repe scasw
%else
    mov cx,0x8000
    repe scasw
%endif
    jne %%data_failed ; ZF also catches a mismatch on the segment's last word.
%if %0 == 2
    dec dh
%else
    add bx,0x1000
    sub ecx,0x10000
%endif
    jnz %%read_segment
    not bp
    cmp bp,0x55AA
    jne %%pattern
%if %0 == 2
    cache_sram_addresses %1,%2
%else
    cache_sram_addresses %1
%endif
    jmp %%done
%%data_failed:
%if %0 == 2
    sub edi,2
    mov ax,[es:edi]
%else
    sub di,2
    mov ax,[es:di]
%endif
    mov bx,bp
    jmp %1
%%done:
%endmacro
