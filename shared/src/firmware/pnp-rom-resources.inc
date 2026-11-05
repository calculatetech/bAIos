; Independent pre-initialization static reports use the existing returning-ROM
; call owner. No ROM is initialized here. Complete generic chains are checked
; before any vector is consumed; Floyd traversal has no metadata/count cutoff.
%include "pc/rom-state.inc"
P_O_LENGTH equ -4
P_O_SEGMENT equ -6
P_O_NEXT equ -8
P_O_SLOW equ -10
P_O_FAST equ -12
P_O_BUFFER equ -16
P_O_HEADER equ -18
P_O_MODE equ -19

pnp_rom_resources:
    pushad
    push ds
    push es
    push gs
    mov bp,sp
    sub sp,20
    mov [ss:bp+P_O_MODE],al  ;0 independent static reports,1 live fixed extents.
    test al,al
    jnz .begin_scan
    mov ecx,1024
    call pnp_new_object
    jc .failed
    mov [ss:bp+P_O_BUFFER],eax
.begin_scan:
    mov word [ss:bp+P_O_SEGMENT],0xC000
.scan:
    mov ax,[ss:bp+P_O_SEGMENT]
    cmp ax,0xF000
    jae .done
%ifdef M919_BOARD_DEFINITION
    cmp ax,0xE000           ; Complete generated APM/SMM/private E0 owner.
    jae .done
%endif
%ifdef PB430_PORT
    cmp ax,0xE000           ; Retained staging/private bank, not an option slot.
    jae .done
%endif
    mov dx,ax
    add dx,0x80
    mov [ss:bp+P_O_NEXT],dx
    mov ds,ax
    cmp word [0],0xAA55
    jne .next
    movzx ecx,byte [2]
    test ecx,ecx
    jz .next
    cmp ecx,128
    ja .next
    shl ecx,9
    mov [ss:bp+P_O_LENGTH],ecx
    movzx edx,ax
    shl edx,4
    add edx,ecx
    cmp edx,0xF0000
    ja .next
    xor esi,esi
    xor bl,bl
.sum:
    add bl,[ds:esi]
    inc esi
    loop .sum
    test bl,bl
    jnz .next
    add edx,0x7FF
    shr edx,4
    and dx,0xFF80
    mov [ss:bp+P_O_NEXT],dx
    cmp byte [ss:bp+P_O_MODE],0
    je .static_headers
    movzx edx,word [ss:bp+P_O_SEGMENT]
    shl edx,4
    mov ecx,[ss:bp+P_O_LENGTH]
    mov esi,1
    mov ax,0x0100
    call pnp_reserve
    jc .failed
    jmp .next               ; The extent pass never recalls a static vector.
.static_headers:
    mov ecx,[ss:bp+P_O_LENGTH]
    call pnp_rom_chain
    jc .invalid
    test si,si
    jz .next
.validated:
    mov si,[ds:0x1A]
.vector:
    mov [ss:bp+P_O_HEADER],si
    call .header
    jc .invalid
    mov [ss:bp+P_O_FAST],ax
    test dx,dx
    jz .following
    mov [fs:R_ENTRY],dx
    mov dx,[ss:bp+P_O_SEGMENT]
    mov [fs:R_ENTRY+2],dx
    mov eax,[ss:bp+P_O_BUFFER]
    call pnp_pointer
    push gs
    pop es
    mov di,si
    push si
    mov cx,256
    xor eax,eax
.clear_buffer:
    mov [gs:si],eax
    add si,4
    loop .clear_buffer
    pop si
    mov al,1
    call CFG_ROM_CODE_SEGMENT:pnp_rom_callback
    mov eax,[ss:bp+P_O_BUFFER]
    call pnp_pointer
    push gs
    pop es
    mov di,si
    cmp byte [es:di+2],0
    jne .invalid_report
    add di,3
    call pnp_eisa_id_valid
    sub di,3
    jc .invalid_report
    mov cx,1024
    movzx esi,word [ss:bp+P_O_SEGMENT]
    shl esi,4
    inc esi                 ; This report's owner, distinct from its ROM extent.
    call pnp_map_node
    jc .invalid_report
    mov bx,ax
    mov ax,[es:di]
    add ax,di
    mov cx,bx
    add cx,4
    cmp cx,ax
    ja .invalid_report
    cmp byte [es:bx],0x79    ; Static Possible block is exactly one End tag.
    jne .invalid_report
    cmp byte [es:bx+1],0
    je .compatible
    cmp byte [es:bx+1],0x87
    jne .invalid_report
.compatible:
    add bx,2
    xor dl,dl
.compatible_next:
    mov cx,bx
    add cx,2
    cmp cx,ax
    ja .invalid_report
    cmp byte [es:bx],0x79
    je .compatible_end
    cmp byte [es:bx],0x1C
    jne .invalid_report
    add cx,3
    cmp cx,ax
    ja .invalid_report
    push di
    lea di,[bx+1]
    call pnp_eisa_id_valid
    pop di
    jc .invalid_report
    lea si,[bx+5]
.compatible_sum:
    add dl,[es:bx]
    inc bx
    cmp bx,si
    jb .compatible_sum
    jmp .compatible_next
.compatible_end:
    cmp cx,ax
    jne .invalid_report
    cmp byte [es:bx+1],0
    je .following
    add dl,0x79
    add dl,[es:bx+1]
    jnz .invalid_report
.following:
    mov ax,[ss:bp+P_O_SEGMENT]
    mov ds,ax
    mov si,[ss:bp+P_O_FAST]
    test si,si
    jnz .vector
.next:
    mov ax,[ss:bp+P_O_NEXT]
    mov [ss:bp+P_O_SEGMENT],ax
    jmp .scan
.invalid:
    ; Legacy ROM1Ah was reserved. Invalid generic metadata is no provider;
    ; never execute it and keep scanning the next physical ROM.
    jmp .next
.invalid_report:
    movzx esi,word [ss:bp+P_O_SEGMENT]
    shl esi,4
    inc esi
    call pnp_claim_remove_owner
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    or byte [gs:si+PNP_ROOT_STATUS],1
    jmp .next
.done:
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    clc
    ret
.failed:
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    stc
    ret
.header:
    mov ecx,[ss:bp+P_O_LENGTH]
    jmp pnp_rom_header

; DS=ROM, SI=header, ECX=outer extent. AX=next, DX=static vector or0.
pnp_rom_header:
    push ebx
    push ecx
    push esi
    push edi
    push bp
    mov bp,sp
    movzx esi,si
    lea edi,[esi+10]
    cmp edi,ecx
    ja .bad
    movzx ebx,byte [ds:esi+5]
    shl ebx,4
    test ebx,ebx
    jz .bad
    lea edi,[esi+ebx]
    cmp edi,ecx
    ja .bad
    mov cx,bx
    xor bl,bl
.sum:
    add bl,[ds:esi]
    inc esi
    loop .sum
    test bl,bl
    jnz .bad
    mov esi,[ss:bp+6]
    movzx esi,si
    xor dx,dx
    cmp dword [ds:esi],0x506E5024
    jne .next
    cmp byte [ds:esi+4],1
    jne .bad
    cmp byte [ds:esi+5],2
    jb .bad
    ; Every nonnull callable/string pointer is ROM-relative and must remain
    ; inside the validated complete image. Unknown generic headers still link.
    push si
    add si,0x0E
    mov cx,2
.string:
    movzx ebx,word [ds:si]
    test bx,bx
    jz .string_next
.string_byte:
    cmp ebx,[ss:bp+10]
    jae .bad_string
    cmp byte [ds:ebx],0
    je .string_next
    inc ebx
    jmp .string_byte
.string_next:
    add si,2
    loop .string
    add si,4
    mov cx,3
.pointer:
    movzx ebx,word [ds:si]
    cmp ebx,[ss:bp+10]
    jae .bad_string
    add si,2
    loop .pointer
    pop si
    mov dx,[ds:esi+0x1E]
    movzx ebx,dx
    cmp ebx,[ss:bp+10]
    jae .bad
.next:
    mov ax,[ds:esi+6]
    pop bp
    pop edi
    pop esi
    pop ecx
    pop ebx
    clc
    ret
.bad_string:
    pop si
.bad:
    pop bp
    pop edi
    pop esi
    pop ecx
    pop ebx
    stc
    ret

; DS=validated outer ROM, ECX=its exact byte extent. Validate the complete
; generic chain before exposing any PnP metadata. SI=first header or0 (legacy).
; Floyd traversal has no header-count cutoff and cannot hide later headers.
pnp_rom_chain:
    push ax
    push bx
    push dx
    push di
    mov si,[ds:0x1A]
    test si,si
    jz .good
    mov di,si
    mov bx,si
    call pnp_rom_header
    jnc .walk
    ; The old ISA header reserved1Ah. Garbage there is not a PnP declaration.
    movzx edx,si
    add edx,4
    cmp edx,ecx
    ja .legacy
    cmp dword [ds:si],0x506E5024
    je .bad
.legacy:
    xor si,si
    jmp .good
.walk:
    mov si,bx
    call pnp_rom_header
    jc .bad
    test ax,ax
    jz .complete
    mov si,ax
    call pnp_rom_header
    jc .bad
    mov bx,ax
    test ax,ax
    jz .complete
    mov si,di
    call pnp_rom_header
    jc .bad
    mov di,ax
    cmp ax,bx
    je .bad
    jmp .walk
.complete:
    mov si,[ds:0x1A]
.good:
    pop di
    pop dx
    pop bx
    pop ax
    clc
    ret
.bad:
    pop di
    pop dx
    pop bx
    pop ax
    stc
    ret
pnp_rom_resources_code_end:
