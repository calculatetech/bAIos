; Complete private POST producer. Module code and journal share one lifetime.
pnp_prepare:
    call pnp_prepare_video
    jmp pnp_configure

; Establish ownership and map the display before video, without ISA probes.
pnp_prepare_video:
%ifndef PNP_EXTERNAL_JOURNAL
    call pnp_journal_begin
    jc .done
%endif
    call pnp_work_begin
    jc .done
    call pnp_seed
    jc .done
%ifdef PB430_PORT
    call CFG_ROM_CODE_SEGMENT:pnp_video_callback
    jc .fixed_failed
%endif
.done:
    ret
%ifdef PB430_PORT
.fixed_failed:
    pushad
    push gs
    mov eax,[fs:PNP_JOURNAL_FIRST]
    call pnp_pointer
    or byte [gs:si+PNP_ROOT_STATUS],1
    pop gs
    popad
    stc
    ret
%endif

; A configured card can add, move or deactivate a BIOS serial/parallel port.
pnp_configure_post:
    push gs
    call pnp_configure
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .done
    call pnp_pointer
    cmp byte [gs:si+PNP_ROOT_CSN_COUNT],0
    je .done
    call pnp_init_peripherals
.done:
    pop gs
    ret

; ISA discovery follows RAM/cache qualification and fixed-port detection.
pnp_configure:
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .done
    push gs
    call pnp_pointer
    cmp dword [gs:si+PNP_ROOT_BUS],0
    jne .ready
    or byte [gs:si+PNP_ROOT_STATUS],1
    pop gs
    ret
.ready:
    cmp byte [gs:si+PNP_ROOT_STATUS],0
    pop gs
    jne .census_only
    xor ax,ax
    call pnp_rom_resources
    jc .census_only
    call pnp_census
    mov al,1
    call pnp_rom_resources
    jc .done
    call pnp_solve
    call pnp_program
.done:
    ret
.census_only:
    call pnp_census
    ret

pnp_finish:
    pushad
    push es
    push gs
    mov eax,[fs:PNP_JOURNAL_FIRST]
    test eax,eax
    jz .release
    call pnp_pointer
.publication:
    mov ax,0x40
    mov es,ax
    mov al,[gs:si+PNP_ROOT_CSN_COUNT]
    mov [es:PNP_ISA],al
    mov ax,[gs:si+PNP_ROOT_READ_PORT]
    mov [es:PNP_ISA+1],ax
    cmp byte [gs:si+PNP_ROOT_STATUS],0
    jne .release
    call pnp_pack_runtime
    jmp .done
.release:
    mov dword [fs:PNP_RUNTIME],0
    stc
.done:
    pop gs
    pop es
    popad
    ret
pnp_allocation_code_end:
