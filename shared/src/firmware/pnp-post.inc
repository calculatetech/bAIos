%ifndef PNP_STATE_LOAD
%define PNP_STATE_LOAD load_bios_state
%endif
; One POST-only arena, dynamically bounded by reported conventional memory.
; Its control header occupies the audited gap after C/U_PNP and before the
; slave model at340h, including on the one-KiB Presario EBDA.
%include "pc/pnp-post-state.inc"

pnp_journal_begin:
    pushad
    push ds
    call PNP_STATE_LOAD
    xor ax,ax
    mov ds,ax
    mov ax,[0x413]
    mov [fs:PNP_JOURNAL_ORIGINAL_KIB],ax
    mov [fs:PNP_JOURNAL_EXTERNAL_KIB],ax
    movzx eax,ax
    shl eax,10
    mov [fs:PNP_JOURNAL_CURSOR],eax
    mov [fs:PNP_JOURNAL_END],eax
    mov dword [fs:PNP_JOURNAL_COUNT],0
    mov dword [fs:PNP_JOURNAL_FIRST],0
    mov dword [fs:PNP_JOURNAL_FLAGS],0
    cmp eax,PNP_JOURNAL_FLOOR
    pop ds
    popad
    ja .ready
    stc
    ret
.ready:
    clc
    ret

; ECX=bytes; EAX=linear allocated address, CF=natural capacity exhaustion.
; No arena/BDA mutation on failure. There is no card/LDN/metadata count cap.
pnp_journal_allocate:
    push ebx
    push ecx
    push edx
    push ds
    call PNP_STATE_LOAD
    xor ax,ax
    mov ds,ax
    mov eax,[fs:PNP_JOURNAL_CURSOR]
    mov ebx,eax
    shr ebx,10
    movzx edx,word [0x413]
    cmp edx,ebx
    jae .size
    ; A returning ROM reserved more conventional memory below our arena.
    ; Preserve that owner, including when a later journal record is appended.
    mov eax,edx
    shl eax,10
.size:
    test ecx,ecx
    jz .bad
    add ecx,3
    jc .bad
    and ecx,~3
    sub eax,ecx
    jc .bad
%ifdef PB430_PORT
    ; The unchanged shadow/video owners stage through20000h..3FFFFh.
    ; No live object may overlap that existing fixed scratch owner.
    cmp eax,0x40000
    jae .scratch_clear
    cmp edx,0x80            ; A returning consumer may already bound us below it.
    jbe .scratch_clear
    cmp dword [fs:PNP_JOURNAL_CURSOR],0x20000
    jbe .scratch_clear
    mov eax,0x20000
    sub eax,ecx
    jc .bad
.scratch_clear:
%endif
    cmp eax,PNP_JOURNAL_FLOOR
    jb .bad
    cmp edx,ebx
    jae .accounted
    mov [fs:PNP_JOURNAL_EXTERNAL_KIB],dx
.accounted:
    mov [fs:PNP_JOURNAL_CURSOR],eax
    mov ebx,eax
    shr ebx,10
    mov [0x413],bx
    pop ds
    pop edx
    pop ecx
    pop ebx
    clc
    ret
.bad:
    pop ds
    pop edx
    pop ecx
    pop ebx
    stc
    ret

%ifndef M919_BOARD_DEFINITION
%include "firmware/pnp-post-release.inc"
%endif
pnp_post_code_end:
