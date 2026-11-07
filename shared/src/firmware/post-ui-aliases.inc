; Only prefixed source aliases vary between inline and private composition.
; Resident symbols and their ABI never become preprocessor aliases.
%macro post_ui_export 1
%ifdef POST_UI_PRIVATE
%define post_ui_%1 post_ui_core_%1
%else
%define post_ui_%1 %1
%endif
%endmacro
%macro post_ui_import 2
%ifdef POST_UI_PRIVATE
%define post_ui_%1 post_ui_import_%1
%else
%define post_ui_%1 %2
%endif
%endmacro
%include "firmware/post-ui-api.inc"
%unmacro post_ui_export 1
%unmacro post_ui_import 2
%ifdef POST_UI_PRIVATE
%define post_ui_warm_reset post_ui_private_restart
%define post_ui_hard_halt post_ui_private_halt
%define post_ui_summary_floppy post_ui_core_post_debug_summary.floppy
%define post_ui_disk_body post_ui_core_post_ui_disks.device
%else
%define post_ui_summary_floppy post_debug_summary.floppy
%define post_ui_disk_body post_ui_disks.device
%define post_ui_warm_reset warm_reset
%define post_ui_hard_halt hard_halt
%endif

; Qualified local targets share the same borrowed near-call frame.
%ifdef POST_UI_PRIVATE
%define post_ui_setup_choices.draw post_ui_core_setup_choices.draw
%else
%define post_ui_setup_choices.draw setup_choices.draw
%endif
%ifdef POST_UI_PRIVATE
%define post_ui_setup_choices.enum post_ui_core_setup_choices.enum
%else
%define post_ui_setup_choices.enum setup_choices.enum
%endif
%ifdef POST_UI_PRIVATE
%define post_ui_setup_number_editor.done post_ui_core_setup_number_editor.done
%else
%define post_ui_setup_number_editor.done setup_number_editor.done
%endif
