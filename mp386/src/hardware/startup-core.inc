%macro mp386_early_wait 0
    xor cx,cx
%%wait:
    in al,0x64
    test al,2
    loopne %%wait
    jnz startup.early_failed
%endmacro

startup:
    cli
    cld
    post_code_early 0x10
    mov esp,edx
    shl esp,16                 ; Keep reset identity above the ROM return stack.
    xor ax,ax
    mov ds,ax
    mov es,ax
    mov al,0x8F
    out 0x70,al
    in al,0x71
    mov bl,al
    xor al,al
    out 0x71,al
    in al,0x64
    test al,4
    jz .cache_holdoff
    cmp bl,5
    je .resume_eoi
    cmp bl,0x0A
    je .resume
.cache_holdoff:
    ; A CPU-only warm reset can retain enabled external cache.
    mov ax,cs
    mov ss,ax
    mov sp,.cache_return
    xor si,si
    jmp oem_cache_92EB
.cache_return: dw .cache_held
.cache_held:
.cpu_holdoff_begin:
    mp_cpu_holdoff
.cpu_holdoff_end:
    ; A hard reset can retain the warm flag and unsafe MCU timings.
    mov al,0xB6
    out 0x70,al
    in al,0x71
    cmp al,0xAB
    je .cold
    in al,0x64
    test al,4
    jz .cold
    cmp word [0x40E],STATE_SEG
    jne .cold
    mov ax,STATE_SEG
    mov es,ax
    cmp dword [es:HW_STATE_VALID],MP_MEMORY_MAGIC
    jne .cold
    mov cx,[es:HW_MCU_COUNT]
    cmp cx,1
    jb .cold
    cmp cx,3
    ja .cold
    xor si,si
.warm_ids:
    mov dx,si
    shl dx,8
    mov ax,dx
    out 0x26,ax
    in ax,0x24
    cmp si,cx
    jae .warm_absent
    cmp ah,dh
    jne .cold
    jmp .warm_next_id
.warm_absent:
    cmp ax,0xFFFF
    jne .cold
.warm_next_id:
    inc si
    cmp si,4
    jb .warm_ids
    movzx ebx,word [es:S_EXTENDED_KIB]
    cmp ebx,0x7C00             ; Complete32MiB mappingwindow, including >16MiB.
    ja .cold
    add ebx,1024
    cmp ebx,1024
    jbe .cold
    test bx,63
    jnz .cold
    mov dx,bx
    shr dx,6
    xor bx,bx
    xor di,di
    xor si,si
    mov bp,1
    mov cx,6
.warm_inventory:
    mov ax,di
    shr ax,2
    cmp ax,[es:HW_MCU_COUNT]
    jb .warm_bank
    cmp word [es:HW_BANK_COUNTS+di],0
    jne .cold
.warm_bank:
    mov ax,[es:HW_BANK_COUNTS+di]
    cmp ax,512
    ja .cold
    test ax,ax
    jz .warm_empty_bank
    or si,bp
.warm_empty_bank:
    add bx,ax
    jc .cold
    add di,2
    shl bp,1
    loop .warm_inventory
    cmp word [es:HW_BANK_COUNTS],8
    jb .cold
    cmp si,[es:HW_BANK_CODES]
    jne .cold
    cmp bx,dx
    jb .cold
    cmp bx,512
    ja .cold
    movzx ebx,bx
    shl ebx,22
    movzx esi,word [es:HW_BANK_CODES]
    shl esi,16
    jmp .mapped
.resume_eoi:
    mov al,0x20
    out 0x20,al
.resume:
    mov ax,0x40
    mov ds,ax
    jmp far [0x67]
.cold:
    mov ax,cs
    mov ss,ax
    mov sp,.cold_return
    post_code_early 0x11
    jmp tiger_cold
.cold_return: dw .count_memory
.count_memory:
    post_code_early 0x12
    ; Memory owner returns installedKiB and six-bank mask in upperBX/SI.
.mapped:
    post_code_early 0x20
    ; MR9ADC..9B0E: quiesce legacy video and AT devices before controller setup.
    mov dx,0x3B8
    mov al,1
    out dx,al
    out 0xEB,ax
    mov dx,0x3D8
    out dx,al
    out 0xEB,ax
    mov dx,0x3BA
    in al,dx
    out 0xEB,ax
    mov dx,0x3DA
    in al,dx
    out 0xEB,ax
    mov dx,0x3C0
    xor al,al
    out dx,al
    out 0x0D,al
    out 0xEB,ax
    out 0xDA,al
    out 0xEB,ax
    mov dx,0x3F2
    out dx,al
    out 0xEB,ax
    mov al,0x0C                 ; MR9B0A masks parity/channel NMI before RAM use.
    out 0x61,al
    out 0xEB,ax
    ; MR9BF3..9C5A: self-test precedes its D1/CF output-port transaction.
    xor cx,cx
.early_drain:
    in al,0x64
    test al,1
    jz .early_empty
    in al,0x60
    loop .early_drain
    jmp .early_failed
.early_empty:
    mp386_early_wait
    mov al,0xAA
    out 0x64,al
    xor cx,cx
.early_reply:
    in al,0x64
    test al,1
    loopz .early_reply
    jz .early_failed
    in al,0x60
    cmp al,0x55
    jne .early_failed
    mp386_early_wait
    mov al,0xD1
    out 0x64,al
    mp386_early_wait
    mov al,0xCF
    out 0x60,al
    mp386_early_wait
    post_code_early 0x21
    mov si,.at_table
    mov cx,21
    xor dh,dh
.at:
    cs lodsw
    mov dl,ah
    out dx,al
    out 0xEB,ax
    loop .at
    mov ax,cs
    mov ss,ax
    mov sp,.warm_return
    post_code_early 0x22
    jmp tiger_warm
.warm_return: dw .ram_ready
.ram_ready:
    post_code_early 0x23
    mov edi,esp
    shr edi,16
    mov edx,ebx
    shr edx,16
    mov ebp,esi
    shr ebp,16
    xor ax,ax
    mov ss,ax
    mov esp,CFG_PLATFORM_STACK_TOP
    push edi
    push edx
    push ebp
    mov ax,STATE_SEG
    mov fs,ax
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,CFG_PLATFORM_STATE_KIB*512
    rep stosw
%ifdef MP386_MEMORY_TRACE
    cmp dword [0x0710],0x4833504D
    jne .no_map_capture
    pushad
    mov si,0x0720
    mov di,0x1040
    mov cx,51
    rep movsw
    mov dword [es:0x1020],0x4833504D
    mov dword [0x0710],0
    popad
.no_map_capture:
%endif
    pop ebp
    pop edx
    pop edi
    mov [fs:S_CPU_SIGNATURE],di
    mov [fs:HW_BANK_CODES],bp
    xor bx,bx
.save_inventory:
    mov ax,[MP_MEMORY_SCRATCH+bx]
    mov [fs:HW_BANK_COUNTS+bx],ax
    add bx,2
    cmp bx,12
    jb .save_inventory
    mov ax,[MP_MEMORY_SCRATCH+12]
    mov [fs:HW_MCU_COUNT],ax
    call cache_initialize
    sub dx,1024
    mov [fs:S_EXTENDED_KIB],dx
    mov [fs:S_INSTALLED_KIB],dx
    movzx eax,dx
    add eax,1024
    shl eax,10
    call memory_qualify_contiguous
    shr eax,10
    sub ax,1024
    mov [fs:S_EXTENDED_KIB],ax
    mov [fs:S_INSTALLED_KIB],ax
.linear_capacity_ready:
    mov dword [fs:HW_STATE_VALID],MP_MEMORY_MAGIC
    mov byte [fs:0],CFG_PLATFORM_STATE_KIB
    xor ax,ax
    mov es,ax
    xor di,di
    mov cx,0x500/2
    rep stosw
    mov cx,256
    xor di,di
.vectors:
    mov ax,default_iret
    stosw
    mov ax,cs
    stosw
    loop .vectors
    set_vector 0x02,chipset_nmi
    set_vector 0x08,int08
    set_vector 0x09,int09
    set_vector 0x0E,int0e
    set_vector 0x11,int11
    set_vector 0x12,int12
    set_vector 0x13,int13
    set_vector 0x15,int15
    set_vector 0x16,int16
    set_vector 0x18,int18
    set_vector 0x19,int19
    set_vector 0x1A,int1a
    set_vector 0x1E,floppy_dpt_1440
    set_vector 0x1D,legacy_video_params
    set_vector 0x70,int70
    set_vector 0x74,int74
    set_vector 0x75,int75
    set_vector 0x76,int76
    mov word [0x40E],STATE_SEG
    mov word [0x413],STATE_SEG >> 6
    mov word [0x410],0x20
    mov word [0x41A],KB_BUFFER_START
    mov word [0x41C],KB_BUFFER_START
    mov word [0x480],KB_BUFFER_START
    mov word [0x482],KB_BUFFER_END
    mov byte [0x400+KB_EXT_FLAGS],0x10
    mov byte [0x449],3
    mov word [0x44A],80
    mov word [0x44C],0x1000
    mov word [0x463],0x3D4
    mov byte [0x484],24
    mov word [0x485],16
    call init_pic_pit
    call init_rtc
    mov al,0x36
    call rtc_read
    call chipset_timing_startup_state
    call rtc_write
    ; MR9E0B..9E19: inhibit keyboard IRQs until its runtime owner is ready.
    mp386_early_wait
    mov al,0x20
    out 0x64,al
    xor cx,cx
.video_kbc_reply:
    in al,0x64
    test al,1
    loopz .video_kbc_reply
    jz .early_failed
    in al,0x60
    and al,0xA0
    or al,0x54
    mov ah,al
    mp386_early_wait
    mov al,0x60
    out 0x64,al
    mp386_early_wait
    mov al,ah
    out 0x60,al
    mp386_early_wait
    ; MR keeps IRQ0/IRQ1 masked across its STI-enabled option-ROM call.
    mov al,0xFB
    out 0x21,al
    out 0xEB,ax
    mov al,0x8D
    out 0x70,al
    out 0xEB,ax
    call initialize_video
    jc video_failed
    call init_keyboard
    call arm_keyboard_runtime
    jc keyboard_runtime_failed
    call mitsubishi_cache_off_initialize
    call mp_shadow_prepare
    mov byte [0x400+KB_POST_STATE],1
    mov al,0xFC
    out 0x21,al
    mov al,0x0D
    out 0x70,al
    sti
    call load_bios_state
    mov byte [fs:P_PHASE],0
    call post_ui_begin
    jmp .post_settings
.memory_failed:
    post_code_early 0xE1
    mov ax,bp                   ; Retain the probe's bank byte on the POST card.
    out POST_PORT,al
    jmp hard_halt
.early_failed:
    post_code_early 0xE2
    jmp hard_halt
.at_table:
    dw 0x0D00,0x0800,0x0B40,0x0B41,0x0B42,0x0B43,0xDA00
    dw 0xD000,0xD6C0,0xD641,0xD642,0xD643,0xD400,0x43B6
    dw 0x4354,0x4112,0x8F1C,0x708F,0x7100,0x708A,0x7126
