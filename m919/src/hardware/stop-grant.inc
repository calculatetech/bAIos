%ifndef M919_STOP_GRANT_MACROS
%define M919_STOP_GRANT_MACROS
%define BOARD_STOP_GRANT_V86 1
; APM owns DS:state in all three entry modes. Installation qualified CPU/bridge.
%macro board_stop_grant_query 0
    cmp byte [ds:HW_SMM_STATUS],1
    jne %%no
    mov dx,0xCF8
    in eax,dx
    mov ebp,eax
    smm_read SMM_SB,0x76
    and al,0x30
    mov bl,al
    mov eax,ebp
    mov dx,0xCF8
    out dx,eax
    test bl,bl
    jz %%yes
%%no:
    stc
    jmp %%done
%%yes:
    clc
%%done:
%endmacro

%macro board_stop_grant_idle 0
%if __BITS__ = 32
    ; APM's consecutive selectors give PM32 its matching 16-bit F code at CS+8.
    mov ax,cs
    add ax,8
    push ax
    push word m919_idle_pm32
    o16 call far [ss:esp]
    lea esp,[esp+4]
%else
    call m919_idle_command
%endif
    jc %%done
    ; No IRQ is acknowledged inside SMM. STI's shadow closes the HLT race.
    sti
    hlt
    cli
    clc
%%done:
%endmacro
%endif
