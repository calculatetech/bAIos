%ifndef PC_PROCESSOR_PRIMITIVES
%define PC_PROCESSOR_PRIMITIVES

; CF clear: qualified board Stop Grant path. Preserve all other caller state.
; Both optional inline providers must work in BITS16 and BITS32.
%macro cpu_idle_query 0
%ifmacro board_stop_grant_query 0
%ifnmacro board_stop_grant_idle 0
%fatal "Stop Grant requires both board_stop_grant_query and board_stop_grant_idle"
%endif
    pushfd
    pushad
    board_stop_grant_query
    jc %%unavailable
    popad
    popfd
    clc
    jmp %%done
%%unavailable:
    popad
    popfd
    stc
%%done:
%else
%ifmacro board_stop_grant_idle 0
%fatal "Stop Grant requires both board_stop_grant_query and board_stop_grant_idle"
%endif
    stc
%endif
%endmacro

; Providers preserve segments/stack and own atomic request and IRQ sequencing.
; CF-set decline precedes sleep: STPCLK released, no wake consumed.
%macro cpu_idle 0-1 1
%ifmacro board_stop_grant_query 0
    pushfd
    pushad
%if !%1
%ifndef BOARD_STOP_GRANT_V86
    ; Other adapters may require a privileged caller; V86 belongs to its monitor.
    smsw ax
    test al,1
    jnz %%fallback
%endif
%endif
    cpu_idle_query
    jc %%fallback
    board_stop_grant_idle
    jc %%fallback
    popad
    popfd
    jmp %%done
%%fallback:
    popad
    popfd
%else
%ifmacro board_stop_grant_idle 0
%fatal "Stop Grant requires both board_stop_grant_query and board_stop_grant_idle"
%endif
%endif
    pushf
    sti
    hlt
    popf
%%done:
%endmacro

%macro cpu_cache_flush 0
%ifndef BOARD_CPU_386
    wbinvd
%endif
%endmacro

%macro cpu_cache_disable 0
%ifndef BOARD_CPU_386
    or eax,0x60000000
%endif
%endmacro

%macro board_a20_read 0
%ifdef BOARD_A20_READ
    call BOARD_A20_READ
%else
    in al,0x92
%endif
%endmacro

%macro board_a20_write 0
%ifdef BOARD_A20_WRITE
    call BOARD_A20_WRITE
%else
    out 0x92,al
%endif
%endmacro

%macro cpu_swap_eax 0
%ifdef BOARD_CPU_386
    pushf
    xchg al,ah
    ror eax,16
    xchg al,ah
    popf
%else
    bswap eax
%endif
%endmacro
%endif
