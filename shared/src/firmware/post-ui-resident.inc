; Resident services remain callable after the transient module is released.
post_ui_invoke:
    call pnp_post_invoke
    jc .missing
    pop bx
    popf
    ret
.missing:
    pop bx
    popf
    stc
    ret
%macro post_ui_export 1
%endmacro
%macro post_ui_import 2
post_ui_callback_%1:
    call %2
    retf
%endmacro
%include "firmware/post-ui-api.inc"
%unmacro post_ui_export 1
%unmacro post_ui_import 2
