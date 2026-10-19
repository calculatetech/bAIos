; PB43098BC..9D60: mode1 bank probe, sorted topology and inverse routing.
; No stack exists until topology, low RAM and alias-aware64-KiB sizing finish.
%macro acc_commit_early 1
    mov ah,al
    mov al,%1
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,ah
    out CHIPSET_DATA,al
    out 0xED,al
%endmacro
%macro memory_sort_pair 2
    mov ax,dx
    shr ax,4*(%1)
    and ax,15
    mov cx,dx
    shr cx,4*(%2)
    and cx,15
    cmp ax,cx
    jbe %%done
    and dx,~((15 << (4*(%1))) | (15 << (4*(%2))))
    shl ax,4*(%2)
    shl cx,4*(%1)
    or dx,ax
    or dx,cx
    mov al,bl
    shr al,2*(%1)
    and al,3
    mov cl,bl
    shr cl,2*(%2)
    and cl,3
    and bl,~((3 << (2*(%1))) | (3 << (2*(%2))))
    shl al,2*(%2)
    shl cl,2*(%1)
    or bl,al
    or bl,cl
%%done:
%endmacro
memory_initialize:
    xor al,al
    acc_commit_early 0x13
    mov al,0x12
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xF7
    acc_commit_early 0x12
    ; OEM9919..99C6 changes the intermediate map before enabling mode1.
    in al,0x92
    or al,2
    out 0x92,al
    ; The cold table selects mode1; retain the OEM dispatch's register05 read.
    mov al,5
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    mov al,0
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xF0
    or al,9
    acc_commit_early 0x0
    mov al,0x12
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xF0
    or al,0x0A
    acc_commit_early 0x12
    mov al,5
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    or al,0x10
    acc_commit_early 0x5
.mode1_ready:
    lgdt [cs:move_gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp 8:.protected
.protected:
    mov ax,16
    mov ds,ax
    mov es,ax
    xor dx,dx
    xor edi,edi
    post_code_early 0x27
    mov bx,.bank0
    jmp memory_probe_bank
.bank0:
    post_code_early 0x2B
    or dx,cx
    mov edi,0x1000000
    post_code_early 0x28
    mov bx,.bank1
    jmp memory_probe_bank
.bank1:
    post_code_early 0x2C
    shl cx,4
    or dx,cx
    mov edi,0x2000000
    post_code_early 0x29
    mov bx,.bank2
    jmp memory_probe_bank
.bank2:
    post_code_early 0x2D
    shl cx,8
    or dx,cx
    mov edi,0x3000000
    post_code_early 0x2A
    mov bx,.bank3
    jmp memory_probe_bank
.bank3:
    post_code_early 0x2E
    shl cx,12
    or dx,cx
    movzx esi,dx
    shl esi,16 ; Keep raw bank facts in a register across the map transition.
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
    jmp 0xF000:.real
.real:
    xor ax,ax
    mov ds,ax
    mov es,ax
    mov cx,4
.absent:
    test dl,15
    jnz .present
    or dl,5
.present:
    ror dx,4
    loop .absent
    mov bl,0xE4
    memory_sort_pair 0,1
    memory_sort_pair 0,2
    memory_sort_pair 0,3
    memory_sort_pair 1,2
    memory_sort_pair 1,3
    memory_sort_pair 2,3
    mov cx,4
.zero:
    mov ax,dx
    and ax,15
    cmp al,5
    jne .keep
    and dx,0xFFF0
.keep:
    ror dx,4
    loop .zero
    xor si,si
.match:
    cmp dx,[cs:memory_patterns+si]
    je .mapped
    add si,2
    cmp si,72
    jb .match
    pb_stage 0xEA ; Unsupported topology; never use OEM's last-entry bug.
    jmp hard_halt
.mapped:
    shr si,1
    mov dh,[cs:memory_maps+si]
    xor ch,ch
    xor bh,bh
.route:
    mov cl,bl
    and cl,3
    mov al,bh
    sub al,cl
    and al,3
    shl cl,1
    shl al,cl
    or ch,al
    shr bl,2
    inc bh
    cmp bh,4
    jb .route
    mov al,0x13
    out CHIPSET_INDEX,al
    mov al,ch
    acc_commit_early 0x13
    mov al,0
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xF0
    mov ah,dh
    and ah,15
    or al,ah
    acc_commit_early 0x0
    mov al,0x12
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xFC
    shr dh,4
    and dh,3
    or al,dh
    acc_commit_early 0x12
%ifdef PB430_INTERLEAVE_PROBE
    jmp memory_interleave
.interleave_done:
%endif
    mov eax,esi
    shr eax,16
    mov [0x500],ax
    mov [0x502],ch
    pb_stage 0x21
    lgdt [cs:move_gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp 8:.count
.count:
    mov ax,16
    mov ds,ax
    mov es,ax
    pb_stage 0x22 ; Protected-mode counting is active.
    ; OEM3CF6/3D44 initializes low RAM before any skippable test.
    mov dx,[dword 0x500]
    mov bl,[dword 0x502]
    xor eax,eax
    xor edi,edi
    mov ecx,0x4000
    a32 rep stosd
    mov [dword 0x500],dx
    mov [dword 0x502],bl
    mov ebx,0x10000
.base:
    mov word [dword 0x6FFE],0x55AA
    mov word [ebx+0x6FFE],0xAA55
    cmp word [dword 0x6FFE],0x55AA
    jne .failed_base
    mov word [ebx],0x55AA
    cmp word [ebx],0x55AA
    jne .failed_base
    ; OEM5855 clears every accepted conventional block, as .block does above 1 MiB.
    xor eax,eax
    mov edi,ebx
    mov ecx,0x4000
    a32 rep stosd
    add ebx,0x10000
    cmp ebx,0xA0000
    jb .base
    mov word [dword 0x508],640
    pb_stage 0x23 ; The complete conventional-memory span responded.
    mov ebp,0x100000
.block:
    ; OEM57F1 aliases candidate+stack offset against the proven low stack.
    mov word [dword 0x6FFE],0x55AA
    mov word [ds:ebp+0x6FFE],0xAA55
    cmp word [dword 0x6FFE],0x55AA
    jne .counted
    mov word [ds:ebp],0x55AA
    mov word [ds:ebp+2],0
    cmp word [ds:ebp],0x55AA
    jne .counted
    xor eax,eax
    mov edi,ebp
    mov ecx,0x4000
    a32 rep stosd
    cmp ebp,0x100000
    jne .filled
    pb_stage 0x26 ; The first complete64-KiB count/clear burst finished.
.filled:
    add ebp,0x10000
    cmp ebp,0x4000000
    jb .block
.counted:
    pb_stage 0x24 ; The first absent/aliased64-KiB block bounded physical RAM.
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
    jmp 0xF000:.count_real
.failed_base:
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
    jmp 0xF000:.failed
.count_real:
    xor ax,ax
    mov ds,ax
    mov es,ax
    mov [0x504],ebp
    mov edi,0x600
    mov cx,(0x8000-0x600)/2
    mov ax,0x55AA
.low_write:
    stosw
    not ax
    loop .low_write
    mov di,0x600
    mov cx,(0x8000-0x600)/2
    mov ax,0x55AA
.low_read:
    scasw
    jne .failed
    not ax
    loop .low_read
    pb_stage 0x25 ; Firmware workspace and actual stack passed the data test.
    jmp startup.ram_ready
.failed:
    pb_stage 0xE1
    jmp hard_halt

memory_probe_bank:
    xor cx,cx
    lea esi,[edi+0x400000]
    mov eax,esi
    mov [esi],eax
    mov [esi],eax
    lea esi,[edi+4]
    mov eax,0x12345678
    mov [edi],eax
    mov [edi],eax
    not eax
    mov [esi],eax
    mov [esi],eax
    not eax
    cmp [edi],eax
    jne .done
    mov cx,1
    lea esi,[edi+0x400000]
    cmp [esi],eax
    je .two
    mov cx,4
    jmp .done
.two:
    lea esi,[edi+0x200000]
    not eax
    mov [esi],eax
    not eax
    mov [edi],eax
    cmp [esi],eax
    je .one
    mov cx,3
    jmp .done
.one:
    lea esi,[edi+0x100000]
    mov eax,0x23456789
    not eax
    mov [esi],eax
    not eax
    mov [edi],eax
    cmp [esi],eax
    je .done
    mov cx,2
.done:
    jmp bx
memory_patterns:
    incbin "../reference/pb430-m27c1001.bin",0x18D29,72
memory_maps:
    incbin "../reference/pb430-m27c1001.bin",0x18D83,36

%ifdef PB430_INTERLEAVE_PROBE
; Experiment requested for four4MiB banks. Map changes precede all live RAM state.
; PB430994E..997A supplies mode0 entry; 8D71/8DA7 and ACC386E68 supply map05.
memory_interleave:
    mov eax,esi
    shr eax,16
    cmp ax,0x3333
    jne .topology_failed
    test ch,ch
    jnz .topology_failed
    post_code_early 0x2F
    mov al,0x12
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xF4
    acc_commit_early 0x12
    mov al,0
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xF0
    or al,8
    acc_commit_early 0
    mov al,5
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xEF
    acc_commit_early 5
    in al,CHIPSET_DATA
    test al,0x10
    jnz .mode_failed
    mov al,0
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xF0
    or al,5
    acc_commit_early 0
    in al,CHIPSET_DATA
    and al,15
    cmp al,5
    jne .map_failed
    mov al,0x12
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    test al,0x0B
    jnz .geometry_failed
    post_code_early 0x31
    lgdt [cs:move_gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp 8:.protected
.protected:
    mov ax,16
    mov ds,ax
    mov es,ax
    mov ebp,0xA55AA55A
.pattern:
    xor edi,edi
.write:
    mov eax,edi
    xor eax,ebp
    mov [es:edi],eax
    add edi,4
    cmp edi,0xA0000
    jne .write_next
    mov edi,0x100000
.write_next:
    cmp edi,0x1000000
    jb .write
    xor edi,edi
.read:
    mov eax,edi
    xor eax,ebp
    cmp [es:edi],eax
    jne .ram_failed
    add edi,4
    cmp edi,0xA0000
    jne .read_next
    mov edi,0x100000
.read_next:
    cmp edi,0x1000000
    jb .read
    not ebp
    cmp ebp,0xA55AA55A
    jne .pattern
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
    jmp 0xF000:.real
.real:
    xor ax,ax
    mov ds,ax
    mov es,ax
    post_code_early 0x32
    jmp memory_initialize.interleave_done
.topology_failed:
    pb_stage 0xE3
    jmp hard_halt
.mode_failed:
    pb_stage 0xE2
    jmp hard_halt
.map_failed:
    pb_stage 0xE4
    jmp hard_halt
.geometry_failed:
    pb_stage 0xE5
    jmp hard_halt
.ram_failed:
    pb_stage 0xE6
    jmp hard_halt
memory_interleave_end:
%endif
