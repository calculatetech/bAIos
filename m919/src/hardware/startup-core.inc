startup:
    cli
    cld
    mov esp,edx
    xor ax,ax
    mov ds,ax
    mov es,ax
    ; Preserve the donor's AT shutdown-service continuation before remapping.
    in al,KBC_STATUS
    mov bh,al
    mov al,0x8F
    out 0x70,al
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
    out 0x20,al
.resume:
    mov eax,cr0
    and eax,0x9FFFFFFF
    mov cr0,eax
    mov ax,0x40
    mov ds,ax
    jmp far [0x67]
.normal:
    board_video_blank 1
    wbinvd
    mov eax,cr0
    or eax,0x60000000
    mov cr0,eax
    wbinvd
    xor ax,ax
    out 0x0D,al
    out 0xDA,al
    post_code_early 0x10
    jmp chipset_initialize
.ram_ready:
    mov edi,esp
    xor ax,ax
    mov ss,ax
    mov esp,CFG_PLATFORM_STACK_TOP
    push edi
    mov ax,STATE_SEG
    mov es,ax
    mov fs,ax
    xor di,di
    xor ax,ax
    mov cx,CFG_PLATFORM_STATE_KIB*512
    rep stosw
    pop eax
    mov [fs:S_CPU_SIGNATURE],ax
    mov eax,ebp
    shr eax,10
    sub eax,1024
    mov [fs:S_EXTENDED_KIB32],eax
    mov [fs:S_INSTALLED_KIB32],eax
    cmp eax,0xFC00
    jbe .legacy_count
    mov eax,0xFC00
.legacy_count:
    mov [fs:S_EXTENDED_KIB],ax
    mov [fs:S_INSTALLED_KIB],ax
    xor ax,ax
    mov ds,ax
    mov al,[0x506]
    mov [fs:HW_RAM_BANKS],al
    mov al,[0x509]
    mov [fs:HW_HB52],al
    mov al,[0x504]
    mov [fs:HW_HB53],al
    mov al,[0x505]
    mov [fs:HW_HB61],al
    xor ax,ax
    mov es,ax
    xor di,di
    mov cx,0x500/2
    rep stosw
    mov di,STATE_BASE
    mov cx,(0xA00-STATE_BASE)/2
    rep stosw
    mov ax,STATE_SEG
    mov [0x40E],ax
    mov word [0x413],CFG_PLATFORM_STATE_SEG >> 6
    mov byte [fs:0],CFG_PLATFORM_STATE_KIB
    mov word [fs:M_VGA_BDF],0xFFFF
    mov word [fs:HW_IDE_BDF],0xFFFF
    mov byte [fs:0x200+HW_POSITION],1
    mov di,0
    mov cx,256
.vector:
    mov ax,default_iret
    stosw
    mov ax,CFG_ROM_CODE_SEGMENT
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
    set_vector 0x1A,pci_int1a
    set_vector 0x1E,floppy_dpt_1440
    set_vector 0x70,int70
    set_vector 0x74,int74
    set_vector 0x75,int75
    set_vector 0x76,int76
    set_vector 0x77,int77
    mov word [0x410],0x20
    mov word [0x41A],KB_BUFFER_START
    mov word [0x41C],KB_BUFFER_START
    mov word [0x480],KB_BUFFER_START
    mov word [0x482],KB_BUFFER_END
    mov byte [0x400+KB_EXT_FLAGS],0x10
    call cache_initialize
    ; IBC51 describes installed RAM in 4 MiB units, independently of CMOS.
    mov eax,[fs:S_INSTALLED_KIB32]
    add eax,1024
    shr eax,12
    jnz .ibc_size
    inc eax
.ibc_size:
    shl al,1
    mov bh,al
    mov bl,0x51
    call isa_write
    call init_pic_pit
    call init_rtc
    call init_at_prerequisites
    call init_superio
    call pci_initialize
    call initialize_video
    jc video_failed
    xor ax,ax
    mov ds,ax
    mov es,ax
    mov eax,[0x40]
    mov [0x108],eax             ; INT42 follows the actual VGA entry.
    call init_keyboard
    call arm_keyboard_runtime
    jc keyboard_runtime_failed
    call board_a20_handoff
    mov byte [0x400+KB_POST_STATE],1
    sti
    call load_bios_state
    mov byte [fs:P_PHASE],0
    mov byte [fs:P_ROM_COUNT],0
    call post_ui_begin
%ifdef EMULATOR_CLOCK_NO_ERRORS
    call core_clock_watch_begin
%endif
%ifdef EMULATOR_SETUP_INVALID_NOTICE
    call setup_test_alert_begin
%endif
%ifdef EMULATOR_SETUP_POWERLOSS
    xor ax,ax
    mov fs,ax
%endif
