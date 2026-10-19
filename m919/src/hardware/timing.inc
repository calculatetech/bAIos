; Profile semantics follow the donor; tuples and register masks are UMC-owned.
chipset_profile_index:
    movzx bx,byte [fs:si+7]
    shl bx,1
    mov al,[fs:si+8]
    and al,0x30
    cmp al,0x10
    je .done
    inc bx
.done:
    ret
chipset_profile_tuple:
    call chipset_profile_index
    mov al,[fs:si+8]
    and al,0xC0
    cmp al,0x40
    jne .fast
    add bx,8
    jmp .offset
.fast:
    cmp al,0xC0
    jne .offset
    add bx,16
.offset:
    imul bx,bx,3
    ret
chipset_fast_available:
%if !CFG_PLATFORM_FAST_MEMORY_PROFILE_SUPPORTED
    ; Repeatable U20 failures prohibit offering the unqualified Fast preset.
    stc
    ret
%else
    push ax
    push bx
    call chipset_profile_index
    imul bx,bx,3
    cmp byte [cs:chipset_profiles+bx],0xF0
    jne .good
    test byte [fs:si+5],1
    jnz .good
    cmp byte [fs:si+2],0
    jne .bad
    cmp byte [fs:HW_CACHE_CODE],0
    je .bad
    call cache_record_supported_extent
    jc .bad
.good:
    pop bx
    pop ax
    clc
    ret
.bad:
    pop bx
    pop ax
    stc
    ret
%endif
chipset_profile_apply:
    push ax
    push bx
    mov al,[fs:si+8]
    and al,0xC0
    cmp al,0x80
    je .done
    cmp al,0xC0
    jne .apply
    call chipset_fast_available
    jnc .apply
    and byte [fs:si+8],0x3F
%if !CFG_PLATFORM_FAST_MEMORY_PROFILE_SUPPORTED
    ; A saved Fast record must also stop applying aggressive cache timings.
    or byte [fs:si+8],0x40
    mov byte [fs:si+2],1
    call cache_validation_clear
%endif
.apply:
    call chipset_profile_tuple
    mov al,[cs:chipset_profiles+bx]
    mov [fs:si],al
    and byte [fs:si+3],0xCF
    mov al,[cs:chipset_profiles+bx+1]
    or [fs:si+3],al
    and byte [fs:si+5],0xFD
    mov al,[cs:chipset_profiles+bx+2]
    or [fs:si+5],al
.done:
    pop bx
    pop ax
    ret
chipset_safe_defaults:
    call chipset_defaults
    mov byte [fs:di+1],0
    mov byte [fs:di+8],0x40
    mov byte [fs:di+2],1
    push si
    mov si,di
    call chipset_profile_apply
    pop si
    ret
chipset_apply_timing:
    cache_read 0x5D
    and al,0x6F
    or al,[fs:C_CHIP+4]
    mov cl,al
    cache_write 0x5D,cl
    cache_read 0x61
    and al,0x37
    test byte [fs:C_CHIP+5],1
    jz .edo_burst
    or al,0xC0
.edo_burst:
    test byte [fs:C_CHIP+5],2
    jz .dram
    or al,8
.dram:
    mov cl,al
    cache_write 0x61,cl
    cache_read 0x5A
    and al,0xEF
    cmp byte [fs:C_CHIP+6],0
    je .parity
    or al,0x10
.parity:
    mov cl,al
    cache_write 0x5A,cl
    ; The donor enables reporting only after RAM/shadow parity initialization.
    in al,0x61
    or al,4
    out 0x61,al
    cache_read 0x52
    and al,0x7F
    test byte [fs:C_CHIP+9],1
    jz .posted
    or al,0x80
.posted:
    mov cl,al
    cache_write 0x52,cl
    cache_read 0x53
    and al,0x3F
    test byte [fs:C_CHIP+9],2
    jz .copyback
    or al,0x80
.copyback:
    test byte [fs:C_CHIP+9],4
    jz .write
    or al,0x40
.write:
    mov cl,al
    cache_write 0x53,cl
    ret

%include "hardware/cache-validation.inc"
