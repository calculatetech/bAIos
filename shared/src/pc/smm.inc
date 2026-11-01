%ifndef PC_SMM_SERVICES
%define PC_SMM_SERVICES

; Board opens/reserves/protects SMRAM and establishes first-fetch coherency.
; AX=CPU profile 1/2, DX bit 0=qualified board, DS:SI=ROM image, CX=length,
; ES:DI=opened SMRAM, DI=8000h. Source must not overlap the destination.
; AX=status (0 OK, 1 unavailable, 2 bounds, 3 verification); CF=error.
; Preserve other registers and all other flags, including DF.
smm_install:
    pushfd
    pushad
    test dx,1
    jz .unavailable
    cmp ax,1
    je .bounds
    cmp ax,2
    jne .unavailable
.bounds:
    cmp di,0x8000
    jne .invalid
    cmp cx,2
    jb .invalid
    cmp cx,0x7E00
    ja .invalid
    movzx eax,si
    movzx ebx,cx
    add eax,ebx
    cmp eax,0x10000
    ja .invalid
    cld
    push si
    push di
    push cx
    rep movsb
    pop cx
    pop di
    pop si
    repe cmpsb
    jne .verification
    xor ax,ax
    jmp .result
.unavailable:
    mov ax,1
    jmp .result
.invalid:
    mov ax,2
    jmp .result
.verification:
    mov ax,3
.result:
    mov bp,sp
    mov [ss:bp+28],ax
    or dword [ss:bp+32],1
    test ax,ax
    jnz .return
    and dword [ss:bp+32],0xFFFFFFFE
.return:
    popad
    popfd
    ret

%define SMM_REQUEST 0x534D4D51
%define SMM_REPLY   0x534D4D52

; Emit at SMBASE+8000h. board_smm_ack must be stackless, acknowledge the
; source, and return AL=1 only for its software-command SMI (else AL=0).
; Relocation target must already contain this handler and be protected.
; Only Intel-compatible two-pin SMM is supported; no classic AMD/Cyrix map.
%macro smm_handler 2
%if (%2 & 0x7FFF) || (%2 < 0) || (%2 > 0xF0000)
    %error SMM relocation target must be aligned and its full window below 1 MiB
%endif
%1:
    board_smm_ack
    cmp al,1
    jne %%resume
    cmp dword [cs:0xFFDC],SMM_REQUEST
    jne %%resume
    movzx eax,word [cs:0xFFD4] ; CX command leaves AL/DX free for the trigger.
    test eax,eax
    jz %%success
    cmp eax,1
    jne %%bad_command
    test dword [cs:0xFEFC],0x00020000
    jz %%no_relocation
    cmp dword [cs:0xFFEC],%2  ; EDI target survives OUT AL/DX.
    jne %%bad_target
    mov dword [cs:0xFEF8],%2
%%success:
    xor eax,eax
    and dword [cs:0xFFF4],0xFFFFFFFE
    jmp %%reply
%%bad_command:
    mov eax,1
    jmp %%failure
%%no_relocation:
    mov eax,2
    jmp %%failure
%%bad_target:
    mov eax,3
%%failure:
    or dword [cs:0xFFF4],1
%%reply:
    mov [cs:0xFFD0],eax
    mov eax,[cs:0xFEFC]
    mov [cs:0xFFD4],eax
    mov dword [cs:0xFFDC],SMM_REPLY
%%resume:
    rsm
%endmacro
%endif
