; The extension must read back before the shorter CAS pulse can be written.
%macro profile_write 3
    mov al,%1
    out 0xF2,al
    out 0xED,al
    mov al,%2
    out 0xF3,al
    out 0xED,al
    in al,0xF3
    out 0xED,al
    mov ah,%3
    cmp al,ah
%endmacro

%macro timing_write 1
%ifidni %1,bl
    test bl,bl
    jnz %%restore
    profile_write 0x16,0x03,0x03
    jne .register_bad
    profile_write 0x19,0x28,0x28
    jne .register_bad
    profile_write 0x01,0x83,0xAF
    jne .register_bad
    mov al,0x0B
    out 0xF2,al
    out 0xED,al
    xor al,al
    out 0xF3,al
    out 0xED,al
    jmp %%done
%endif
%%restore:
    ; Recover the longer CAS first. Retry every field before interrupts or stores.
    profile_write 0x0B,0x04,0x04
    jne %%restore
    profile_write 0x16,0x00,0x00
    jne %%restore
    profile_write 0x19,0x08,0x08
    jne %%restore
    profile_write 0x01,0x93,0xBF
    jne %%restore
    mov al,0x0B
    out 0xF2,al
    out 0xED,al
%%done:
%endmacro
