%ifndef PC_PROCESSOR_PRIMITIVES
%include "pc/processor.inc"
%endif
%ifndef RAM_TEST_SERVICE_MASK
%define RAM_TEST_SERVICE_MASK 0x3FFF
%endif
%if RAM_TEST_BLOCK_SIZE < 4 || (RAM_TEST_BLOCK_SIZE & (RAM_TEST_BLOCK_SIZE-1))
    %error RAM burst size must be a power of two of at least four bytes
%endif
%if RAM_TEST_SERVICE_MASK < 3 || RAM_TEST_SERVICE_MASK > 0xFFFF || (RAM_TEST_SERVICE_MASK & (RAM_TEST_SERVICE_MASK+1)) || ((RAM_TEST_SERVICE_MASK+1) % RAM_TEST_BLOCK_SIZE)
    %error RAM service quantum must be a power of two and contain whole blocks
%endif
%ifdef RAM_TEST_BUFFER_ABSOLUTE
%if (RAM_TEST_BUFFER_ABSOLUTE & 3) || RAM_TEST_BUFFER_ABSOLUTE < 0x500 || RAM_TEST_BUFFER_ABSOLUTE < RAM_TEST_SCRATCH_BEGIN || RAM_TEST_BUFFER_ABSOLUTE+RAM_TEST_BLOCK_SIZE > RAM_TEST_SCRATCH_END || RAM_TEST_SCRATCH_END > 0x10000 || RAM_TEST_SCRATCH_END >= RAM_TEST_STACK_TOP
    %error RAM burst backup exceeds the reserved POST scratch
%endif
%if RAM_TEST_BUFFER_ABSOLUTE < (STATE_SEG*16+CFG_PLATFORM_STATE_KIB*1024) && RAM_TEST_BUFFER_ABSOLUTE+RAM_TEST_BLOCK_SIZE > STATE_SEG*16
    %error RAM burst backup overlaps live firmware state
%endif
%else
%if S_RAM_TEST_BUFFER + RAM_TEST_BLOCK_SIZE > CFG_PLATFORM_STATE_KIB * 1024
    %error RAM burst backup exceeds the reserved firmware state
%endif
%endif

%macro ram_block_pattern 1
    mov si,sp
    mov ecx,[ss:si]
    mov edi,[ss:si+4]
    mov eax,%1
    a32 rep stosd
%if %1 == 0x55AA55AA
%ifdef EMULATOR_CHIPSET_RAM_ERROR
    mov si,sp
    cmp dword [ss:si+4],0x10000
    jne %%not_injected
    not dword [es:dword 0x10000]
%%not_injected:
%endif
%ifdef EMULATOR_RAM_PROOF_RECOVERY
    mov si,sp
    cmp dword [ss:si+4],0x10000
    jne %%recovery_not_injected
%ifndef EMULATOR_RAM_PROOF_PERSISTENT
    mov al,0xB7
    out 0x70,al
    in al,0x71
    cmp al,1
    jne %%recovery_not_injected
%endif
    not dword [es:dword 0x10000]
%%recovery_not_injected:
    mov eax,%1
%endif
%endif
    mov si,sp
    mov ecx,[ss:si]
    mov edi,[ss:si+4]
    a32 repe scasd
    jne .bad_block
%endmacro

chipset_visible_ram_test:
    pushf
    cli
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    cmp byte [fs:P_PHASE], 0
    je .legacy_progress
    call post_ram_start
    jmp .prepare
.legacy_progress:
    mov si, chipset_ram_progress
    call print_string
.prepare:
%ifmacro BOARD_RAM_TEST_PREPARE 0
    BOARD_RAM_TEST_PREPARE
%endif
    sub sp, 6
    mov di, sp
    sgdt [ss:di]
    in al, 0x61
    push ax
    or al, 0x0C
    out 0x61, al
    board_a20_read
    push ax
    and al, 0xFE
    or al, 2
    board_a20_write
    mov ebp, cr0
    cpu_cache_flush
    mov eax, ebp
    cpu_cache_disable
    mov cr0, eax
    memory_extended_kib ebx
    add ebx, 1024
    shl ebx, 10
%ifdef BOARD_FAST_BOOT_SETTING
    cmp byte [fs:BOARD_FAST_BOOT_SETTING], 1
    jne .test_limit_ready
    mov ebx, 0x100000
.test_limit_ready:
%endif
    xor edx, edx
    mov dx, fs
    shl edx, 4
    lgdt [cs:move_gdtr]
    mov eax, cr0
    or al, 1
    mov cr0, eax
    jmp 0x08:.protected
.protected:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov edi, 0x10000
.point:
    mov ecx,RAM_TEST_BLOCK_SIZE
    mov esi,ebx
    cmp edi,0x100000
    jae .block_limit
    mov esi,edx
.block_limit:
    sub esi,edi
    cmp ecx,esi
    jbe .block_size
    mov ecx,esi
.block_size:
    shr ecx,2
    push edi
    push ecx
    mov esi,edi
%ifdef RAM_TEST_BUFFER_ABSOLUTE
    mov edi,RAM_TEST_BUFFER_ABSOLUTE
%else
    lea edi,[edx+S_RAM_TEST_BUFFER]
%endif
    a32 rep movsd
    ram_block_pattern 0x55AA55AA
    ram_block_pattern 0xAA55AA55
    ram_block_pattern 0
    ; Constant passes need independent low-address-line witnesses.
    mov si,sp
    mov ecx,[ss:si]
    shl ecx,2
    mov esi,[ss:si+4]
    mov dword [esi],0x1265ABCD
    mov edi,4
.address_write:
    cmp edi,ecx
    jae .address_base
    mov eax,edi
    xor eax,0xED9A5432
    mov [esi+edi],eax
    shl edi,1
    jmp .address_write
.address_base:
    cmp dword [esi],0x1265ABCD
    jne .bad_block
    mov edi,4
.address_read:
    cmp edi,ecx
    jae .good_block
    mov eax,edi
    xor eax,0xED9A5432
    cmp [esi+edi],eax
    jne .bad_block
    shl edi,1
    jmp .address_read
.good_block:
    xor eax,eax
    jmp .restore_block
.bad_block:
    mov eax,1
.restore_block:
    mov si,sp
    mov ecx,[ss:si]
    mov edi,[ss:si+4]
%ifdef RAM_TEST_BUFFER_ABSOLUTE
    mov esi,RAM_TEST_BUFFER_ABSOLUTE
%else
    lea esi,[edx+S_RAM_TEST_BUFFER]
%endif
    a32 rep movsd
    add sp,8
    test eax,eax
    jnz .bad
    cmp edi, edx              ; Skip the live EBDA and ROM/MMIO window.
    jne .limit
    mov edi, 0x100000
.limit:
    test edi, 0xFFFF
    jnz .yield_check
    call .progress
    jmp .continue
.yield_check:
    test edi, RAM_TEST_SERVICE_MASK ; Board-selected keyboard service cadence.
    jnz .continue
    call .yield
.continue:
    cmp edi, ebx
    jb .point
    call .progress
    xor edi, edi
    jmp .leave
.bad:
    mov edi, 1
.leave:
    cpu_cache_flush
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov eax, ebp
    and al, ~1
    mov cr0, eax
    jmp 0xF000:.real
.progress:
    pushad
    mov eax, edi
    shr eax, 10
    cmp byte [edx+P_PHASE], 0
    je .legacy_row
    mov edi, 0xB8000 + BOARD_POST_RAM_ROW*160 + 24*2
    push eax
    mov cx, MEMORY_COUNT_DIGITS
    mov ax, 0x0720
.clear_count:
    mov [edi], ax
    add edi, 2
    loop .clear_count
    pop eax
    mov edi, 0xB8000 + BOARD_POST_RAM_ROW*160 + 24*2
    xor cx, cx
    mov ebx, 10
.count_digit:
    xor edx, edx
    div ebx
    push dx
    inc cx
    test eax, eax
    jnz .count_digit
.count_write:
    pop ax
    add al, '0'
    mov ah, 7
    mov [edi], ax
    add edi, 2
    loop .count_write
    jmp .count_done
.legacy_row:
    ; Standalone diagnostic entry retains its original progress oracle.
    movzx edi, byte [0x0451]
    dec edi
    imul edi, 160
    add edi, 0xB8000 + (10+MEMORY_COUNT_DIGITS)*2
    mov ebx, 10
    mov cx, MEMORY_COUNT_DIGITS
.digit:
    xor edx, edx
    div ebx
    add dl, '0'
    mov dh, 7
    mov [edi], dx
    sub edi, 2
    loop .digit
.count_done:
%ifdef EMULATOR_CHIPSET_POST_RAM
    mov bp, sp
    cmp dword [ss:bp], 0x100000 ; PUSHAD's saved EDI: real mid-test count.
    jne .captured
    ; Let retained VGA finish two frames before the external screenshot.
    mov dx, 0x03DA
    mov cx, 2
.retrace_low:
    in al, dx
    test al, 8
    jnz .retrace_low
.retrace_high:
    in al, dx
    test al, 8
    jz .retrace_high
    loop .retrace_low
    call setup_test_snapshot
.captured:
%endif
    jmp .service
.yield:
    pushad
.service:
    ; Service the existing IRQ/scan owner only with the real-mode IVT active.
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov eax, cr0
    and al, ~1
    mov cr0, eax
    jmp 0xF000:.keyboard
.keyboard:
    push ds
    push es
    push fs
    xor ax, ax
    mov ds, ax
    mov es, ax
    sti
    nop
    call post_keyboard_wait
    cli
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .abort
    test byte [fs:P_RAM_FLAGS], 2
    jnz .abort
    pop fs
    pop es
    pop ds
    lgdt [cs:move_gdtr]
    mov eax, cr0
    or al, 1
    mov cr0, eax
    jmp 0x08:.resume_test
.resume_test:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    popad
    ret
.abort:
    ; The current block was restored before yielding. Remove only the
    ; service frame and its near return, then use the normal real exit.
    pop fs
    pop es
    pop ds
    popad
    pop ax
    mov eax, ebp
    and al, ~1
    mov cr0, eax
    xor edi, edi
    jmp .real
.real:
    xor ax, ax
    mov ds, ax
    mov es, ax
    pop ax
    and al, 0xFE
    board_a20_write
    pop ax
    out 0x61, al
    mov si, sp
    o32 lgdt [ss:si]
    add sp, 6
    test edi, edi
    jnz .retry
    cmp byte [fs:P_PHASE], 0
    je .legacy_pass
    call post_ram_finish
    jmp .done
.legacy_pass:
    mov si, chipset_ram_pass
    call print_string
    jmp .done
.retry:
%ifdef BOARD_RAM_FAILURE_RESTORE
    BOARD_RAM_FAILURE_RESTORE
%endif
    mov al, 0x36
    call rtc_read
    and al, 0xBF
    cmp al, 0x1A
    je .failed
    call settings_recovery_publish
    mov ax, 0x5A36
    call rtc_write
    cmp byte [fs:P_PHASE], 0
    je .ram_retry_text
    call post_message_cursor
.ram_retry_text:
    mov si, chipset_ram_retry
    call print_string
    call chipset_recovery_ack
%ifdef EMULATOR_CHIPSET_RAM_ERROR
    call chipset_test_recovery_capture
%endif
%ifdef EMULATOR_RAM_PROOF_RECOVERY
    call core_ram_recovery_check
%endif
    jmp controlled_defaults_restart
.failed:
    cmp byte [fs:P_PHASE], 0
    je .ram_failure_text
    call post_message_cursor
.ram_failure_text:
    mov si, chipset_ram_failure
    call print_string
    post_code_early 0xE7
%ifdef EMULATOR_RAM_PROOF_RECOVERY
    call core_ram_recovery_failed
%endif
    jmp hard_halt
.done:
    pop fs
    pop es
    pop ds
    popad
    popf
    ret

chipset_post_recovery_notice:
    pushad
    mov al, 0x36
    call rtc_read
    cmp al, 0x5A
    je .report
    cmp al, 0xDA
    jne .done
.report:
    call post_message_cursor
    mov si, chipset_early_retry
    call print_string
    call chipset_recovery_ack
.done:
    popad
    ret

; Clear the notice only after printing, preserving a current-POST retry guard.
chipset_recovery_ack:
    mov ax, 0x1A36
    call rtc_write
    ret

; The visible pass checks free conventional/extended RAM in place.
; The stackless early pass owns low firmware RAM and EBDA.
chipset_runtime_ram_check:
    ; The lowest test point needs free DRAM through 110003h for eviction.
%ifdef BOARD_WIDE_MEMORY_COUNTS
    cmp dword [fs:S_EXTENDED_KIB32],64
%else
    cmp word [fs:S_EXTENDED_KIB],64
%endif
    ja .scratch_available
    clc
    ret
.scratch_available:
    pushad
    in al, 0x61
    push ax
    or al, 0x0C               ; No parity/channel NMI through the real-mode IVT in PE.
    out 0x61, al
    push ds
    push es
    sub sp, 6
    mov di, sp
    sgdt [ss:di]
    board_a20_read
    push ax
    and al, 0xFE
    or al, 2
    board_a20_write
    mov ebp, cr0
    cpu_cache_flush
    mov eax, ebp
    cpu_cache_disable
    mov cr0, eax
    memory_extended_kib ebx
    add ebx, 1024
    shl ebx, 10
    sub ebx, 0x100004
    lgdt [cs:move_gdtr]
    mov eax, cr0
    or al, 1
    mov cr0, eax
    jmp 0x08:.protected
.protected:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov edi, 0x10000
.point:
    mov esi, [edi]
    lea edx, [edi+0x100000]
    mov ecx, 0x55AA55AA
.pattern:
    mov [edi], ecx
    mov eax, [edx]
    mov eax, [edi]
    cmp eax, ecx
    jne .bad
    not ecx
    cmp ecx, 0x55AA55AA
    jne .pattern
    mov [edi], esi
    mov eax, [edx]
    cmp edi, 0x10000
    jne .next
    mov edi, 0x100000
    jmp .limit
.next:
    add edi, 0x100000
.limit:
    cmp edi, ebx
    jb .point
    xor edi, edi
    jmp .leave
.bad:
    mov [edi], esi
    mov eax, [edx]
    mov edi, 1
.leave:
    cpu_cache_flush
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov eax, ebp
    and al, ~1
    mov cr0, eax
    jmp 0xF000:.real
.real:
    pop ax
    and al, 0xFE
    board_a20_write
    mov si, sp
    o32 lgdt [ss:si]
    add sp, 6
    test edi, edi
    pop es
    pop ds
    pop ax
    out 0x61, al              ; Real-mode segments and caller GDTR are restored.
    popad
    jnz .failure
    clc
    ret
.failure:
    stc
    ret

chipset_nmi:
    push ax
    in al, 0x61
    test al, 0x80
    jz .done
    cli
%ifdef BOARD_LATE_POST_TRACE
    post_code_early 0xE8 ; PB430 must expose parity before a potentially stalled print.
%endif
    push cs
    pop ds
    mov si, chipset_parity_error
    call print_string
    post_code_early 0xE8
    jmp hard_halt
.done:
    pop ax
    iret


chipset_parity_error db 13,10,'RAM parity error. Restart with chipset defaults.',13,10,0
chipset_ram_pass db ' POST RAM test passed',13,10,0
%ifdef BOARD_WIDE_MEMORY_COUNTS
chipset_ram_progress db ' RAM test: 000000 KB',13,10,0
%else
chipset_ram_progress db ' RAM test: 00000 KB',13,10,0
%endif
chipset_ram_retry db ' RAM test failed; retrying defaults',13,10,0
chipset_ram_failure db ' RAM test failed at defaults',13,10,0
chipset_early_retry db ' POST RAM test failed; chipset defaults restored',13,10,0
chipset_cache_retry db 13,10,' RAM test after L2 setup failed; retrying defaults',13,10,0
chipset_cache_failure db 13,10,' RAM test after L2 setup failed at defaults',13,10,0
