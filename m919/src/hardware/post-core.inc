post_summary_cache:
    call post_cache_name
    mov di,4*160+20*2
    mov bh,7
    jmp setup_text
post_cache_name:
    mov si,u_disabled
    movzx bx,byte [fs:HW_CACHE_CODE]
    test bx,bx
    jz .text
    dec bx
    shl bx,1
    mov si,[cs:cache_off_names+bx]
    test byte [fs:HW_CACHE_FLAGS],4
    jz .text
    mov si,[cs:cache_on_names+bx]
    test byte [fs:C_CHIP+3],0x40
    jz .text
    mov si,[cs:cache_wb_names+bx]
.text:
    ret

cache_off_names dw cache_64_off,cache_128_off,cache_256_off,cache_512_off,cache_1024_off
cache_on_names dw cache_64_on,cache_128_on,cache_256_on,cache_512_on,cache_1024_on
cache_wb_names dw cache_64_wb,cache_128_wb,cache_256_wb,cache_512_wb,cache_1024_wb
cache_64_off db '64 KB Off',0
cache_128_off db '128 KB Off',0
cache_256_off db '256 KB Off',0
cache_512_off db '512 KB Off',0
cache_1024_off db '1024 KB Off',0
cache_64_on db '64 KB WT ',0
cache_128_on db '128 KB WT ',0
cache_256_on db '256 KB WT ',0
cache_512_on db '512 KB WT ',0
cache_1024_on db '1024 KB WT ',0
cache_64_wb db '64 KB WB ',0
cache_128_wb db '128 KB WB ',0
cache_256_wb db '256 KB WB ',0
cache_512_wb db '512 KB WB ',0
cache_1024_wb db '1024 KB WB ',0

post_ui_cache:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax,0xB800
    mov es,ax
    ui_text 3,3,u_post_l1,0x0B
    mov si,u_disabled
    mov eax,cr0
    test eax,0x40000000
    jnz .l1
    mov si,u_post_enabled
.l1:
    mov word [es:3*160+31*2],0x0720
    mov di,3*160+24*2
    mov bh,7
    call setup_text
    pop es
    pop ds
    popad
    ret

post_l2_test_begin:
    push si
    mov si,cache_test_running
    call post_l2_test_text
    pop si
    ret
post_l2_test_passed:
    push si
    mov si,u_post_passed
    call post_l2_test_text
    pop si
    ret
post_l2_test_text:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax,0xB800
    mov es,ax
    push si
    ui_text 7,3,cache_test_title,0x0B
    mov di,7*160+24*2
    call post_clear_value
    pop si
    mov bh,7
    call setup_text
    pop es
    pop ds
    popad
    ret
cache_test_title db 'L2 Cache Test',0
cache_test_running db 'Testing...',0

post_memory_banks:
    pushad
    mov bl,[fs:HW_RAM_BANKS]
    xor cx,cx
    xor dx,dx
.bank:
    bt bx,cx
    jnc .next
    test dx,dx
    jz .digit
    mov ax,0x0720
    stosw
.digit:
    mov ax,0x0730
    add al,cl
    stosw
    inc dx
.next:
    inc cx
    cmp cx,4
    jb .bank
.done:
    popad
    ret

; Same any/all state contract as the donor, using UM8881F shadow registers.
; Cache policy does not alter regional shadow ownership.
post_rom_state:
    pushad
    movzx edi,dx
    movzx ecx,bx
    add edi,ecx
    mov si,0x0100
    movzx ebp,dx
.block:
    mov eax,0x80000054 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    call pci_read
    mov edx,eax
    xor bx,bx
    test dh,0x80
    jz .aggregate
    mov eax,ebp
    cmp ax,0xF000
    jb .regions
    inc bx
    jmp .aggregate
.regions:
    cmp ax,0xC000
    jb .aggregate
    cmp ax,0xE000
    jb .c_d
    test dl,1
    jz .aggregate
    inc bx
    jmp .aggregate
.c_d:
    sub ax,0xC000
    cmp ax,0x1000
    jae .d
    cmp ax,0x800
    jb .first_c
    sub ax,0x800
    shr ax,10
    add ax,2
    jmp .bit
.first_c:
    mov ax,1
    jmp .bit
.d:
    sub ax,0x1000
    shr ax,10
    add ax,4
.bit:
    bt dx,ax
    jnc .aggregate
    inc bx
.aggregate:
    mov ax,si
    or al,bl
    and ah,bl
    mov si,ax
    add ebp,0x80
    cmp ebp,edi
    jb .block
    mov bp,sp
    mov [ss:bp+28],si
    popad
    ret

