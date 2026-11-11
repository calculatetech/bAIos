post_ui_pnp_ui_count:
    movzx bx,byte [fs:U_PNP_SCREEN]
    mov cl,[POST_UI_DATA:pnp_counts+bx]
    ret
post_ui_pnp_ui_select:
    cmp byte [fs:U_PNP_SCREEN],0
    jne .edit
    mov al,[fs:U_FIELD]
    cmp al,4
    jae .edit
    inc al
    mov [fs:U_PNP_SCREEN],al
    mov byte [fs:U_FIELD],0
    ret
.edit:
    cmp byte [fs:U_PNP_SCREEN],3
    je post_ui_pnp_ui_number
    jmp post_ui_setup_choices

post_ui_pnp_ui_choices:
    pushad
    call post_ui_pnp_ui_parameters
    jmp post_ui_setup_choices.enum

