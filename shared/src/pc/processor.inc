%ifndef PC_PROCESSOR_PRIMITIVES
%define PC_PROCESSOR_PRIMITIVES

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
