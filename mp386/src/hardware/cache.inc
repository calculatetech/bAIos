; OEM6398..674D /2454..24A4 qualification and92EB..93BE normal cache policy.
; Status bits:1 held off,2 requested by switch,4 qualified,8 active,16 failed.
cache_initialize:
    pushf
    pushad
    mov byte [fs:HW_CACHE_STATUS],1
    mov byte [fs:HW_BOARD_KIND],0
    in al,0x5E
    test al,1
    jz .kind_two
    mov byte [fs:HW_BOARD_KIND],1
    jmp .kind_ready
.kind_two:
    test al,4
    jz .kind_ready
    mov byte [fs:HW_BOARD_KIND],2
.kind_ready:
    in al,0x5F
    test al,0x80
    jnz .done
    or byte [fs:HW_CACHE_STATUS],2
.done:
    popad
    popf
    ret

cache_test:
mp_cache_qualify:
    pushf
    pushad
    push ds
    push es
    cli
    cld
    mov al,0x8D
    out 0x70,al
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    call cache_initialize
    test byte [fs:HW_CACHE_STATUS],2
    jz mp_cache_return
    mov cx,[fs:HW_MCU_COUNT]
    cmp cx,1
    jb mp_cache_register_failed
    cmp cx,3
    ja mp_cache_register_failed
    xor si,si
.maps:
    mov dx,si
    or dl,2
    mp_mcu_read
    cmp ax,0x8100
    jne mp_cache_register_failed
    mov dx,si
    shl dx,4
    or dx,0x800C
    mov bx,0x800C
.page:
    mp_mcu_read
    test si,si
    jnz .other_unit
    cmp ax,bx
    jne mp_cache_register_failed
    jmp .next_page
.other_unit:
    test ax,0x8000
    jnz mp_cache_register_failed
.next_page:
    inc dx
    inc bx
    cmp bl,0x10
    jb .page
    add si,0x100
    loop .maps
    push cs
    pop ds
    xor si,si
    post_code 0x26
    jmp oem_cache_63AB

mp_cache_pass:
    or byte [fs:HW_CACHE_STATUS],4
    post_code 0x27
mp_cache_return:
    pop ax
    out 0x61,al
    mov al,0x0D                ; The shared POST caller entered with NMI enabled.
    out 0x70,al
    pop es
    pop ds
    popad
    popf
    ret

mp_cache_register_failed:
    ; The reference stops when the control latches cannot be verified.
    jmp hard_halt
mp_cache_data_failed:
    ; Native cleanup is complete; discard its CALL before restoring our frame.
    pop ax
    or byte [fs:HW_CACHE_STATUS],16
    post_code 0xE3
    jmp mp_cache_return
mp_cache_title:
    ret

mp_cache_record_read:
    cmp dx,0x02DD
    je .count
    cmp dx,0x02CF
    je .kind
    jmp hard_halt
.count:
    mov al,[fs:HW_MCU_COUNT]
    jmp bp
.kind:
    mov al,[fs:HW_BOARD_KIND]
    jmp bp
mp_cache_record_write:
    mov al,ah                  ; OEM02FF bookkeeping has no bAIos consumer.
    jmp bp

mp_memory_finish:
    call mp_shadow_activate
    jmp mp_cache_enable
mp_cache_enable:
    pushf
    pushad
    push ds
    cli
    test byte [fs:HW_CACHE_STATUS],4
    jz .done
    call cache_memory_policy
    mov si,1
    call oem_cache_92EB
    mov [fs:HW_CACHE_POLICY],bh
    test bh,bh
    jz .nmi_ready
    and byte [fs:HW_CACHE_STATUS],0xFE
    or byte [fs:HW_CACHE_STATUS],8
.nmi_ready:
    mov al,0x0D
    out 0x70,al
.done:
    pop ds
    popad
    popf
    ret

; The reset caller passes SI=0 to choose the complete reference Off branch.
; Late SI=1 commits the tested bAIos memory policy when the switch is on.
%include "hardware/cache-native.inc"
