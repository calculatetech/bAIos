; POST-only image initialization and actual-instance provider census.
%include "pc/pnp-runtime-state.inc"

; The complete discovery transaction is POST-only. The public boot/router
; entries remain F000; this body returns before runtime publication/release.
pnp_discovery_entry:
    pushf
    pushad
    push ds
    push es
    push fs
    push gs
    cld
    call pnp_module_state
    cmp byte [fs:R_SCANNED],1
    je .return
    mov byte [fs:R_SCANNED],1
    xor ax,ax
    mov es,ax
    mov dword [es:0x64],(CFG_ROM_CODE_SEGMENT << 16)+boot_rom_fallback
%ifdef M919_BOARD_DEFINITION
    call pnp_pci_option_roms
%endif
    call pnp_discover_images
    xor ax,ax
    mov ds,ax
    mov eax,[0x64]
    cmp eax,(CFG_ROM_CODE_SEGMENT << 16)+boot_rom_fallback
    jne .save_boot_chain
    xor eax,eax
.save_boot_chain:
    mov [fs:B_ROM19],eax
    mov dword [0x64],(CFG_ROM_CODE_SEGMENT << 16)+int19
.return:
    pop gs
    pop fs
    pop es
    pop ds
    popad
    popf
    ret

; DS=outer ROM. ECX=complete byte extent on success. No metadata is consumed
; until the entire declared image and generic chain have been validated.
pnp_rom_outer:
    cmp word [ds:0],0xAA55
    jne .bad
    movzx ecx,byte [ds:2]
    test ecx,ecx
    jz .bad
    cmp ecx,128
    ja .bad
    shl ecx,9
    push edx
    xor edx,edx
    mov dx,ds
    shl edx,4
    add edx,ecx
%ifdef M919_BOARD_DEFINITION
    cmp edx,0xE0000
%elifdef PB430_PORT
    cmp edx,0xE0000
%else
    cmp edx,0xF0000
%endif
    pop edx
    ja .bad
    push ecx
    xor esi,esi
    xor al,al
.sum:
    add al,[ds:esi]
    inc esi
    loop .sum
    pop ecx
    test al,al
    jnz .bad
    jmp pnp_rom_chain
.bad:
    stc
    ret

; Complete late physical scan. The selected VGA and deployed PCI extents have
; already executed. All other admitted2KiB apertures reach the same validator.
pnp_discover_images:
    pushad
    push ds
    mov ax,0xC000
    mov ds,ax
    movzx edx,byte [ds:2]
    shl edx,5
    add dx,0xC07F
    and dx,0xFF80
%ifdef BOARD_OPTION_ROM_FIRST_SEG
    cmp dx,BOARD_OPTION_ROM_FIRST_SEG
    jae .scan
    mov dx,BOARD_OPTION_ROM_FIRST_SEG
%endif
.scan:
%ifdef M919_BOARD_DEFINITION
    call pnp_pci_rom_skip
%endif
%ifdef M919_BOARD_DEFINITION
    cmp dx,0xE000
%elifdef PB430_PORT
    cmp dx,0xE000
%else
    cmp dx,0xF000
%endif
    jae .done
    mov ds,dx
    cmp word [ds:0],0xAA55
    jne .next
    call pnp_rom_outer
    jc .invalid
    mov edi,ecx
    shr edi,4
    movzx eax,dx
    add edi,eax
    add di,0x7F
    and di,0xFF80
    call CFG_ROM_CODE_SEGMENT:pnp_post_rom_callback
    mov ax,0xFFFF
    xor cl,cl
    call pnp_initialize_image
    mov dx,di
    jmp .scan
.invalid:
    call CFG_ROM_CODE_SEGMENT:pnp_rom_error_callback
.next:
    add dx,0x80
    jmp .scan
.done:
    pop ds
    popad
    ret

; AX=actual PCI BDF orFFFF, DX=image segment, CL=selected BCV role (2 video).
; The same image is initialized once; distinct headers/segments stay distinct.
pnp_initialize_image:
    pushad
    push ds
    push es
    push gs
    mov bp,sp
    sub sp,32
    mov [ss:bp-2],dx
    mov [ss:bp-4],ax
    mov [ss:bp-5],cl
    mov eax,[fs:PNP_PROVIDERS]
    mov [ss:bp-12],eax
.seen:
    test eax,eax
    jz .validate
    call pnp_pointer
    mov dx,[ss:bp-2]
    cmp [gs:si+P_V_SEG],dx
    je .done
    mov eax,[gs:si+P_V_NEXT]
    jmp .seen
.validate:
    mov ds,dx
    call pnp_rom_outer
    jc .bad
    mov [ss:bp-16],ecx
    mov [ss:bp-18],si
    cmp byte [ss:bp-5],2
    jne .headers_begin
    ; Preserve the display's validated extent before it replaces its header.
    pushad
    push gs
    movzx edx,word [ss:bp-2]
    shl edx,4
    mov esi,1
    mov ax,0x0100
    call pnp_reserve
%ifdef M919_BOARD_DEFINITION
    cmp word [fs:M_VGA_BDF],0xFFFF
    jne .display_reserved
    call pnp_reserve_vga
.display_reserved:
%endif
    pop gs
    popad
.headers_begin:
    mov byte [ss:bp-6],0
.headers:
    test si,si
    jz .legacy
    mov [ss:bp-20],si
    mov ecx,[ss:bp-16]
    call pnp_rom_header
    jc .bad
    mov [ss:bp-22],ax
    cmp dword [ds:si],0x506E5024
    jne .following
    mov byte [ss:bp-6],1
    call .record
    jc .bad
.following:
    mov si,[ss:bp-22]
    jmp .headers
.legacy:
    cmp byte [ss:bp-6],0
    jne .initialize
    mov word [ss:bp-20],0
    call .record
    jc .bad
.initialize:
    mov eax,[fs:PNP_PROVIDERS]
    call pnp_pointer
    mov word [fs:R_ENTRY],3
    mov ax,[ss:bp-2]
    mov [fs:R_ENTRY+2],ax
    mov ax,[ss:bp-4]
    mov bx,[gs:si+P_V_CSN]
    mov dx,[gs:si+P_V_PORT]
    mov cl,[ss:bp-6]
    test cl,cl
    jnz .enter
    mov cl,[ss:bp-5]           ; Selected legacy video retains its old entry ABI.
.enter:
    call CFG_ROM_CODE_SEGMENT:pnp_initialize_callback
    mov [ss:bp-24],ax       ; Capture init AX before the wrapper restores regs.
    call pnp_module_state
    mov eax,[fs:PNP_PROVIDERS]
.status:
    cmp eax,[ss:bp-12]
    je .done
    call pnp_pointer
    mov dx,[ss:bp-24]
    mov [gs:si+P_V_STATUS],dx
    cmp byte [ss:bp-5],2
    jne .next_status
    test byte [gs:si+P_V_INDICATORS],1
    jz .next_status
    test dl,0x0C
    jz .next_status
    cmp word [gs:si+P_V_BCV],0
    je .next_status
    push gs
    push si
    mov ax,[gs:si+P_V_BCV]
    mov [fs:R_ENTRY],ax
    mov ax,[gs:si+P_V_SEG]
    mov [fs:R_ENTRY+2],ax
    mov bx,[gs:si+P_V_CSN]
    mov dx,[gs:si+P_V_PORT]
    mov ax,2               ; Header Display1 becomes BCV Video2.
    mov cl,1
    call CFG_ROM_CODE_SEGMENT:pnp_initialize_callback
    call pnp_module_state
    pop si
    pop gs
    or byte [gs:si+P_V_FLAGS],4
.next_status:
    mov eax,[gs:si+P_V_NEXT]
    jmp .status
.done:
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    clc
    ret
.bad:
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .failed
    call pnp_pointer
    or byte [gs:si+PNP_ROOT_STATUS],2
.failed:
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    stc
    ret
.record:
    mov ecx,PNP_PROVIDER_SIZE
    call pnp_new_object
    jc .record_failed
    mov [ss:bp-28],eax
    mov edx,[fs:PNP_PROVIDERS]
    mov [gs:si+P_V_NEXT],edx
    mov [fs:PNP_PROVIDERS],eax
    inc dword [fs:PNP_PROVIDER_COUNT]
    mov dx,[ss:bp-2]
    mov [gs:si+P_V_SEG],dx
    mov dx,[ss:bp-4]
    mov [gs:si+P_V_BDF],dx
    mov dx,[ss:bp-20]
    mov [gs:si+P_V_HEADER],dx
    mov byte [gs:si+P_V_FLAGS],1
    movzx dx,byte [ds:2]
    mov [gs:si+P_V_UNITS],dx
    mov word [gs:si+P_V_CSN],0xFFFF
    mov word [gs:si+P_V_LDN],0xFFFF
    push eax
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov dx,[gs:si+PNP_ROOT_READ_PORT]
    cmp byte [gs:si+PNP_ROOT_CSN_COUNT],0
    jne .port
    mov dx,0xFFFF
.port:
    pop eax
    call pnp_pointer
    mov [gs:si+P_V_PORT],dx
    cmp word [ss:bp-20],0
    jne .pnp
    or byte [gs:si+P_V_FLAGS],2
    clc
    ret
.pnp:
    mov bx,[ss:bp-20]
    mov dx,[ds:bx+0x16]
    mov [gs:si+P_V_BCV],dx
    mov dx,[ds:bx+0x18]
    mov [gs:si+P_V_DISCONNECT],dx
    mov dx,[ds:bx+0x1A]
    mov [gs:si+P_V_BEV],dx
    mov dl,[ds:bx+0x15]
    mov [gs:si+P_V_INDICATORS],dl
    mov eax,[ss:bp-28]
    call pnp_rom_associate
    clc
    ret
.record_failed:
    stc
    ret

; EAX=provider record. Only an actually allocated ROM domain can associate it
; with an ISA CSN/LDN. Product IDs never identify a physical instance.
pnp_rom_associate:
    pushad
    push gs
    mov ebp,eax
    call pnp_pointer
    movzx edx,word [gs:si+P_V_SEG]
    shl edx,4
    movzx ecx,word [gs:si+P_V_UNITS]
    shl ecx,9
    add ecx,edx
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    mov edi,[gs:si+PNP_ROOT_LDNS]
.ldn:
    test edi,edi
    jz .done
    mov eax,edi
    call pnp_pointer
    test byte [gs:si+PNP_LDN_STATUS],1
    jz .next
    movzx ebx,byte [gs:si+PNP_LDN_NDOM]
    add si,PNP_LDN_DOMAINS
.domain:
    test ebx,ebx
    jz .next
    cmp byte [gs:si],1
    jne .advance
    test byte [gs:si+2],0x40
    jz .advance
    mov eax,[gs:si+20]
    cmp edx,eax
    jb .advance
    add eax,[gs:si+16]
    jc .advance
    cmp ecx,eax
    ja .advance
    mov eax,edi
    call pnp_pointer
    mov dl,[gs:si+PNP_LDN_INDEX]
    mov eax,[gs:si+PNP_LDN_CARD]
    call pnp_pointer
    mov cl,[gs:si+PNP_CARD_CSN]
    mov eax,ebp
    call pnp_pointer
    movzx cx,cl
    mov [gs:si+P_V_CSN],cx
    movzx dx,dl
    mov [gs:si+P_V_LDN],dx
    jmp .done
.advance:
    add si,32
    dec ebx
    jmp .domain
.next:
    mov eax,edi
    call pnp_pointer
    mov edi,[gs:si+PNP_LDN_NEXT]
    jmp .ldn
.done:
    pop gs
    popad
    ret
