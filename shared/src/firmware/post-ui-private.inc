; Private code, resident F000 read-only data. No runtime service moves here.
%define POST_UI_PRIVATE
%define POST_UI_DATA ds
%include "firmware/post-ui-aliases.inc"
%include "firmware/setup-loop.inc"
%include "firmware/setup-draw.inc"
%include "firmware/post-summary.inc"
%include "firmware/post-header.inc"
%include "firmware/post-screen.inc"
%include "firmware/post-screen-detail.inc"
%include "firmware/setup-actions.inc"
%include "firmware/setup-modal.inc"
%include "firmware/setup-fields.inc"
%include "firmware/setup-fields-edit.inc"
%include "firmware/setup-clock-edit.inc"
%include "firmware/setup-ide-ui.inc"
%include "firmware/setup-ports-ui.inc"
%include "firmware/setup-pnp-navigation.inc"
%include "firmware/setup-pnp-controls.inc"
%include "firmware/setup-chipset-choices.inc"
%undef POST_UI_PRIVATE
%define POST_UI_DATA cs
%include "firmware/post-ui-aliases.inc"
; The resident facade owns FLAGS/BX slots. Restore inputs before the body,
; then write its actual outputs back without changing any other register.
%macro post_ui_export 1
post_ui_export_%1:
    push bp
    mov bp,sp
    mov bx,[ss:bp+10]
    push word [ss:bp+12]
    popf
    pop bp
    call post_ui_core_%1
    pushf
    push bp
    mov bp,sp
    mov [ss:bp+12],bx
    mov bx,[ss:bp+2]
    mov [ss:bp+14],bx
    pop bp
    popf
    ret
%endmacro
%macro post_ui_import 2
post_ui_import_%1:
    call CFG_ROM_CODE_SEGMENT:post_ui_callback_%1
    ret
%endmacro
%include "firmware/post-ui-api.inc"
%unmacro post_ui_export 1
%unmacro post_ui_import 2
post_ui_private_restart:
    jmp CFG_ROM_CODE_SEGMENT:warm_reset
post_ui_private_halt:
    jmp CFG_ROM_CODE_SEGMENT:hard_halt
