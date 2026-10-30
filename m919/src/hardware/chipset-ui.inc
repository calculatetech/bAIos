%include "setup/enum-ui.inc"
chipset_ui_parameters:
    call chipset_ui_enum_parameters
    call chipset_ui_choice_order
    mov [fs:U_CHIP_VALUE],al
    ret
chipset_ui_editable:
    clc
    ret
chipset_ui_commit:
    pushad
    call chipset_ui_descriptor
    mov si,[cs:si+7]
    mov al,[fs:U_CHIP_VALUE]
    call chipset_ui_choice_order
    mov [fs:U_CHIP_VALUE],al
    call chipset_ui_enum_commit
    popad
    ret
chipset_ui_choice_order:
    cmp si,chip_l2_values
    jne .waits
    xor al,1
    mov si,chip_enable_values
    ret
.waits:
    cmp si,chip_wait_values
    jne .type
    xor al,3
    mov si,chip_wait_choices
    ret
.type:
    cmp si,chip_type_values
    jne .policy
    xor al,1
    mov si,chip_type_choices
    ret
.policy:
    cmp si,chip_policy_values
    jne .burst
    xor al,1
    mov si,chip_policy_choices
    ret
.burst:
    cmp si,chip_burst_values
    jne .edo
    xor al,3
    mov si,chip_burst_choices
    ret
.edo:
    cmp si,chip_edo_burst_values
    jne .reverse_three
    xor al,1
    mov si,chip_edo_burst_choices
    ret
.reverse_three:
    cmp si,chip_keep_switch_values
    jne .ldev
    mov si,chip_keep_switch_choices
    jmp .three
.ldev:
    cmp si,chip_ldev_values
    jne .isa
    mov si,chip_ldev_choices
    jmp .three
.isa:
    cmp si,chip_isa_values
    jne .lock
    mov si,chip_isa_choices
.three:
    neg al
    add al,2
    ret
.lock:
    cmp si,chip_lock_values
    jne .devsel
    mov si,chip_lock_choices
    jmp .swap_first
.devsel:
    cmp si,chip_devsel_values
    jne .keyboard
    mov si,chip_devsel_choices
    jmp .swap_first
.keyboard:
    cmp si,chip_kbc_values
    jne .pci_clock
    mov si,chip_kbc_choices
.swap_first:
    cmp al,2
    jae .done
    xor al,1
    ret
.pci_clock:
    cmp si,chip_pci_clock_values
    jne .recovery
    mov si,chip_pci_clock_choices
    xor al,3
    ret
.recovery:
    cmp si,chip_recovery_values
    jne .posted
    mov si,chip_recovery_choices
    xor al,3
.posted:
    cmp si,chip_posted_values
    jne .irq
    mov si,chip_posted_choices
    xor al,1
    ret
.irq:
    cmp si,chip_irq_values
    jne .done
    mov si,chip_irq_choices
    cmp al,0
    je .swap_irq
    cmp al,10
    jne .done
.swap_irq:
    xor al,10
.done:
    ret
