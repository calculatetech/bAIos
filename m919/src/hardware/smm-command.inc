%ifndef M919_SMM_COMMAND_MACROS
%define M919_SMM_COMMAND_MACROS
; Shared by the real-mode extension and inline protected-mode idle adapters.
%define SMM_HB (0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11))
%define SMM_SB (0x80000000 | (CFG_PLATFORM_ISA_PCI_DEVICE << 11))

%macro smm_read 2
    mov eax,%1 | ((%2) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%2) & 3)
    in al,dx
%endmacro
%macro smm_write 3
    mov eax,%1 | ((%2) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%2) & 3)
    mov al,%3
    out dx,al
%endmacro

%macro m919_smm_command_code 0-1 0
    pushfd
    cli
    pushad
    movzx ecx,ax
    or ecx,0x04000000
    mov dx,0xCF8
    in eax,dx
    mov ebp,eax
    smm_read SMM_SB,0xA0
    push ax
    smm_read SMM_SB,0xA8
    push ax
%if !%1
    mov esi,cr0
    smm_read SMM_HB,0x50
    movzx edx,al
    shl edx,16
    mov al,0x8D
    out 0x70,al
    wbinvd
    mov eax,esi
    or eax,0x60000000
    mov cr0,eax
    mov eax,SMM_HB | 0x50
    mov dx,0xCF8
    out dx,eax
    mov eax,edx
    shr eax,16
    and al,0x7F
    mov dx,0xCFC
    out dx,al
%else
    ; APM also enters from V86. Only the SMM handler may touch CR0/caches.
    mov al,0x8D
    out 0x70,al
%endif
    ; Both fields survive the reference's PM-disable/software-SMI path.
    smm_read SMM_SB,0xA0
    or al,0x34
    out dx,al
    smm_read SMM_SB,0xA8
    or al,0x28
    out dx,al
    smm_read SMM_SB,0xA3
    and al,0x3F
    or al,0x80                  ; Arm SMI before its request edge, as in the reference.
    out dx,al
    mov edi,0xA0000
    mov ebx,SMM_REQUEST
    or al,0x40
    out dx,al
%%wait:
    cmp ebx,SMM_REPLY
    je %%reply
    sub ecx,0x10000
    cmp ecx,0x10000
    jae %%wait
    mov eax,4
%%reply:
    mov edi,eax
    smm_read SMM_SB,0xA3
    and al,0xBF
    out dx,al
    pop ecx                     ; Saved A8 word, followed by saved A0 word.
    mov ebx,ecx
    shr ecx,16
%if %1
    ; Successful idle returned full-on; old A0 mode bits are not live policy.
    test edi,edi
    jnz %%restore_a0
    and cl,0xFC
%%restore_a0:
%endif
    smm_write SMM_SB,0xA0,cl
    smm_write SMM_SB,0xA8,bl
%if !%1
    mov eax,SMM_HB | 0x50
    mov dx,0xCF8
    out dx,eax
    mov eax,edx
    shr eax,16
    mov dx,0xCFC
    out dx,al
    invd                        ; Flush preceded disable; discard only clean stale tags.
    mov cr0,esi
%endif
    mov eax,ebp
    mov dx,0xCF8
    out dx,eax
%if %1
    mov al,RTC_NMI_SELECT_MASK | 0x0D
    out 0x70,al
%endif
%if %1
    ; Outer cpu_idle owns register preservation. Avoid assuming SS.B or ESP size.
    mov ax,di
    pop edi
    pop esi
    pop ebp
    pop ebx                     ; PUSHAD's unused original ESP.
    pop ebx
    pop edx
    pop ecx
    pop ebx                     ; Discard original EAX; AX holds command status.
    popfd
    test ax,ax
    jz %%ok
    stc
    jmp %%return
%%ok:
    clc
%%return:
%else
    mov bp,sp
    mov [ss:bp+28],di
    or dword [ss:bp+32],1
    test edi,edi
    jnz %%return
    and dword [ss:bp+32],0xFFFFFFFE
%%return:
    popad
    popfd
%endif
%endmacro

%endif
