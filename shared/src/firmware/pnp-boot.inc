; Resident boot continuation. Every durable reference is relative to the current
; advertised EBDA; the POST list, private code and sector buffer are not owners.
%include "pc/pnp-runtime-state.inc"
%include "firmware/pnp-runtime-open.inc"
%ifdef PB430_PORT
%include "hardware/pnp-warm.inc"
%endif

; GS:SI=current header, FS=new base. Only actual BIOS FDPT aliases follow it.
; Caller-owned external pointers, counts, INT13 and CD predecessor stay intact.
pnp_rebase_fdpts:
    pushad
    push es
    mov bp,[gs:si+P_T_BASE_SEG]
    mov bx,fs
    xor ax,ax
    mov es,ax
    mov di,0x104
    call .pointer
    mov di,0x118
    call .pointer
    push gs
    pop es
    lea di,[si+P_T_FDPT0]
    call .pointer
    add di,4
    call .pointer
    mov [gs:si+P_T_BASE_SEG],bx
    pop es
    popad
    ret
.pointer:
    cmp word [es:di],S_FDPT
    jne .done
    mov ax,[es:di+2]
    mov dx,bp
    mov cx,BOARD_ATA_DEVICE_COUNT
.position:
    cmp ax,dx
    je .rebase
    add dx,0x20
    loop .position
    ret
.rebase:
    sub ax,bp
    add ax,bx
    mov [es:di+2],ax
.done:
    ret

; A successful BIOS-owned transfer always supplies the real installation.
pnp_boot_handoff:
%ifndef EMULATOR_PNP_PARTIAL
    push ax
    mov ax,0xF000
    mov es,ax
    mov di,pnp_installation
    pop ax
%endif
    ret

pnp_other_begin:
    call pnp_runtime_open
    jc pnp_other_legacy
    mov dword [gs:si+P_T_CURSOR],0
    or byte [gs:si+P_T_FLAGS],1
pnp_other_next:
    call pnp_runtime_open
    jc pnp_other_legacy
    mov eax,[gs:si+P_T_CURSOR]
    cmp eax,[gs:si+P_T_COUNT]
    jae .end
    inc dword [gs:si+P_T_CURSOR]
    inc eax
    mov [gs:si+P_T_ACTIVE],eax
    dec eax
    imul eax,PNP_PROVIDER_BYTES
    add eax,P_T_SIZE
    add eax,[fs:PNP_RUNTIME]
    call pnp_runtime_relative
    test byte [gs:si+P_V_FLAGS-4],2
    jnz pnp_other_next
    test byte [gs:si+P_V_INDICATORS-4],4
    jz pnp_other_next
    mov ax,[gs:si+P_V_STATUS-4]
    and al,0x30
    jz pnp_other_next
    cmp al,0x30
    je pnp_other_next
    test ah,1
    jz .bev
    cmp word [gs:si+P_V_BCV-4],0
    je pnp_other_next
    call pnp_connection_snapshot
    mov cx,P_V_BCV-4
    mov ax,4
    call pnp_call_provider
    call pnp_runtime_open
    jc pnp_other_legacy
    mov eax,[0x60]
    mov [gs:si+P_T_HOOK18],eax
    mov eax,[0x64]
    mov [gs:si+P_T_HOOK19],eax
    call pnp_boot_route
    mov dl,[gs:si+P_T_HDD]
    cmp dl,[0x475]
    jae .floppy
    test dl,0x80
    jnz .failed
    add dl,0x80
    jmp .read
.floppy:
    mov ax,[gs:si+P_T_EQUIPMENT]
    call .floppy_count
    mov dl,al
    mov ax,[0x410]
    call .floppy_count
    cmp dl,al
    jae .failed
.read:
    xor dh,dh             ; Connected providers receive cylinder0/head0/sector1.
    xor ax,ax
    mov es,ax
    jmp boot_read
.floppy_count:
    test al,1
    jnz .present
    xor ax,ax
    ret
.present:
    shr ax,6
    and al,3
    inc al
    ret
.failed:
    jmp boot_candidate
.bev:
    cmp word [gs:si+P_V_BCV-4],0
    jne pnp_other_next
    cmp word [gs:si+P_V_BEV-4],0
    je pnp_other_next
    mov cx,P_V_BEV-4
    xor ax,ax
    call pnp_call_provider
    jmp boot_candidate
.end:
    and byte [gs:si+P_T_FLAGS],~1
    mov dword [gs:si+P_T_ACTIVE],0
pnp_other_legacy:
    cmp dword [fs:B_ROM19],0
    je boot_candidate
    mov byte [fs:B_ACTIVE],0xA6  ; Explicit legacy-chain provenance.
    mov eax,[fs:B_ROM19]
    mov [fs:R_ENTRY],eax
    xor ax,ax
    mov bx,0xFFFF
    mov dx,0xFFFF
    call pnp_boot_handoff
    call boot_pnp_call
    jmp boot_candidate

; GS:SI=selected payload, CX=callback word offset, AX=role (init uses BDF).
pnp_call_provider:
    push ax
    mov bx,cx
    mov ax,[gs:si+bx]
    mov [fs:R_ENTRY],ax
    mov ax,[gs:si+P_V_SEG-4]
    mov [fs:R_ENTRY+2],ax
    mov bx,[gs:si+P_V_CSN-4]
    mov dx,[gs:si+P_V_PORT-4]
    call pnp_boot_handoff
    pop ax
    call boot_pnp_call
    jmp load_bios_state

pnp_connection_snapshot:
    pushad
    push gs
    mov edi,[fs:PNP_RUNTIME]
    mov eax,edi
    call pnp_runtime_relative
    or byte [gs:si+P_T_FLAGS],2 ; Persist before BCV may enter external control.
    mov al,[0x475]
    mov [gs:si+P_T_HDD],al
    mov ax,[0x410]
    mov [gs:si+P_T_EQUIPMENT],ax
    xor ax,ax
    call pnp_boot_vectors
    pop gs
    popad
    ret

pnp_disconnect_active:
    call pnp_runtime_open
    jc .done
    test byte [gs:si+P_T_FLAGS],2
    jz .done
    and byte [gs:si+P_T_FLAGS],~2 ; Exactly once, including a returning vector.
    mov eax,[gs:si+P_T_ACTIVE]
    test eax,eax
    jz .restore
    dec eax
    imul eax,PNP_PROVIDER_BYTES
    add eax,P_T_SIZE
    add eax,[fs:PNP_RUNTIME]
    call pnp_runtime_relative
    cmp word [gs:si+P_V_DISCONNECT-4],0
    je .restore
    mov cx,P_V_DISCONNECT-4
    xor ax,ax
    call pnp_call_provider
.restore:
    call pnp_runtime_open
    jc .done
    mov ax,1
    call pnp_boot_vectors
    mov al,[gs:si+P_T_HDD]
    mov [0x475],al
    mov ax,[gs:si+P_T_EQUIPMENT]
    mov [0x410],ax
    mov dword [gs:si+P_T_ACTIVE],0
.done:
    ret

%ifndef PB430_PORT
%include "firmware/pnp-boot-route.inc"
%endif

; Header snapshot and restoration use the same existing vector identities.
; AL=0 captures; AL=1 restores. BIOS18/19 routing is asserted by the caller.
pnp_boot_vectors:
    pushad
    mov bp,ax
    mov bx,.offsets
    lea di,[si+P_T_OLD13]
    mov cx,5
.next:
    movzx edx,word [cs:bx]
    test bp,bp
    jnz .restore
    mov eax,[edx]
    mov [gs:di],eax
    jmp .advance
.restore:
    mov eax,[gs:di]
    mov [edx],eax
.advance:
    add bx,2
    add di,4
    loop .next
    popad
    ret
.offsets: dw 0x4C,0x60,0x64,0x104,0x118
