; Shared Boot-page labels and sorted saved choices.
%ifndef PB430_PORT
%include "firmware/setup-post-delay-values.inc"
%endif
%ifdef PRESARIO_SHARED_OWNER
%include "firmware/settings-base-fields.inc"
%endif
u_help_post_delay1:
    ui_string 'Pause before the summary.', u_help_post_delay1
u_help_post_delay2:
    ui_string 'Use 5 seconds. 0 skips.', u_help_post_delay2
%ifdef BOARD_PCI_VIDEO_ORDER
u_video_order_values dw u_video_isa,u_video_pci
u_video_order:
    ui_string 'Video Init Order', u_video_order
u_video_isa db 'ISA/PCI',0
u_video_pci db 'PCI/ISA',0
u_help_video_order1:
    ui_string 'Choose which display card starts first.', u_help_video_order1
u_help_video_order2:
    ui_string 'Use PCI/ISA. The other bus is the fallback.', u_help_video_order2
%endif

%ifdef PB430_PORT
u_post_delay:
    ui_string 'POST Delay (Seconds)', u_post_delay
%endif
