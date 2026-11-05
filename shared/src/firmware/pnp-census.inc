; Complete card/LDN census. Arbitrary metadata stays in the hardware stream;
; only identities, alternative priority/cursors and bounded hardware domains
; enter the one POST journal. Nothing is activated by census.
PNP_CARD_SIZE equ 32
PNP_CARD_NEXT equ 0
PNP_CARD_FIRST_LDN equ 4
PNP_CARD_ID equ 8
PNP_CARD_CSN equ 17
PNP_CARD_FAMILY equ 18
PNP_CARD_STATUS equ 19
PNP_CARD_LDN_COUNT equ 20
PNP_LDN_NEXT equ 0
PNP_LDN_PREV equ 4
PNP_LDN_CARD equ 8
PNP_LDN_ALTS equ 12
PNP_LDN_ALT equ 16
PNP_LDN_ID equ 20
PNP_LDN_INDEX equ 24
PNP_LDN_BOOT equ 25
PNP_LDN_STATUS equ 26
PNP_LDN_NDOM equ 27
PNP_LDN_POSITION equ 28
PNP_LDN_ALT_ORDINAL equ 32
PNP_LDN_COUNTS equ 36
PNP_LDN_TAILS equ 40
PNP_LDN_DOMAINS equ 52
PNP_LDN_SIZE equ PNP_LDN_DOMAINS+16*32
PNP_ALT_SIZE equ 16
PNP_ALT_NEXT equ 0
PNP_ALT_ORDINAL equ 4
PNP_ALT_PRIORITY equ 8

P_C_EVENT equ -32
P_C_SERIAL equ -48
P_C_CARD equ -52
P_C_LDN equ -56
P_C_INDEX equ -60
P_C_PORT equ -62
P_C_CSN equ -63
P_C_SEEN equ -64
P_C_DF equ -65
P_C_ORDINAL equ -72
P_C_FAMILY equ -73
P_C_PROBED equ -74
P_C_PRIORITY equ -75
P_C_SCAN_PRIORITY equ -76
P_C_ALT equ -80
P_C_TAIL equ -84
P_C_NORMAL equ -128

; ECX=multiple-of-four object size. EAX address and GS:SI object start, CF.
pnp_new_object:
    call PNP_ALLOCATE
    jc .done
    push eax
    call pnp_pointer
    push si
    xor ebx,ebx
    shr ecx,2
.zero:
    mov [gs:si],ebx
    add si,4
    loop .zero
    pop si
    pop eax
    clc
.done:
    ret

pnp_census:
    pushad
    push gs
    push es
    push ds
    mov bp,sp
    sub sp,128
    push ss
    pop es
    mov byte [ss:bp+P_C_CSN],0
    mov byte [ss:bp+P_C_PROBED],0
    mov word [ss:bp+P_C_PORT],0x203
    mov dword [ss:bp+P_C_CARD],0
    call pnp_isa_reset
.find:
    cmp byte [ss:bp+P_C_CSN],0
    jne .probe
    mov ax,0x0201
    movzx edx,word [ss:bp+P_C_PORT]
    mov ecx,1
    call pnp_claim_query
    jc .relocate
.probe:
    mov byte [ss:bp+P_C_PROBED],1
    mov dx,[ss:bp+P_C_PORT]
    call pnp_isa_wake_zero
    call pnp_isa_read_port
    lea di,[bp+P_C_SERIAL]
    call pnp_isa_isolate
    jnc .found
    cmp byte [ss:bp+P_C_CSN],0
    jne .finish
.relocate:
    add word [ss:bp+P_C_PORT],4
    cmp word [ss:bp+P_C_PORT],0x3FF
    jbe .find
    jmp .finish
.found:
    cmp byte [ss:bp+P_C_CSN],255
    je .too_many
    inc byte [ss:bp+P_C_CSN]
    mov ah,[ss:bp+P_C_CSN]
    mov al,6
    call pnp_isa_write
    cmp ah,1
    jne .card
    call pnp_bus_claim
    jnc .card
    call pnp_census_bad
.card:
    mov dword [ss:bp+P_C_CARD],0
    lea di,[bp+P_C_SERIAL]
    call pnp_eisa_id_valid
    jc .invalid_card
    mov ecx,PNP_CARD_SIZE
    call pnp_new_object
    jnc .have_card
    call pnp_census_bad
    jmp .stream
.have_card:
    mov [ss:bp+P_C_CARD],eax
    mov ebx,eax
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov ecx,[gs:si+PNP_ROOT_CARDS]
    mov [gs:si+PNP_ROOT_CARDS],ebx
    mov eax,ebx
    call pnp_pointer
    mov [gs:si+PNP_CARD_NEXT],ecx
    add si,PNP_CARD_ID
    lea di,[bp+P_C_SERIAL]
    mov cx,9
.identity:
    mov al,[es:di]
    mov [gs:si],al
    inc si
    inc di
    loop .identity
    mov al,[ss:bp+P_C_CSN]
    mov [gs:si],al
.stream:
    mov byte [ss:bp+P_C_EVENT+1],0
    mov dword [ss:bp+P_C_LDN],0
    mov word [ss:bp+P_C_INDEX],0xFFFF
    mov byte [ss:bp+P_C_SEEN],0
    mov byte [ss:bp+P_C_DF],0
    mov byte [ss:bp+P_C_FAMILY],0
.event:
    mov dx,[ss:bp+P_C_PORT]
    lea di,[bp+P_C_EVENT]
    call pnp_resource_next
    jc .invalid_card
    cmp al,0x0A
    je .version
    cmp al,0x82
    je .string
    cmp al,0x83
    je .string
    cmp al,0x15
    je .ldn
    cmp al,0x16
    je .ldn
    cmp al,0x1C
    je .compatible
    cmp al,0x30
    je .alternative
    cmp al,0x31
    je .alternative
    cmp al,0x38
    je .dependent_end
    cmp al,0x79
    je .end
    push ss
    pop gs
    lea si,[bp+P_C_NORMAL]
    call pnp_normalize_event
    jc .invalid_card
    test al,al
    jz .event
    test byte [ss:bp+P_C_SEEN],4
    jz .invalid_card
    cmp al,1
    jne .event
    mov al,[gs:si+3]
    and al,4
    inc al                    ; Family1=24-bit,5=32-bit, fixed for the card.
    cmp byte [ss:bp+P_C_FAMILY],0
    jne .family
    mov [ss:bp+P_C_FAMILY],al
    mov bl,al
    mov eax,[ss:bp+P_C_CARD]
    test eax,eax
    jz .event
    call pnp_pointer
    mov [gs:si+PNP_CARD_FAMILY],bl
    jmp .event
.family:
    cmp al,[ss:bp+P_C_FAMILY]
    jne .invalid_card
    jmp .event
.version:
    cmp byte [ss:bp+P_C_SEEN],0
    jne .invalid_card
    mov al,[es:di+4]
    cmp al,0x10
    jb .invalid_card
    mov ah,al
    and al,15
    cmp al,9
    ja .invalid_card
    shr ah,4
    cmp ah,9
    ja .invalid_card
    or byte [ss:bp+P_C_SEEN],1
    jmp .event
.string:
    test byte [ss:bp+P_C_SEEN],1
    jz .invalid_card
    or byte [ss:bp+P_C_SEEN],2
    jmp .event
.ldn:
    mov al,[ss:bp+P_C_SEEN]
    and al,3
    cmp al,3
    jne .invalid_card
    cmp byte [ss:bp+P_C_DF],1
    je .invalid_card
    inc word [ss:bp+P_C_INDEX]
    cmp word [ss:bp+P_C_INDEX],256
    jae .invalid_card
    mov ax,[ss:bp+P_C_INDEX]
    mov ah,al
    mov al,7
    call pnp_isa_write
    mov ax,0x0030
    call pnp_isa_write        ; Every actual LDN starts inactive, before any replay.
    add di,4
    call pnp_eisa_id_valid
    jc .invalid_card
    sub di,4
    or byte [ss:bp+P_C_SEEN],4
    mov byte [ss:bp+P_C_DF],0
    mov dword [ss:bp+P_C_ORDINAL],0xFFFFFFFF
    mov dword [ss:bp+P_C_LDN],0
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    inc dword [gs:si+PNP_ROOT_LDN_COUNT]
    mov eax,[ss:bp+P_C_CARD]
    test eax,eax
    jz .allocate_ldn
    call pnp_pointer
    inc word [gs:si+PNP_CARD_LDN_COUNT]
.allocate_ldn:
    mov ecx,PNP_LDN_SIZE
    call pnp_new_object
    jnc .have_ldn
    call pnp_census_bad
    jmp .event
.have_ldn:
    mov [ss:bp+P_C_LDN],eax
    mov ebx,eax
    mov eax,[ss:bp+P_C_CARD]
    mov [gs:si+PNP_LDN_CARD],eax
    mov eax,[es:di+4]
    mov [gs:si+PNP_LDN_ID],eax
    mov ax,[ss:bp+P_C_INDEX]
    mov [gs:si+PNP_LDN_INDEX],al
    mov al,[es:di+8]
    mov [gs:si+PNP_LDN_BOOT],al
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov edx,[gs:si+PNP_ROOT_LAST_LDN]
    mov [gs:si+PNP_ROOT_LAST_LDN],ebx
    test edx,edx
    jnz .link_ldn
    mov [gs:si+PNP_ROOT_LDNS],ebx
    jmp .ldn_prev
.link_ldn:
    mov eax,edx
    call pnp_pointer
    mov [gs:si+PNP_LDN_NEXT],ebx
.ldn_prev:
    mov eax,ebx
    call pnp_pointer
    mov [gs:si+PNP_LDN_PREV],edx
    mov eax,[ss:bp+P_C_CARD]
    test eax,eax
    jz .event
    call pnp_pointer
    cmp dword [gs:si+PNP_CARD_FIRST_LDN],0
    jne .event
    mov [gs:si+PNP_CARD_FIRST_LDN],ebx
    jmp .event
.compatible:
    test byte [ss:bp+P_C_SEEN],4
    jz .invalid_card
    add di,4
    call pnp_eisa_id_valid
    jc .invalid_card
    jmp .event
.alternative:
    test byte [ss:bp+P_C_SEEN],4
    jz .invalid_card
    cmp byte [ss:bp+P_C_DF],2
    je .invalid_card
    mov byte [ss:bp+P_C_DF],1
    inc dword [ss:bp+P_C_ORDINAL]
    mov al,1                 ; Omitted priority is acceptable, not preferred.
    cmp word [es:di+2],0
    je .priority
    mov al,[es:di+4]
.priority:
    cmp al,2
    ja .invalid_card
    mov [ss:bp+P_C_PRIORITY],al
    mov [ss:bp+P_C_SCAN_PRIORITY],al
    cmp dword [ss:bp+P_C_LDN],0
    je .event
    mov ecx,PNP_ALT_SIZE
    call pnp_new_object
    jnc .have_alt
    call pnp_census_bad
    mov eax,[ss:bp+P_C_LDN]
    call pnp_pointer
    or byte [gs:si+PNP_LDN_STATUS],0x80
    jmp .event
.have_alt:
    mov [ss:bp+P_C_ALT],eax
    mov edx,[ss:bp+P_C_ORDINAL]
    mov [gs:si+PNP_ALT_ORDINAL],edx
    mov dl,[ss:bp+P_C_PRIORITY]
    mov [gs:si+PNP_ALT_PRIORITY],dl
    movzx eax,dl
    shl eax,2
    add eax,[ss:bp+P_C_LDN]
    add eax,PNP_LDN_TAILS
    mov [ss:bp+P_C_TAIL],eax
    mov edi,eax
.previous_priority:
    mov eax,edi
    call pnp_pointer
    mov ecx,[gs:si]
    test ecx,ecx
    jnz .previous_alt
    cmp byte [ss:bp+P_C_SCAN_PRIORITY],0
    je .first_alt
    dec byte [ss:bp+P_C_SCAN_PRIORITY]
    sub edi,4
    jmp .previous_priority
.previous_alt:
    mov edi,ecx              ; ALT next is offset0.
    jmp .insert_alt
.first_alt:
    mov edi,[ss:bp+P_C_LDN]
    add edi,PNP_LDN_ALTS
.insert_alt:
    mov eax,edi
    call pnp_pointer
    mov ecx,[gs:si]
    mov ebx,[ss:bp+P_C_ALT]
    mov [gs:si],ebx
    mov eax,ebx
    call pnp_pointer
    mov [gs:si+PNP_ALT_NEXT],ecx
    mov eax,[ss:bp+P_C_TAIL]
    call pnp_pointer
    mov [gs:si],ebx
    jmp .event
.dependent_end:
    cmp byte [ss:bp+P_C_DF],1
    jne .invalid_card
    mov byte [ss:bp+P_C_DF],2
    jmp .event
.end:
    cmp byte [ss:bp+P_C_SEEN],7
    jne .invalid_card
    cmp byte [ss:bp+P_C_DF],1
    je .invalid_card
    mov eax,[ss:bp+P_C_CARD]
    test eax,eax
    jz .find
    call pnp_pointer
    or byte [gs:si+PNP_CARD_STATUS],1
    jmp .find
.invalid_card:
    call pnp_census_bad
    mov dx,[ss:bp+P_C_PORT]
    mov cx,256               ; The actual8-bit hardware LDN selector, no cutoff.
    xor bx,bx
.deactivate:
    mov ah,bl
    mov al,7
    call pnp_isa_write
    mov ax,0x0030
    call pnp_isa_write
    inc bl
    loop .deactivate
    jmp .find
.too_many:
    call pnp_census_bad
.finish:
    call pnp_isa_wait_key
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov al,[ss:bp+P_C_CSN]
    mov [gs:si+PNP_ROOT_CSN_COUNT],al
    xor dx,dx
    test al,al
    jz .no_port
    mov dx,[ss:bp+P_C_PORT]
.no_port:
    mov [gs:si+PNP_ROOT_READ_PORT],dx
    cmp byte [ss:bp+P_C_PROBED],0
    jne .status
    or byte [gs:si+PNP_ROOT_STATUS],1
.status:
    cmp byte [gs:si+PNP_ROOT_STATUS],0
    jne .bad_return
    mov sp,bp
    pop ds
    pop es
    pop gs
    popad
    clc
    ret
.bad_return:
    mov sp,bp
    pop ds
    pop es
    pop gs
    popad
    stc
    ret

; Census frame BP stays live. Root incomplete never becomes a successful Clear.
pnp_census_bad:
    pushad
    push gs
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    or byte [gs:si+PNP_ROOT_STATUS],1
    mov eax,[ss:bp+P_C_CARD]
    test eax,eax
    jz .done
    call pnp_pointer
    or byte [gs:si+PNP_CARD_STATUS],0x80
.done:
    pop gs
    popad
    ret
pnp_census_code_end:
