; Native request/release shared by the RTC trial (2) and ordinary APM idle (3).
%define CLOCK_DATA (0x8000+board_clock_saved-board_smm_image)
%macro clock_save 2
    smm_read SMM_SB,%1
    mov [cs:CLOCK_DATA+%2],al
%endmacro
%macro clock_restore 2
    smm_write SMM_SB,%1,[cs:CLOCK_DATA+%2]
%endmacro

board_clock_smm_entry:
    cmp word [cs:0xFFD4],3
    jne .cache_ready
    ; A8000 is in the uncached VGA aperture; drain ordinary RAM only inside SMM.
    mov esi,cr0
    wbinvd
    mov eax,esi
    or eax,0x60000000
    mov cr0,eax
    smm_read SMM_HB,0x50
    mov [cs:CLOCK_DATA+7],al
    and al,0x7F
    out dx,al
.cache_ready:
    smm_read SMM_SB,0x76
    test al,0x30
    jnz .unavailable
    cmp word [cs:0xFFD4],3
    je .idle_ready
    mov al,0x8B
    out 0x70,al
    in al,0x84
    in al,0x71
    and al,0xF0
    cmp al,0x20
    jne .busy
    mov al,0x0A
    out 0xA0,al
    in al,0xA0
    mov bl,al
    mov al,0x0B
    out 0xA0,al
    in al,0xA0
    or bl,al
    mov al,0x0A
    out 0xA0,al
    test bl,1
    jnz .busy
.idle_ready:
    clock_save 0xA0,0
    clock_save 0xA4,1
    clock_save 0x56,2
    clock_save 0x80,3
    clock_save 0x91,4
    in al,0x61
    mov [cs:CLOCK_DATA+6],al
    cmp word [cs:0xFFD4],3
    jne .rtc_wake
    clock_save 0x90,5
    in al,0x21
    not al
    mov bl,al
    smm_write SMM_SB,0x90,bl
    in al,0xA1
    not al
    mov bl,al
    smm_write SMM_SB,0x91,bl
    ; Native doze's clock pair; its separate standby-timer owner is not used.
    jmp .wake_ready
.rtc_wake:
    smm_read SMM_SB,0x91
    or al,1
    out dx,al
.wake_ready:
    in al,0x61
    and al,0xFC
    out 0x61,al
    smm_read SMM_SB,0x80
    and al,0x3F
    cmp word [cs:0xFFD4],3
    jne .suspend_mode
    or al,0x40
    jmp .mode_ready
.suspend_mode:
    or al,0xC0
.mode_ready:
    out dx,al
    smm_read SMM_SB,0xA0
    and al,0xFC
    cmp word [cs:0xFFD4],3
    jne .suspend_control
    or al,1
    jmp .control_ready
.suspend_control:
    or al,2
.control_ready:
    out dx,al
    smm_read SMM_SB,0x56
    and al,0xFC
    or al,3
    out dx,al
    ; Native owner 44A3..44AE uses 4579,458B,4593,45B1 in that order.
    smm_read SMM_SB,0xA4
    ; The low two bits belong to the selected PCI divider, not the sleep state.
    and al,0x73
    or al,4
    out dx,al
    smm_read SMM_SB,0xA4
    and al,0xEF
    out dx,al
    smm_read SMM_SB,0xA4
    or al,0x10
    out dx,al
.window:
    times 18 nop
.window_end:
    smm_read SMM_SB,0xA2
    xor edi,edi
    cmp word [cs:0xFFD4],3
    je .idle_irq
    mov al,0x0A
    out 0xA0,al
    in al,0xA0
    and al,1
    xor al,1
    movzx edi,al
    imul di,di,6              ; 0=IRQ8 pending, 6=continued before the alarm.
    jmp .release
.idle_irq:
    ; A doze wake need not be deliverable (for example a masked PIT edge).
    ; Read IRR without acknowledging it; cascade alone is not a slave IRQ.
    mov al,0x0A
    out 0x20,al
    out 0xA0,al
    in al,0x21
    not al
    mov bl,al
    in al,0x20
    and al,bl
    mov ah,al
    and al,0xFB
    jnz .release
    test ah,4
    jz .retry
    in al,0xA1
    not al
    mov bl,al
    in al,0xA0
    and al,bl
    jnz .release
.retry:
    ; Reuse the native source acknowledgement, then reissue the complete state.
    smm_write SMM_SB,0xA2,0
    smm_read SMM_SB,0xA3
    or al,0x20
    out dx,al
    and al,0x9F
    out dx,al
    jmp .wake_ready
 .release:
    smm_read SMM_SB,0x80
    and al,0x3F
    out dx,al
    smm_read SMM_SB,0xA0
    and al,0xFC
    out dx,al
    smm_read SMM_SB,0xA3
    or al,0x20
    out dx,al
    and al,0xDF
    out dx,al
    clock_restore 0x56,2
    mov bl,[cs:CLOCK_DATA+1]
    cmp word [cs:0xFFD4],3
    jne .restore_latch
    ; Native459F/45B1 selects full-on, retaining the PCI divider, then latches.
    ; Retain native command bits instead of replaying the dormant raw selector.
    and bl,0x63
    or bl,0x80
.restore_latch:
    and bl,0xEF
    smm_write SMM_SB,0xA4,bl
    or bl,0x10
    smm_write SMM_SB,0xA4,bl
    cmp word [cs:0xFFD4],3
    je .full_on
    ; The controlled suspend comparison retains its prior exact-byte contract.
    clock_restore 0xA4,1
.full_on:
    cmp word [cs:0xFFD4],3
    jne .restore_suspend
    clock_restore 0x90,5
    jmp .restored_wake
.restore_suspend:
    clock_restore 0x80,3
.restored_wake:
    clock_restore 0x91,4
    mov al,[cs:CLOCK_DATA+6]
    out 0x61,al
    cmp word [cs:0xFFD4],3
    je .run_ready
    clock_restore 0xA0,0
.run_ready:
    mov eax,edi
    jmp .reply
.busy:
    mov eax,2
    jmp .reply
.unavailable:
    mov eax,1
.reply:
    mov edi,eax
    cmp word [cs:0xFFD4],3
    jne .cache_restored
    smm_write SMM_HB,0x50,[cs:CLOCK_DATA+7]
    invd
    mov cr0,esi
.cache_restored:
    mov eax,edi
    mov [cs:0xFFD0],eax
    or dword [cs:0xFFF4],1
    test eax,eax
    jnz .flags
    and dword [cs:0xFFF4],0xFFFFFFFE
.flags:
    mov eax,[cs:0xFEFC]
    mov [cs:0xFFD4],eax
    mov dword [cs:0xFFDC],SMM_REPLY
    mov eax,ebp
    mov dx,0xCF8
    out dx,eax
    rsm
board_clock_saved:
    times 8 db 0
