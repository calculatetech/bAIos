; OEM0712..07BD owns the ATU; callers use a ROM return word, not a RAM stack.
mitsubishi_atu_initialize:
    cli
    mov ax,0x0800
    out 0x26,ax
    in ax,0x24
    and ah,3
    xor ah,2
    jnz mitsubishi_atu_failed
    mov cx,4
    mov dx,0x0808
.clear_devices:
    mov ax,dx
    out 0x26,ax
    xor ax,ax
    out 0x24,ax
    inc dl
    loop .clear_devices
    mov cx,4
    mov dx,0x0840
.clear_checked:
    mov ax,dx
    out 0x26,ax
    xor ax,ax
    out 0x24,ax
    mov ax,dx
    out 0x26,ax
    in ax,0x24
    test ax,ax
    jnz mitsubishi_atu_failed
    inc dl
    loop .clear_checked
    mov cx,3
    mov dx,0x0845
.set_devices:
    mov ax,dx
    out 0x26,ax
    mov ax,4
    out 0x24,ax
    inc dl
    loop .set_devices
    in al,0x49
    mov ah,6
    test al,1
    jz .clock_high
    inc ah
.clock_high:
    mov bh,ah
    mov ax,0x0800
    out 0x26,ax
    in ax,0x24
    test ah,0xF0
    jz .old_atu
    mov al,0x80
    jmp .clock_low
.old_atu:
    mov ah,0xA4
    in al,0x49
    test al,6
    jnz .old_clock
    mov ah,0x80
.old_clock:
    mov al,ah
.clock_low:
    mov ah,bh
    mov dx,0x0801
    xchg ax,dx
    out 0x26,ax
    xchg ax,dx
    out 0x24,ax
    mov ax,0x0015
    mov bx,ax
    inc dl
    xchg ax,dx
    out 0x26,ax
    xchg ax,dx
    out 0x24,ax
    mov ax,dx
    out 0x26,ax
    in ax,0x24
    and ax,0x003F
    cmp ax,bx
    jne mitsubishi_atu_failed
    xor ax,ax
    inc dl
    xchg ax,dx
    out 0x26,ax
    xchg ax,dx
    out 0x24,ax
    mov ax,dx
    out 0x26,ax
    in ax,0x24
    test ax,ax
    jnz mitsubishi_atu_failed
mitsubishi_atu_end:
    ret
mitsubishi_atu_failed:
    jmp hard_halt

%macro mitsubishi_control_write 2
    mov al,%1
    out 0x5A,al
    jmp short $+2
    mov al,%2
    out 0x5B,al
    jmp short $+2
%endmacro

; OEM92EB..93BE cache-Off path, before the first linear RAM test.
; Unused OEM2FF bookkeeping is omitted; no RAM access is added inside E2.
mitsubishi_cache_off_initialize:
    pushf
    pushad
    cli
    in al,0x5F
    test al,0x80
    jz mitsubishi_cache_off_end
mitsubishi_cache_off_begin:
    mov al,0xE2
    mov bp,.e2_read
    jmp .read
.e2_read:
    or al,2
    mov ah,al
    mov al,0xE2
    mov cx,ax
    mov bp,.e2_open
    jmp .write
.e2_open:
    in al,0x5F
    test al,0x80
    jnz .off
    jmp .restore_e2
.off:
    xor ah,ah
    jmp .set_e0
.set_e0:
    mov al,0xE0
    mov bh,ah
    mov bp,.e0_written
    jmp .write
.e0_written:
    mov ah,bh
.restore_e2:
    mov ax,cx
    and ah,0xFD
    mov bp,mitsubishi_cache_off_end
    jmp .write
.read:
    cli
    out 0x5A,al
    jmp short $+2
    in al,0x5B
    jmp short $+2
    jmp bp
.write:
    cli
    out 0x5A,al
    jmp short $+2
    mov al,ah
    out 0x5B,al
    jmp short $+2
    jmp bp
mitsubishi_cache_off_end:
    popad
    popf
    ret

; OEM0BEF reset classification precedes PIT1; controls0D2F follow it.
%macro mitsubishi_board_reset_kind 0
    cli
    movzx ecx,ax
    shl ecx,16
    in al,0x5E
    test al,1
    jnz %%kind_one
    test al,4
    jnz %%kind_two
    mov al,0x80
    out 0x8E,al
    xor cx,cx
    jmp %%done
%%kind_one:
    xor al,al
    out 0x8E,al
    jmp short $+2
    jmp short $+2
    mov cl,1
    jmp %%kind_selected
%%kind_two:
    mov al,0x80
    out 0x8E,al
    jmp short $+2
    jmp short $+2
    mov cl,2
%%kind_selected:
    mov al,0xE6
    out 0x5A,al
    jmp short $+2
    in al,0x5B
    jmp short $+2
    mitsubishi_control_write 0xE6,cl
%%done:
%endmacro

; Keep CL/upperECX from reset classification across the ROM/PIT witnesses.
; bAIos uses explicit defaults instead of unqualified OEM saved policy.
%macro mitsubishi_board_controls 0
    mitsubishi_control_write 0x92,0
    mitsubishi_control_write 0xE7,0
    mitsubishi_control_write 0xE1,1
    mitsubishi_control_write 0xE1,0
    mitsubishi_control_write 0xE1,1
    test cl,cl
    jz %%disk_controls
    smsw ax                    ; OEM reads only CR0.ET; retain the other EAX bits.
    test al,0x10
    mov ah,0
    jnz %%fpu_control
    inc ah
%%fpu_control:
    mitsubishi_control_write 0x90,ah
%%disk_controls:
    mov ah,0x80               ; OEM invalid-config speed default; cache bit1 stays clear.
    in al,0x5F
    test al,0x10
    jz %%ide_switch
    or ah,8
%%ide_switch:
    test al,0x40
    jz %%disk_ready
    or ah,4
%%disk_ready:
    mitsubishi_control_write 0xE2,ah
    in al,0x5F
    mov ah,al
    shr ah,2
    and ah,3
    and al,3
    dec al
    jnz %%parallel_two
    or ah,8
    jmp %%ports_ready
%%parallel_two:
    dec al
    jnz %%parallel_three
    or ah,4
    jmp %%ports_ready
%%parallel_three:
    dec al
    jnz %%ports_ready
    or ah,0x0C
%%ports_ready:
    mitsubishi_control_write 0xEC,ah
    shr ecx,16
    mov ax,cx
%endmacro
