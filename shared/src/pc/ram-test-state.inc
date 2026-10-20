; AL=persisted RAM-test marker. AX=normal-startup update for CMOS36.
; An unfinished test does not prove failure; only committed notices survive.
%macro ram_test_startup_state 0
    cmp al,0x5A
    je %%pending
    cmp al,0xDA
    je %%pending
    mov ax,0x0036
    jmp %%ready
%%pending:
    mov ax,0xDA36
%%ready:
%endmacro
