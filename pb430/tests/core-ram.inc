core_ram_test_begin:
%ifdef EMULATOR_RAM_PROOF
    pushad
    push es
    mov eax,cr0
    mov [0xB80],eax
    sgdt [0xB84]
    in al,0x61
    and al,0x0C
    mov [0xB8A],al
    in al,0x92
    and al,0xFE
    mov [0xB8B],al
%ifdef EMULATOR_RAM_PROOF_DELETE
    cmp byte [fs:C_CHIP],1
    je .seeded
%endif
    mov ax,0x1200
    mov es,ax
    xor di,di
    mov cx,512
.pattern:
    movzx eax,di
    xor eax,0xAC216811
    stosd
    loop .pattern
    mov byte [0xB8C],0
.seeded:
    pop es
    popad
%endif
%ifdef EMULATOR_RAM_PROOF_RECOVERY
    jmp core_ram_recovery_begin
%endif
%ifdef EMULATOR_RAM_PROOF_DELETE
    cmp byte [fs:C_CHIP],1 ; Full saved-field checks run after peripheral init.
    je .saved
%endif
    mov byte [0xB34],0
%ifdef EMULATOR_RAM_PROOF
    mov word [0xB35],0
    mov byte [0xB3F],0
%endif
    push es
    xor ax,ax
    mov es,ax
    set_vector 0x1C,core_ram_test_tick
    pop es
%ifdef EMULATOR_RAM_PROOF_DELETE
.saved:
%endif
    ret
core_ram_test_tick:
    pushad
    push ds
    push es
    push fs
    xor ax,ax
    mov ds,ax
    mov fs,[0x40E]
%ifdef EMULATOR_RAM_PROOF
    inc byte [0xB3F]
    cmp byte [0xB3F],180
    jae .fail
%ifdef EMULATOR_RAM_PROOF_PAUSE
    cmp byte [0xB35],0
    jne .pause_events
%endif
%endif
    cmp byte [fs:P_RAM_FLAGS],1
    jne .done
    mov ax,0xB800
    mov es,ax
    cmp byte [fs:C_CHIP+6],1
    jne .full_progress
    cmp word [es:5*160+26*2],0x0720
    je .done                    ; Fast Boot stops before a four-digit count.
    jmp .progress_seen
.full_progress:
    cmp word [es:5*160+27*2],0x0720
    je .done                    ; Require an actual four-digit progress count.
.progress_seen:
    cmp byte [es:5*160+24*2],'1'
    jb .done
    cmp byte [es:5*160+24*2],'9'
    ja .done
    in al,0x64
    test al,3
    jnz .done
%ifdef EMULATOR_RAM_PROOF
%ifdef EMULATOR_RAM_PROOF_PAUSE
    inc byte [0xB35]
    mov al,0xE1
    jmp .send
.pause_events:
    mov ax,0xB800
    mov es,ax
    cmp byte [0xB35],1
    jne .paused_checked
    mov eax,[es:5*160+24*2]
    mov [0xB36],eax
    mov eax,[es:5*160+26*2]
    mov [0xB3A],eax
.paused_checked:
    cmp byte [0xB35],16
    je .resumed
    cmp byte [0x400+KB_PAUSED],1
    jne .fail
    cmp byte [0x400+KB_PAUSE_OWNER],1
    jne .fail
    cmp byte [0x400+KB_POST_STATE],3
    jne .fail
    mov eax,[es:5*160+24*2]
    cmp eax,[0xB36]
    jne .fail
    mov eax,[es:5*160+26*2]
    cmp eax,[0xB3A]
    jne .fail
    movzx bx,byte [0xB35]
    inc byte [0xB35]
    cmp bx,15
    je .fresh_make
    cmp bx,10
    jae .done                 ; Timer-only contrast also retains Pause.
    mov al,[cs:.pause_scans+bx-1]
    jmp .send
.fresh_make:
    cmp byte [0x400+KB_E1_REMAIN],0
    jne .fail
    mov al,0x1E
    jmp .send
.resumed:
    cmp byte [0x400+KB_PAUSED],0
    jne .fail
    cmp byte [0x400+KB_PAUSE_OWNER],0
    jne .fail
    cmp byte [0x400+KB_POST_STATE],1
    jne .fail
    mov ax,[0x41A]
    cmp ax,[0x41C]
    jne .fail                 ; Resume make was consumed, never queued.
    jmp .finished
.pause_scans db 0x1D,0x45,0xE1,0x9D,0xC5,0xFA,0xFE,0x9E,0xE0
%elifdef EMULATOR_RAM_PROOF_DELETE
    cmp byte [0xB35],0
    jne .delete_make
    inc byte [0xB35]
    mov al,0xE0
    jmp .send
.delete_make:
    mov al,0x53
    call .send_byte
    jc .fail
    mov byte [0xB34],1
    call setup_test_begin
    mov byte [0x0600],2        ; Setup fixture ST_PHASE: Delete supplied the request.
    jmp .done
%else
    cmp byte [0xB35],0
    jne .ordinary_seen
    inc byte [0xB35]
    mov al,0x1E
    jmp .send
.ordinary_seen:
    cmp word [0x41E],0x1E61
    jne .fail
    cmp byte [fs:P_RAM_FLAGS],1
    jne .fail
    mov al,1
    call .send_byte
    jc .fail
    jmp .finished
%endif
.send:
    call .send_byte
    jc .fail
    jmp .done
.send_byte:
    push ax
    mov al,0xD2
    call kbc_command
    pop ax
    jc .send_done
    call kbc_write_data
.send_done:
    ret
.finished:
    mov byte [0xB34],1
    xor ax,ax
    mov es,ax
    set_vector 0x1C,default_iret
    jmp .done
.fail:
    mov al,0x79
    call emulator_exit
    jmp hard_halt
%else
    mov al,0xD2
    call kbc_command
    jc .done
    mov al,1                    ; Physical Esc scan through IRQ1.
    call kbc_write_data
    jc .done
    mov byte [0xB34],1
    xor ax,ax
    mov es,ax
    set_vector 0x1C,default_iret
%endif
.done:
    pop fs
    pop es
    pop ds
    popad
    iret

%ifdef EMULATOR_RAM_PROOF_RECOVERY
; CMOS37 survives the real8042 reset; the original2KiB pattern proves restoration.
core_ram_recovery_begin:
    pushf
    cli
    pushad
    push es
    mov al,0x37
    call rtc_read
    inc al
    cmp al,2
    ja core_ram_recovery_bad
    mov bl,al
    mov ah,al
    mov al,0x37
    call rtc_write
    cmp bl,1
    jne .defaults
    cmp byte [fs:C_CHIP+1],1
    jne core_ram_recovery_bad
    jmp .seed
.defaults:
    cmp byte [fs:C_CHIP+1],0
    jne core_ram_recovery_bad
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    jne core_ram_recovery_bad
    mov al,0x36
    call rtc_read
    cmp al,0x1A
    jne core_ram_recovery_bad
.seed:
    mov eax,cr0
    mov [0xB40],eax
    sgdt [0xB44]
    in al,0x61
    and al,0x0F             ; Refresh/output status bits are live, not gates.
    mov [0xB4A],al
    in al,0x92
    and al,0xFE
    mov [0xB4B],al
    mov ax,0x1000
    mov es,ax
    xor di,di
    mov cx,RAM_TEST_BLOCK_SIZE/4
.dword:
    movzx eax,di
    xor eax,0x1265ABCD
    stosd
    loop .dword
    pop es
    popad
    popf
    ret

core_ram_recovery_check:
    pushad
    push es
    mov eax,cr0
    cmp eax,[0xB40]
    jne core_ram_recovery_bad
    sgdt [0xB50]
    mov eax,[0xB50]
    cmp eax,[0xB44]
    jne core_ram_recovery_bad
    mov ax,[0xB54]
    cmp ax,[0xB48]
    jne core_ram_recovery_bad
    in al,0x61
    and al,0x0F
    cmp al,[0xB4A]
    jne core_ram_recovery_bad
    in al,0x92
    and al,0xFE
    cmp al,[0xB4B]
    jne core_ram_recovery_bad
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    jne core_ram_recovery_bad
    mov al,0x36
    call rtc_read
    cmp al,0x1A
    jne core_ram_recovery_bad
    mov ax,0x1000
    mov es,ax
    xor di,di
    mov cx,RAM_TEST_BLOCK_SIZE/4
.dword:
    movzx eax,di
    xor eax,0x1265ABCD
    scasd
    jne core_ram_recovery_bad
    loop .dword
    pop es
    popad
    ret

core_ram_recovery_failed:
    call core_ram_recovery_check
    mov al,0x37
    call rtc_read
    cmp al,2
    jne core_ram_recovery_bad
    cmp byte [fs:C_CHIP+1],0
    jne core_ram_recovery_bad
    mov al,0x6A               ; Actual E7 branch; no second reset.
    call emulator_exit
    jmp hard_halt
core_ram_recovery_bad:
    mov al,0x7B
    call emulator_exit
    jmp hard_halt
%endif

%ifdef EMULATOR_RAM_PROOF
; Independent terminal oracle for the actual composed RAM/input path.
core_ram_restore_check:
    pushad
    push ds
    push es
    xor ax,ax
    mov ds,ax
    mov eax,cr0
    and eax,0xFFFFFFD1 ; The later shared FPU owner clears MP/EM/TS/NE.
    mov edx,[0xB80]
    and edx,0xFFFFFFD1
    cmp byte [fs:P_PHASE],5
    jb .cache_expected
    cmp byte [fs:C_CHIP+1],0
    je .cache_expected
    and edx,0x9FFFFFFF ; Late POST enables the selected L1 after the RAM test.
.cache_expected:
    cmp eax,edx
    jne .bad
    sgdt [0xB90]
    mov eax,[0xB90]
    cmp eax,[0xB84]
    jne .bad
    mov ax,[0xB94]
    cmp ax,[0xB88]
    jne .bad
    in al,0x61
    and al,0x0C
    cmp al,[0xB8A]
    jne .bad
    in al,0x92
    and al,0xFE
    cmp al,[0xB8B]
    jne .bad
    mov ax,0x1200
    mov es,ax
    xor di,di
    mov cx,512
.dword:
    movzx eax,di
    xor eax,0xAC216811
    scasd
    jne .bad
    loop .dword
%ifdef EMULATOR_RAM_PROOF_DELETE
    cmp byte [0xB8C],1
    jne .bad
%endif
    pop es
    pop ds
    popad
    clc
    retf
.bad:
    pop es
    pop ds
    popad
    stc
    retf
%endif
