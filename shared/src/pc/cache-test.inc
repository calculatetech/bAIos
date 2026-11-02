; Flat DS, exclusive end in %3. Preserve all but EAX/EDX/EDI and flags.
; Failure: EDI=bad dword, EAX=expected; caller reads the observed dword.
; Optional fourth argument invalidates only where the adapter requires it.
%macro cache_address_patterns 3-4
    mov edx,0x55AA55AA
%%pattern:
    mov edi,%2
%%write:
    mov eax,edi
    xor eax,edx
    mov [edi],eax
    add edi,4
    cmp edi,%3
    jb %%write
%if %0 == 4
    %4
%endif
    mov edi,%2
%%check:
    mov eax,edi
    xor eax,edx
    cmp [edi],eax
    jne %1
    add edi,4
    cmp edi,%3
    jb %%check
    not edx
    cmp edx,0x55AA55AA
    jne %%pattern
%endmacro

; Flat ES, ESI=cache bytes, EBP=RAM end in upper 16 bits, %2=cacheable end.
; At most two competing tag pairs; scratch addresses share cache index zero.
; Failure: EDI=bad dword, EAX=expected. No calls, stack, I/O or live state.
%macro cache_tag_witnesses 2
    and ebp,0xFFFF0000
    cmp ebp,%2
    jbe %%begin
    mov ebp,%2
%%begin:
    lea edx,[esi+0x100000]
    xor ecx,ecx
%%pair:
    cmp edx,0x100000
    jbe %%done
    cmp edx,ebp
    jae %%done
    mov edi,0x100000
    mov eax,edi
    xor eax,0xA55A3CC3
    mov [es:edi],eax
    mov edi,edx
    mov eax,edi
    xor eax,0xA55A3CC3
    mov [es:edi],eax
    mov edi,0x100000
    mov eax,edi
    xor eax,0xA55A3CC3
    cmp [es:edi],eax
    jne %1
    mov edi,edx
    mov eax,edi
    xor eax,0xA55A3CC3
    cmp [es:edi],eax
    jne %1
    inc ecx
    cmp ecx,2
    je %%done
    mov edx,ebp
    dec edx
    mov eax,esi
    neg eax
    and edx,eax
    lea eax,[esi+0x100000]
    cmp edx,eax
    je %%done
    jmp %%pair
%%done:
%endmacro

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
