u_post_delay_values dw u_post_delay0,u_post_delay5,u_post_delay10
%ifndef PB430_PORT
u_post_delay:
    ui_string 'POST Delay (Seconds)', u_post_delay
%endif
u_post_delay0 db '0',0
u_post_delay5 db '5',0
u_post_delay10 db '10',0
