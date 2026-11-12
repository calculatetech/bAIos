; One ownership map for existing onboard encoder, manual policy and reported
; static/PCI resources. ESI=owner, AH=kind, AL=I/O decode, EDX=base, ECX=len.
pnp_reserve:
    test ecx,ecx
    jz .empty
    pushad
    push gs
    push esi
    push ax
    push ecx
    mov ecx,32
    call pnp_new_object
    pop ecx
    pop bx
    pop edi
    jc .bad
    mov [gs:si],bh
    mov [gs:si+2],bl
    mov [gs:si+16],ecx
    mov [gs:si+20],edx
    mov [gs:si+28],edi
    call pnp_claim_add
    pop gs
    popad
    ret
.bad:
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    or byte [gs:si+PNP_ROOT_STATUS],1
    pop gs
    popad
    stc
    ret
.empty:
    clc
    ret

; ES:DI=node, CX=actual available bytes. Only the allocated block is claimed.
; Full known resource fields use the same normalizer as actual ISA streams.
pnp_map_node:
    pushad
    push ds
    push es
    push gs
    mov bp,sp
    sub sp,64
    mov [ss:bp-8],esi
    mov byte [ss:bp-3],0
    mov bx,di
    add cx,di
    jc .bad
    mov ax,[es:di]
    cmp ax,16
    jb .bad
    add ax,di
    jc .bad
    cmp ax,cx
    ja .bad
    mov [ss:bp-2],ax
    add bx,12
    push es
    pop ds
    push ss
    pop es
.tag:
    cmp bx,[ss:bp-2]
    jae .bad
    mov al,[ds:bx]
    add [ss:bp-3],al
    inc bx
    mov [ss:bp-32],al
    xor cx,cx
    mov cl,al
    and cl,7
    test al,0x80
    jz .length
    mov ax,bx
    add ax,2
    jc .bad
    cmp ax,[ss:bp-2]
    ja .bad
    mov cx,[ds:bx]
    add [ss:bp-3],cl
    add [ss:bp-3],ch
    add bx,2
.length:
    mov [ss:bp-30],cx
    mov si,pnp_resource_lengths
.known:
    mov al,[cs:si]
    test al,al
    jz .bad
    cmp al,[ss:bp-32]
    je .known_length
    add si,2
    jmp .known
.known_length:
    cmp cl,[cs:si+1]
    jne .bad
    test ch,ch
    jnz .bad
    mov ax,bx
    add ax,cx
    jc .bad
    cmp ax,[ss:bp-2]
    ja .bad
    cmp cx,17
    ja .bad
    lea di,[bp-28]
.payload:
    jcxz .event
    mov al,[ds:bx]
    add [ss:bp-3],al
    mov [es:di],al
    inc bx
    inc di
    loop .payload
.event:
    cmp byte [ss:bp-32],0x79
    je .done
    lea di,[bp-32]
    push ss
    pop gs
    lea si,[bp-64]
    call pnp_normalize_event
    jc .bad
    test al,al
    jz .bad
    test byte [gs:si+3],1
    jnz .tag
    cmp al,3
    jae .channels
    mov edx,[gs:si+4]
    cmp edx,[gs:si+8]
    jne .bad
    mov ecx,[gs:si+16]
    mov ah,al
    mov al,[gs:si+2]
    mov esi,[ss:bp-8]
    call pnp_reserve
    jc .bad
    jmp .tag
.channels:
    mov edi,[gs:si+4]
    mov ah,al
    xor edx,edx
.channel:
    bt edi,edx
    jnc .skip
    push dx
    mov ecx,1
    mov esi,[ss:bp-8]
    cmp ah,3
    jne .channel_reserve
    cmp dx,2
    jne .channel_reserve
    cmp esi,1               ; Only onboard PIC node owns the internal cascade.
    je .channel_reserve
    mov dx,9                ; Independent legacy ISA report of IRQ2 owns PIC9.
.channel_reserve:
    call pnp_reserve
    pop dx
    jc .bad
.skip:
    inc edx
    cmp edx,16
    jb .channel
    jmp .tag
.done:
    cmp byte [ss:bp-28],0
    je .good
    cmp byte [ss:bp-3],0
    jne .bad
.good:
    mov [ss:bp+34],bx       ; AX=first byte of the Possible block.
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    clc
    ret
.bad:
    mov esi,[ss:bp-8]
    call pnp_claim_remove_owner
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    stc
    ret

pnp_seed:
    pushad
    push es
    push gs
    movzx ebp,sp
    sub sp,PNP_FRAME
    mov ax,0x40
    mov gs,ax
    xor bx,bx
.node:
    xor ax,ax
    call PNP_NODE_LOAD
    push ss
    pop es
    lea di,[bp+PNP_NODE]
    mov cx,PNP_NODE_MAX
    mov esi,1
    call pnp_map_node
    jc .bad
    inc bx
    cmp bx,PNP_RESOURCE_NODE_COUNT
    jb .node
%ifdef M919_BOARD_DEFINITION
    cmp word [fs:M_VGA_BDF],0xFFFF
    je .manual_policy
    call pnp_reserve_vga
    jc .bad
.manual_policy:
%endif
    mov esi,2               ; Manual policy is a distinct owner.
    xor edx,edx
.irq:
    bt [fs:C_PNP+PNP_IRQ],dx
    jnc .next_irq
    mov ax,0x0300
    mov ecx,1
    push dx
    cmp dx,2
    jne .manual_pic
    mov dx,9
.manual_pic:
    call pnp_reserve
    pop dx
    jc .bad
.next_irq:
    inc dx
    cmp dx,16
    jb .irq
    xor dx,dx
.dma:
    bt [fs:C_PNP+PNP_DMA],dx
    jnc .next_dma
    mov ax,0x0400
    mov ecx,1
    call pnp_reserve
    jc .bad
.next_dma:
    inc dx
    cmp dx,8
    jb .dma
    xor bx,bx
.window:
    movzx edx,word [fs:C_PNP+PNP_IO+bx]
    movzx ecx,word [fs:C_PNP+PNP_IO+bx+2]
    mov ax,0x0201
    call pnp_reserve
    jc .bad
    add bx,4
    cmp bx,8
    jb .window
    xor bx,bx
    mov edx,0xC0000
.upper:
    bt [fs:C_PNP+PNP_MEMORY],bx
    jnc .next_upper
    mov ax,0x0100
    mov ecx,0x4000
    call pnp_reserve
    jc .bad
.next_upper:
    add edx,0x4000
    inc bx
    cmp bx,12
    jb .upper
    ; Fixed firmware aperture. Selected VGA/static-ROM extents are added by
    ; their actual discovery owner before a candidate can claim memory.
    mov ax,0x0100
%ifdef CFG_ROM_BASE
    mov edx,CFG_ROM_BASE
%else
    mov edx,CFG_ROM_CODE_SEGMENT << 4
%endif
    mov ecx,CFG_ROM_SIZE
    call pnp_reserve
    jmp .return
.bad:
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    or byte [gs:si+PNP_ROOT_STATUS],1
    stc
.return:
    mov sp,bp
    pop gs
    pop es
    popad
    ret
pnp_map_code_end:

%ifdef M919_BOARD_DEFINITION
; Same legacy decode as the embedded-VGA encoder. ESI=existing owner1.
; PCI selection seeds it early; a validated ISA C000 extent supplies fallback.
pnp_reserve_vga:
    mov ax,0x0200
    mov edx,0x3B0
    mov ecx,12
    call pnp_reserve
    jc .done
    mov dl,0xC0
    mov cl,32
    call pnp_reserve
    jc .done
    mov ah,1
    mov edx,0xA0000
    mov ecx,0x20000
    jmp pnp_reserve
.done:
    ret

pnp_pci_candidate_core:
    pushad
    mov edx,ecx
    mov ecx,esi
    mov ah,al
    mov al,0x81             ; PCI bus ownership, with full I/O address decode.
    call pnp_claim_query
    jc .done
    mov esi,4
    call pnp_reserve
.done:
    popad
    ret

; AX=free PIC mask, DX=actual allocated ISA high-true-edge mask.
; Manual reservations exclude routing without inventing their signal type.
pnp_irq_mask:
    push gs
    pushad
    mov bp,sp
    xor ebx,ebx
    xor edi,edi
    mov word [ss:bp+28],0
    mov word [ss:bp+20],0
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .return
    call pnp_pointer
    mov ecx,[gs:si+PNP_ROOT_CLAIM_COUNT]
    mov eax,[gs:si+PNP_ROOT_CLAIMS]
.next:
    test eax,eax
    jz .free
    jecxz .return
    dec ecx
    call pnp_pointer
    cmp byte [gs:si],3
    jne .advance
    movzx edx,byte [gs:si+20]
    test byte [gs:si+3],0x20
    jz .pic
    cmp dl,2
    jne .isa
    mov dl,9
.isa:
    bts edi,edx
.pic:
    bts ebx,edx
.advance:
    mov eax,[gs:si+24]
    jmp .next
.free:
    not bx
    mov [ss:bp+28],bx
    mov [ss:bp+20],di
.return:
    popad
    pop gs
    ret
%endif
