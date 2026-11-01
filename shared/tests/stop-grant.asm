bits 16
org 0

%ifdef LATE_PROVIDER
%include "pc/processor.inc"
%endif

; Synthetic external provider ABI, not a chipset driver.
%ifdef PROVIDER
%ifndef ONLY_IDLE
%macro board_stop_grant_query 0
    in al,0xE0
    mov ebx,0x12345678
    std
    cmp al,1
    je %%ready
    stc
    jmp %%done
%%ready:
    clc
%%done:
%endmacro
%endif
%ifndef ONLY_QUERY
%macro board_stop_grant_idle 0
    in al,0xE1
    cmp al,1
    jne %%decline
    mov eax,1
    mov edi,0x87654321
    sti
    out 0xE2,al
    clc
    jmp %%done
%%decline:
    stc
%%done:
%endmacro
%endif
%endif

%include "pc/processor.inc"
dd query16,idle16,query32,idle32,int15,apm_pm16,apm_pm32,irq16,irq32
query16:
    cpu_idle_query
    ret
idle16:
    cpu_idle
    ret
int15:
    push bp
    mov bp,sp
    jmp apm_int15
%include "load-bios-state.inc"
irq16:
    inc dword [cs:0x6000]
    iret
bits 32
query32:
    cpu_idle_query
    ret
idle32:
    cpu_idle
    ret
irq32:
    inc dword [cs:0x6000]
    iretd
bits 16
%include "firmware/apm.inc"
