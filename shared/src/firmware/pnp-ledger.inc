; POST ownership ledger. Domain records are32 bytes: the normalized24-byte
; resource plus claim-next at24 and owner at28. Each live domain is linked
; at most once; retries reuse that record instead of leaking arena capacity.
%ifndef PNP_ALLOCATE
%define PNP_ALLOCATE pnp_journal_allocate
%endif
PNP_ROOT_SIZE equ 32
PNP_ROOT_CLAIMS equ 0
PNP_ROOT_CARDS equ 4
PNP_ROOT_LDNS equ 8
PNP_ROOT_LAST_LDN equ 12
PNP_ROOT_READ_PORT equ 16
PNP_ROOT_CSN_COUNT equ 18
PNP_ROOT_STATUS equ 19
PNP_ROOT_CLAIM_COUNT equ 20
PNP_ROOT_LDN_COUNT equ 24
PNP_ROOT_BUS equ 28

; EAX linear conventional-RAM pointer -> GS:SI, independent of a64KiB window.
pnp_pointer:
    mov si,ax
    and si,15
    shr eax,4
    mov gs,ax
    ret

pnp_work_begin:
    pushad
    push gs
    mov ecx,PNP_ROOT_SIZE
    call PNP_ALLOCATE
    jc .bad
    mov [fs:PNP_JOURNAL_FIRST],eax
    mov edx,eax
    call pnp_pointer
    xor eax,eax
    mov cx,PNP_ROOT_SIZE/4
.zero:
    mov [gs:si],eax
    add si,4
    loop .zero
    mov ecx,96               ; Three bus owners exist before card-journal pressure.
    call PNP_ALLOCATE
    jc .bad
    mov ebx,eax
    call pnp_pointer
    mov cx,24
.bus_zero:
    mov [gs:si],dword 0
    add si,4
    loop .bus_zero
    mov eax,edx
    call pnp_pointer
    mov [gs:si+PNP_ROOT_BUS],ebx
    pop gs
    popad
    clc
    ret
.bad:
    pop gs
    popad
    stc
    ret

; DX=actual admitted read port, called only once a real card was isolated.
; Existing fixed LPT2/status overlap is a compatible baseline, not a reason
; to reject that controller. New device assignments query the complete union.
pnp_bus_claim:
    pushad
    push gs
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov ebx,[gs:si+PNP_ROOT_BUS]
    test ebx,ebx
    jz .bad
    xor edi,edi
.owner:
    mov eax,ebx
    call pnp_pointer
    mov byte [gs:si],2
    mov byte [gs:si+2],1
    mov dword [gs:si+16],1
    mov eax,0x279
    test di,di
    jz .port
    mov eax,0xA79
    cmp di,1
    je .port
    movzx eax,dx
.port:
    mov [gs:si+20],eax
    mov dword [gs:si+28],3
    mov eax,ebx
    call pnp_claim_add
    add ebx,32
    inc di
    cmp di,3
    jb .owner
    pop gs
    popad
    clc
    ret
.bad:
    pop gs
    popad
    stc
    ret

; EAX=normalized domain address. Nulls owe ordinals but own no resources.
pnp_claim_add:
    pushad
    push gs
    mov ebx,eax
    call pnp_pointer
    test byte [gs:si+3],3
    jnz .done
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .bad
    call pnp_pointer
    mov ecx,[gs:si+PNP_ROOT_CLAIMS]
    mov [gs:si+PNP_ROOT_CLAIMS],ebx
    inc dword [gs:si+PNP_ROOT_CLAIM_COUNT]
    mov eax,ebx
    call pnp_pointer
    mov [gs:si+24],ecx
    or byte [gs:si+3],2
.done:
    pop gs
    popad
    clc
    ret
.bad:
    pop gs
    popad
    stc
    ret

; AH=kind, AL=I/O decode info, EDX=base/PIC IRQ/DMA, ECX=length.
; CF=conflict (including missing/corrupt ledger). PIC2 internal cascade stays
; PIC2 here: only the ISA request selector maps external ISA2 into PIC9.
pnp_claim_query:
    push gs
    pushad
    mov bp,sp
    test ecx,ecx
    jz .free
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .conflict
    call pnp_pointer
    push dword [gs:si+PNP_ROOT_CLAIM_COUNT]
    mov eax,[gs:si+PNP_ROOT_CLAIMS]
.next:
    test eax,eax
    jz .free
    sub dword [ss:bp-4],1
    jc .conflict              ; Bound traversal by actual live records, not a cap.
    call pnp_pointer
    mov al,[ss:bp+29]
    cmp [gs:si],al
    jne .advance
    mov edi,[ss:bp+20]
    cmp al,3
    jae .scalar
    mov ebx,[ss:bp+24]
    mov eax,[gs:si+20]
    mov edx,[gs:si+16]
    cmp byte [ss:bp+29],2
    jne .interval
    mov cl,[ss:bp+28]
    and cl,[gs:si+2]
    test cl,1
    jnz .interval
    ; A10-bit range repeats every400h. These modular distances cover every
    ; alias, including a range crossing the400h boundary and large16-bit BARs.
    cmp ebx,0x400
    jae .conflict
    cmp edx,0x400
    jae .conflict
    mov ecx,edi
    sub ecx,eax
    and ecx,0x3FF
    cmp ecx,edx
    jb .conflict
    sub eax,edi
    and eax,0x3FF
    cmp eax,ebx
    jb .conflict
    jmp .advance
.interval:
    mov ecx,edi
    sub ecx,eax
    cmp ecx,edx
    jb .conflict
    sub eax,edi
    cmp eax,ebx
    jb .conflict
    jmp .advance
.scalar:
    movzx eax,byte [gs:si+20]
    test byte [gs:si+3],0x20
    jz .scalar_pic
    cmp al,2
    jne .scalar_pic
    mov al,9                ; External ISA2, never the PIC's internal cascade.
.scalar_pic:
    cmp eax,edi
    je .conflict
.advance:
    mov eax,[gs:si+24]
    jmp .next
.free:
    mov sp,bp
    popad
    pop gs
    clc
    ret
.conflict:
    mov sp,bp
    popad
    pop gs
    stc
    ret

; ESI=owner. Rollback removes only its claims; fixed/manual/other devices and
; overlapping unions survive. Records remain reusable by the next candidate.
pnp_claim_remove_owner:
    push gs
    pushad
    mov bp,sp
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .bad
    mov edi,eax
    lea ebx,[eax+PNP_ROOT_CLAIM_COUNT]
    call pnp_pointer
    push dword [gs:si+PNP_ROOT_CLAIM_COUNT]
    mov eax,[gs:si+PNP_ROOT_CLAIMS]
.next:
    test eax,eax
    jz .done
    sub dword [ss:bp-4],1
    jc .bad
    mov ecx,eax
    call pnp_pointer
    mov edx,[gs:si+24]
    mov eax,[ss:bp+4]
    cmp [gs:si+28],eax
    jne .keep
    and byte [gs:si+3],0xFD
    mov dword [gs:si+24],0
    mov eax,edi
    call pnp_pointer
    mov [gs:si],edx
    mov eax,ebx
    call pnp_pointer
    dec dword [gs:si]
    jmp .advance
.keep:
    lea edi,[ecx+24]
.advance:
    mov eax,edx
    jmp .next
.done:
    mov sp,bp
    popad
    pop gs
    clc
    ret
.bad:
    mov sp,bp
    popad
    pop gs
    stc
    ret
pnp_ledger_code_end:
