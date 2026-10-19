%macro pb_stage 1
    post_code_early %1
%assign pb_stage_exit 0
%ifdef PB430_TRACE_STAGE
%if PB430_TRACE_STAGE == %1
%assign pb_stage_exit 1
%endif
%endif
%ifdef PB430_TRACE_FAILURE
%if %1 >= 0xE0
%assign pb_stage_exit 1
%endif
%endif
%if pb_stage_exit
    mov dx,0x80
    mov al,'8'
    out dx,al
    mov al,'6'
    out dx,al
    mov al,'B'
    out dx,al
    mov al,'o'
    out dx,al
    mov al,'x'
    out dx,al
    mov al,1
    out dx,al
    mov al,5
    out dx,al
    mov dx,0x501
    mov al,4
    out dx,al
    inc dx
    mov al,(%1)&0x7F
    out dx,al
%endif
%endmacro
startup:
    cli
    cld
    jmp 0xF000:.normalized
.normalized:
    xor ax,ax
    mov ds,ax
    mov es,ax
    in al,KBC_STATUS
    mov bh,al
    mov al,0x8F
    out 0x70,al
    in al,0x84
    in al,0x71
    mov bl,al
    xor al,al
    out 0x71,al
    test bh,4
    jz .normal
    cmp bl,5
    je .resume_eoi
    cmp bl,0x0A
    jne .normal
    jmp .resume
.resume_eoi:
    mov al,0x20
    out 0xA0,al
    out 0x20,al
.resume:
    mov al,bl ; Identify a service resume instead of normal POST, without a stack.
    out POST_PORT,al
    mov eax,cr0
    and eax,0x9FFFFFFF
    mov cr0,eax
    mov ax,0x40
    mov ds,ax
    jmp far [0x67]
.normal:
    mov esp,edx ; Service continuations retain their caller's original stack.
    ; A saved AT-refresh disable can outlive the trial marker and corrupt RAM.
    pb430_restore_field 0x18,1,0,0xF3
    xor bp,bp
    test bh,4
    jz .classified
    cmp word [0x472],0x1234
    jne .classified
    inc bp
.classified:
    pb_stage 0x10
.cache_off:
    ; Keep L1 off before modular RAM work without an unreferenced write-back cycle.
    ; OEM963D..964A is also byte-identical to the cold probe prefix8F3A..8F47.
    incbin "../reference/pb430-m27c1001.bin",0x1963D,0x0E
.refresh_dma:
    pb430_refresh_dma
.refresh_dma_ready:
    pb430_timing_restore
.write_timing_reset_ready:
    pb430_timing_recover
.ras_reset_ready:
%ifdef PB430_CACHE_BURST_PROBE
    pb430_burst_clear
.burst_reset_ready:
%endif
    ; Restore normal refresh before warm cache teardown or any DRAM work.
    mov al,5
    out CHIPSET_INDEX,al
    out 0xED,al
    in al,CHIPSET_DATA
    and al,0xFC
    out CHIPSET_DATA,al
    out 0xED,al
    mov al,0x0C
    out 0x61,al
    ; Presario presentation: blank both VGA/CGA owners before long POST.
    mov dx,0x3B8
    mov al,1
    out dx,al
    mov dx,0x3D8
    out dx,al
    mov dx,0x3BA
    in al,dx
    mov dx,0x3DA
    in al,dx
    mov dx,0x3C0
    xor al,al
    out dx,al
    test bp,bp
    jnz .warm_memory
.clock:
    ; OEME067..E07B initializes06 before clearing shutdown and sampling78.
    mov al,6
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,0x13
    out CHIPSET_DATA,al
    mov al,0x8F
    out 0x70,al
    xor al,al
    out 0xED,al
    out 0x71,al
    out 0x78,al
    ; OEM reset E05B chooses06 from actual board jumpers78, not CPU guesses.
    in al,0x78
    and al,7
    mov ah,0x13
    cmp al,4
    jne .clock5
    mov ah,0x33
    jmp .clock_write
.clock5:
    cmp al,5
    jne .clock_write
    mov ah,0xB7
.clock_write:
    mov al,6
    out CHIPSET_INDEX,al
    mov al,ah
    out CHIPSET_DATA,al
    ; OEMF163..F19E precedes the later8CD1 cold table.
.initial_setup:
    mov si,.initial_table
    mov cx,19
.initial:
    cs lodsw
    out CHIPSET_INDEX,al
    out 0xED,al
    cs lodsw
    out CHIPSET_DATA,al
    out 0xED,al
    loop .initial
    mov al,0
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,0x20
    out CHIPSET_DATA,al
    mov al,0x12
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,0x4D
    out CHIPSET_DATA,al
    out 0xED,al
    mov al,5
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,0x96
    out CHIPSET_DATA,al
.initial_done:
    mov si,.cold_table
.cold:
    cs lodsw
    cmp al,0xFF
    je .cold_ready
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,ah
    out CHIPSET_DATA,al
    out 0xED,al
    jmp .cold
.cold_ready:
    mov byte [0x50A],0
    mov byte [0x510],0
    pb_stage 0x20
    jmp memory_initialize
.warm_memory:
    post_code_early 0x11
    ; OEM3A3F/9631 precedes all warm BIOS-state reads; retained RAM owns this stack.
    mov ebp,esp
    xor ax,ax
    mov ss,ax
    mov sp,0x7C00
    mov di,.warm_cache_return
    jmp cache_stock_warm_entry
.warm_cache_return:
    cli ; The modular startup rebuilds its vectors before enabling IRQs.
    mov esp,ebp
    mov ax,[0x40E]
    cmp ax,STATE_SEG
    jne .cold_entry
    mov es,ax
    post_code_early 0x1B
    ; OEM8E88..8E9C: clear1E bit5 before touching BIOS RAM.
.warm_cache:
    mov al,0x1E
    out CHIPSET_INDEX,al
    in al,CHIPSET_DATA
    and al,0xDF
    mov ah,al
    mov al,0x1E
    out CHIPSET_INDEX,al
    out 0xED,al
    mov al,ah
    out CHIPSET_DATA,al
    out 0xED,al
.warm_cache_ready:
    mov eax,[es:HW_CACHE_PRESENT]
    mov [0x50B],eax
    mov al,[es:HW_CACHE_LAST]
    mov [0x50F],al
    mov al,[es:HW_CACHE_VALID]
    mov [0x511],al
    mov byte [0x510],1
    movzx ebp,word [es:S_EXTENDED_KIB]
    add ebp,1024
    shl ebp,10
    mov [0x504],ebp
    mov ax,[es:HW_BANK_CODES]
    mov [0x500],ax
    mov al,[es:HW_ROUTING]
    mov [0x502],al
    mov al,[es:HW_VGA_REQUIRED]
    mov [0x50A],al
    mov ax,[0x413]
    add ax,CFG_PLATFORM_STATE_KIB
    mov [0x508],ax
    xor ax,ax
    mov es,ax
    jmp .ram_ready
.cold_entry:
    jmp .clock
.ram_ready:
    mov edi,esp
    xor ax,ax
    mov ss,ax
    mov esp,CFG_PLATFORM_STACK_TOP
    push edi
    mov ax,STATE_SEG
    mov fs,ax
    mov es,ax
    xor di,di
    xor ax,ax
    mov cx,CFG_PLATFORM_STATE_KIB*512
    rep stosw
    pop eax
    mov [fs:S_CPU_SIGNATURE],ax
    mov eax,[0x504]
    shr eax,10
    sub eax,1024
    mov [fs:S_EXTENDED_KIB],ax
    mov [fs:S_INSTALLED_KIB],ax
    mov ax,[0x500]
    mov [fs:HW_BANK_CODES],ax
    mov al,[0x502]
    mov [fs:HW_ROUTING],al
    mov al,[0x50A]
    mov [fs:HW_VGA_REQUIRED],al
    cmp byte [0x510],1
    jne .cache_state_ready
    mov byte [fs:HW_CACHE_WARM],1
    cmp byte [0x511],CACHE_STATE_VALID
    jne .cache_state_ready
    mov ax,[0x50B]
    mov [fs:HW_CACHE_PRESENT],ax
    mov al,[0x50D]
    mov [fs:HW_CACHE_QUALIFIED],al
    mov al,[0x50F]
    mov [fs:HW_CACHE_LAST],al
    mov byte [fs:HW_CACHE_VALID],CACHE_STATE_VALID
.cache_state_ready:
    mov bp,[0x508]
    xor ax,ax
    mov es,ax
    xor di,di
    mov cx,0x500/2
    rep stosw
    mov di,STATE_BASE
    mov cx,(0xA00-STATE_BASE)/2
    rep stosw
    mov word [0x40E],STATE_SEG
    mov ax,bp
    sub ax,CFG_PLATFORM_STATE_KIB
    mov [0x413],ax
    mov byte [fs:0],CFG_PLATFORM_STATE_KIB
    mov di,0
    mov cx,256
.vector:
    mov ax,default_iret
    stosw
    mov ax,0xF000
    stosw
    loop .vector
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
    set_vector 0x70,int70
    set_vector 0x74,int74
    set_vector 0x75,int75
    set_vector 0x76,int76
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
    pb_stage 0x30
    call cache_initialize
    call cache_initial_policy
    call shadow_system_bios
    pb_stage 0x40
    call init_pic_pit
    pb_stage 0x41
    call init_rtc
    pb_stage 0x42
    call init_superio
    pb_stage 0x43
    call init_at_prerequisites
    pb_stage 0x50
    call initialize_video
    jc video_failed
    pb_stage 0x60
    call init_keyboard
    pb_stage 0x48
    call arm_keyboard_runtime
    jc keyboard_runtime_failed
    call board_a20_handoff
    pb_stage 0x49
    mov byte [0x400+KB_POST_STATE],1
    sti
    call load_bios_state
    mov byte [fs:P_PHASE],0
    mov byte [fs:P_ROM_COUNT],0
    call post_ui_begin
    pb_stage 0x51
    jmp .post_settings
.initial_table:
    incbin "../reference/pb430-m27c1001.bin",0x1F6AB,76
.cold_table:
    dw 0x8002,0x2000,0x9001,0x1003,0x1404,0x1805,0x1407
    dw 0x0008,0x0309,0x040A,0x150B,0x0012,0x0013,0x0018
    dw 0x0019,0xAC1A,0x101B,0x001D,0x001E,0x0225,0x0026,0x00FF
