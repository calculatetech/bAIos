; Cyrix Detection Guide1997: ZF means Cyrix; AX/BX and flags are scratch.
%macro mp_cyrix_test 0
    xor ax,ax
    sahf
    mov ax,5
    mov bx,2
    div bl
    lahf
    cmp ah,2
%endmacro

; Cyrix NO_CACHE.EXE1.5: complete off policy before any MCU map changes.
; No RAM stack exists here. UpperESP retains the reset identity.
%macro mp_cpu_holdoff 0
    mp_cyrix_test
    jne %%done
    invd
    jmp short $+2
    mov al,0xC0
    out 0x22,al
    xor al,al
    out 0x23,al
    mov al,0xC1
    out 0x22,al
    xor al,al
    out 0x23,al
%assign mp_ncr 0xC4
%rep 12
    mov al,mp_ncr
    out 0x22,al
%if mp_ncr = 0xC6
    mov al,0x0F
%else
    xor al,al
%endif
    out 0x23,al
%assign mp_ncr mp_ncr+1
%endrep
    invd
    jmp short $+2
%%done:
%endmacro
