; Resident publication. No instruction in this file executes from released
; POST storage. The complete staged object may overlap its final EBDA address.
%include "pc/pnp-runtime-state.inc"
pnp_promote_runtime:
    pushad
    push ds
    push es
    push gs
    mov ebx,[fs:PNP_RUNTIME]
    test ebx,ebx
    jz .bad
    movzx ebp,byte [fs:0]
    shl ebp,10
    lea eax,[ebx+ebp]
    call pnp_runtime_pointer
    cmp dword [gs:si+P_T_MAGIC],PNP_RUNTIME_MAGIC
    jne .bad
    mov dx,[gs:si+P_T_DEST_SEG]
    movzx ecx,byte [gs:si+P_T_TOTAL_KIB]
    push dx
    shl ecx,10
    movzx edx,dx
    shl edx,4
    call pnp_promote_copy
    pop dx
    xor ax,ax
    mov ds,ax
    mov fs,dx
    mov [fs:PNP_RUNTIME],ebp
    mov eax,ebp
    call pnp_runtime_relative
    call pnp_rebase_fdpts
    mov al,[gs:si+P_T_TOTAL_KIB]
    mov [fs:0],al
    mov ax,dx
    shr ax,6
    mov [0x413],ax
    mov [fs:PNP_JOURNAL_EXTERNAL_KIB],ax
    mov [0x40E],dx
    pop gs
    pop es
    pop ds
    popad
    clc
    ret
.bad:
    or byte [fs:C_ERROR],0x40
    pop gs
    pop es
    pop ds
    popad
    stc
    ret

; EAX=linear -> GS:SI, or EAX=offset relative to current FS EBDA.
pnp_runtime_relative:
    push edx
    xor edx,edx
    mov dx,fs
    shl edx,4
    add eax,edx
    pop edx
pnp_runtime_pointer:
    mov si,ax
    and si,15
    shr eax,4
    mov gs,ax
    ret

; EBX=staging start, EDX=final start, ECX=complete advertised byte extent.
; Destination is at/above staging. Normalize each bounded chunk and move from
; the end, so neither linked source records nor overlap order is assumed.
pnp_promote_copy:
    pushad
    mov ebp,ecx
    std
.chunk:
    test ebp,ebp
    jz .done
    mov ecx,ebp
    cmp ecx,0xFFF0
    jbe .size
    mov ecx,0xFFF0
.size:
    sub ebp,ecx
    lea eax,[ebx+ebp]
    mov si,ax
    and si,15
    shr eax,4
    mov ds,ax
    lea eax,[edx+ebp]
    mov di,ax
    and di,15
    shr eax,4
    mov es,ax
    add si,cx
    add di,cx
    sub si,2
    sub di,2
    shr cx,1
    rep movsw
    jmp .chunk
.done:
    cld
    popad
    ret
