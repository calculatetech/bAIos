; Keep code, an8K bounce, metadata and stack in the established upper SMRAM.
; Intel486 Table8-3 supplies flat physical DS, PE/PG off, and32-bit limits.
%define SMM_ESCD_BUFFER 0x9000
%define SMM_ESCD 0xB000
board_escd_smm_entry:
    ; Final SMBASE is A0000; normalize CS before the first stack access.
    jmp 0xA000:(0x8000+.relocated-board_smm_image)
.relocated:
    mov ax,cs
    mov ss,ax
    mov esp,0xFCF0
    mov es,ax
    cld
    wbinvd
    mov ax,[cs:0xFFD4]
    mov [cs:SMM_ESCD],ax
    mov eax,[cs:0xFFE8]
    mov [cs:SMM_ESCD+4],eax
    movzx edx,word [cs:0xFFA8] ; Saved ES in the 486 SMM state map.
    shl edx,4
    sub eax,edx
    mov [cs:SMM_ESCD+12],ax
    test dword [cs:0xFFF4],0x20000
    jz .error
    cmp word [cs:SMM_ESCD],5
    jne .read
    ; Read the size through the saved paging map before accepting the input.
    mov eax,[cs:SMM_ESCD+4]
    call board_escd_smm_translate
    jc .error
    movzx ecx,byte [ds:esi]
    inc eax
    call board_escd_smm_translate
    jc .error
    mov ch,[ds:esi]
    cmp cx,14
    jb .error
    cmp cx,8192
    ja .error
    call board_escd_smm_pages
    jc .error
    call board_escd_smm_copy
    mov ax,0x43
    jmp .invoke
.read:
    mov ax,0x42
.invoke:
    mov dx,cs
    mov es,dx
    push word 0x40
    push word (BOARD_ESCD_BASE >> 4)
    push es
    push word SMM_ESCD_BUFFER
    push ax
    call CFG_ROM_CODE_SEGMENT:pnp_real_entry
    add sp,10
    test ax,ax
    jnz .reply
    cmp word [cs:SMM_ESCD],4
    jne .reply
    movzx ecx,word [es:SMM_ESCD_BUFFER]
    cmp cx,14
    jb .error
    cmp cx,8192
    ja .error
    call board_escd_smm_pages
    jc .error
    call board_escd_smm_copy
    xor ax,ax
    jmp .reply
.error:
    mov ax,0x55
.reply:
    wbinvd
    movzx eax,ax
    mov [cs:0xFFD0],eax
    and dword [cs:0xFFF4],0xFFFFFFFE
    test ax,ax
    jz .ok
    or dword [cs:0xFFF4],1
.ok:
    mov eax,[cs:0xFEFC]
    mov [cs:0xFFD4],eax
    mov dword [cs:0xFFDC],SMM_REPLY
    rsm

; Validate every translated page before copying any caller data.
board_escd_smm_pages:
    movzx eax,word [cs:SMM_ESCD+12]
    add eax,ecx
    cmp eax,0x10000
    ja .bad
    mov eax,[cs:SMM_ESCD+4]
    xor edi,edi
.page:
    call board_escd_smm_translate
    jc .bad
    mov [cs:SMM_ESCD+0x40+edi],edx
    mov edx,eax
    and edx,0xFFF
    neg edx
    add edx,0x1000
    cmp edx,ecx
    jbe .chunk
    mov edx,ecx
.chunk:
    push esi
    add esi,edx
    dec esi
    call board_escd_smm_ram
    pop esi
    jc .bad
    mov [cs:SMM_ESCD+0x20+edi],esi
    mov [cs:SMM_ESCD+0x24+edi],dx
    add edi,8
    cmp edi,24
    ja .bad
    add eax,edx
    sub ecx,edx
    jnz .page
    mov [cs:SMM_ESCD+14],di
    clc
    ret
.bad:
    stc
    ret

board_escd_smm_copy:
    xor ebx,ebx
    xor ebp,ebp
.page:
    movzx ecx,word [cs:SMM_ESCD+0x24+ebx]
    cmp word [cs:SMM_ESCD],5
    jne .output
    mov esi,[cs:SMM_ESCD+0x20+ebx]
    lea edi,[ebp+SMM_ESCD_BUFFER]
    jmp .copy
.output:
    ; All output pages passed validation. Mark the page that receives data.
    test dword [cs:0xFFFC],0x80000000
    jz .output_address
    mov edx,[cs:SMM_ESCD+0x40+ebx]
    or byte [ds:edx],0x40
.output_address:
    xor ax,ax
    mov es,ax
    mov ax,cs
    movzx esi,ax
    shl esi,4
    add esi,ebp
    add esi,SMM_ESCD_BUFFER
    mov edi,[cs:SMM_ESCD+0x20+ebx]
.copy:
    add ebp,ecx
    a32 rep movsb
    add bx,8
    cmp bx,[cs:SMM_ESCD+14]
    jb .page
    ret

; EAX linear -> ESI physical, EDX leaf entry address when paging is enabled.
board_escd_smm_translate:
    push ebx
    push ecx
    mov ebx,eax
    mov esi,eax
    test dword [cs:0xFFFC],0x80000000
    jz .physical
    mov esi,[cs:0xFFF8]
    and esi,0xFFFFF000
    call board_escd_smm_ram_page
    jc .bad
    mov edx,eax
    shr edx,22
    lea edx,[esi+edx*4]
    mov esi,[ds:edx]
    mov ecx,esi
    and cl,0x85
    cmp cl,5
    jne .bad
    cmp word [cs:SMM_ESCD],4
    jne .directory_readable
    test si,2
    jz .bad
.directory_readable:
    or byte [ds:edx],0x20
    and esi,0xFFFFF000
    call board_escd_smm_ram_page
    jc .bad
    mov edx,eax
    shr edx,12
    and edx,0x3FF
    lea edx,[esi+edx*4]
    mov esi,[ds:edx]
    mov ecx,esi
    and cl,5
    cmp cl,5
    jne .bad
    cmp word [cs:SMM_ESCD],4
    jne .readable
    test si,2
    jz .bad
.readable:
    or byte [ds:edx],0x20
    and esi,0xFFFFF000
    and ebx,0xFFF
    or esi,ebx
.physical:
    call board_escd_smm_ram
    jmp .done
.bad:
    stc
.done:
    pop ecx
    pop ebx
    ret
board_escd_smm_ram:
    cmp esi,0xA0000
    jb .low
    cmp esi,0x100000
    jb .bad
.low:
    cmp esi,[ds:0x400+PNP_RAM_END]
    jae .bad
    clc
    ret
.bad:
    stc
    ret
board_escd_smm_ram_page:
    push esi
    add esi,4095
    call board_escd_smm_ram
    pop esi
    ret
