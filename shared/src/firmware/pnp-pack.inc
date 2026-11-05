; Pack only durable provider metadata and the complete current EBDA prefix.
; The new staging object is separately charged below every live source/code
; interval. It stays owned through the private epilogue and far return.
pnp_pack_runtime:
    pushad
    push ds
    push es
    push gs
    mov bp,sp
    sub sp,28
    movzx eax,byte [fs:0]
    test eax,eax
    jz .bad
    mov [ss:bp-1],al
    shl eax,10
    mov [ss:bp-8],eax
    mov ecx,[fs:PNP_PROVIDER_COUNT]
    imul ecx,PNP_PROVIDER_BYTES
    jo .bad
    add ecx,eax
    jc .bad
    add ecx,P_T_SIZE+1023
    jc .bad
    shr ecx,10
    cmp ecx,255             ; The standard EBDA size field is one byte.
    ja .bad
    mov [ss:bp-2],cl
    shl ecx,10
    mov [ss:bp-12],ecx
    movzx edx,word [fs:PNP_JOURNAL_EXTERNAL_KIB]
    shl edx,10
    xor eax,eax
    mov ax,fs
    shl eax,4
    mov [ss:bp-16],eax
    cmp edx,eax
    jb .external_end
    add eax,[ss:bp-8]       ; Extend existing prefix only across owned memory.
    mov edx,eax
.external_end:
    sub edx,ecx
    jc .bad
    cmp edx,PNP_JOURNAL_FLOOR
    jb .bad
    shr edx,4
    mov [ss:bp-18],dx
    call PNP_ALLOCATE
    jc .bad
    mov [ss:bp-24],eax
    mov edi,eax
    mov eax,[ss:bp-16]
    mov ecx,[ss:bp-8]
    call pnp_stage_copy
    mov eax,[ss:bp-24]
    add eax,[ss:bp-8]
    mov [ss:bp-28],eax
    call pnp_pointer
    push si
    mov cx,P_T_SIZE/4
    xor eax,eax
.zero:
    mov [gs:si],eax
    add si,4
    loop .zero
    pop si
    mov dword [gs:si+P_T_MAGIC],PNP_RUNTIME_MAGIC
    mov eax,[fs:PNP_PROVIDER_COUNT]
    mov [gs:si+P_T_COUNT],eax
    mov al,[ss:bp-1]
    mov [gs:si+P_T_PREFIX_KIB],al
    mov ax,[fs:PNP_JOURNAL_ORIGINAL_KIB]
    mov [gs:si+P_T_ORIGINAL_KIB],ax
    mov ax,[fs:PNP_JOURNAL_EXTERNAL_KIB]
    mov [gs:si+P_T_EXTERNAL_KIB],ax
    mov ax,[ss:bp-18]
    mov [gs:si+P_T_DEST_SEG],ax
    mov al,[ss:bp-2]
    mov [gs:si+P_T_TOTAL_KIB],al
    mov ax,fs
    mov [gs:si+P_T_BASE_SEG],ax
    mov eax,[fs:PNP_PROVIDERS]
    mov ebx,[fs:PNP_PROVIDER_COUNT]
.record:
    test eax,eax
    jz .complete
    test ebx,ebx
    jz .bad
    push eax
    call pnp_pointer
    mov edx,[gs:si+P_V_NEXT]
    pop eax
    push edx
    add eax,4
    dec ebx
    imul edi,ebx,PNP_PROVIDER_BYTES
    add edi,[ss:bp-28]
    add edi,P_T_SIZE
    mov ecx,PNP_PROVIDER_BYTES
    call pnp_stage_copy
    pop eax
    jmp .record
.complete:
    test ebx,ebx
    jnz .bad
    mov eax,[ss:bp-24]
    mov [fs:PNP_RUNTIME],eax ; Remains linear until resident publication.
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    clc
    ret
.bad:
    mov dword [fs:PNP_RUNTIME],0
    or byte [fs:C_ERROR],0x40
    mov sp,bp
    pop gs
    pop es
    pop ds
    popad
    stc
    ret

; EAX source, EDI destination, ECX even bytes, disjoint forward copy.
; Each normalized segment chunk stays within its real-mode64KiB limit.
pnp_stage_copy:
    pushad
    push ds
    push es
    mov ebx,eax
    mov edx,edi
    mov ebp,ecx
    cld
.chunk:
    test ebp,ebp
    jz .done
    mov ecx,ebp
    cmp ecx,0xFFF0
    jbe .size
    mov ecx,0xFFF0
.size:
    sub ebp,ecx
    mov eax,ebx
    shr eax,4
    mov ds,ax
    mov si,bx
    and si,15
    add ebx,ecx
    mov eax,edx
    shr eax,4
    mov es,ax
    mov di,dx
    and di,15
    add edx,ecx
    shr cx,1
    rep movsw
    jmp .chunk
.done:
    pop es
    pop ds
    popad
    ret
