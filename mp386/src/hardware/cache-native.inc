; Complete OEM cache diagnostic, exercise helper and normal E0 policy.
; Private record storage and phase/display exits are adapted in cache.inc.
; No diagnostics or stack operations are added inside the transient owner.
%include "hardware/cache-control.inc"
oem_cache_2454:
    shl ebp, 0x10
oem_cache_2458:
    shl eax, 0x10
oem_cache_245C:
    mov al, 0xe2
oem_cache_245E:
    mov bp, oem_cache_2463
oem_cache_2461:
    jmp short oem_cache_23FC
oem_cache_2463:
    or al, 2
oem_cache_2465:
    mov ah, al
oem_cache_2467:
    mov al, 0xe2
oem_cache_2469:
    mov cx, ax
oem_cache_246B:
    mov bp, oem_cache_2470
oem_cache_246E:
    jmp short oem_cache_2407
oem_cache_2470:
    mov ax, 0x1e0
oem_cache_2473:
    mov bp, oem_cache_2478
oem_cache_2476:
    jmp short oem_cache_2407
oem_cache_2478:
    mov ax, cx
oem_cache_247A:
    and ah, 0xfd
oem_cache_247D:
    mov bp, oem_cache_2482
oem_cache_2480:
    jmp short oem_cache_2407
oem_cache_2482:
    shr ebp, 0x10
oem_cache_2486:
    mov bx, di
oem_cache_2488:
    mov cx, 0x4000
oem_cache_248B:
    rep lodsw
oem_cache_248D:
    shr eax, 0x10
oem_cache_2491:
    mov cx, 0x4000
oem_cache_2494:
    mov di, bx
oem_cache_2496:
    rep stosw
oem_cache_2498:
    mov cx, 0x4000
oem_cache_249B:
    mov di, bx
oem_cache_249D:
    repe scasw
oem_cache_249F:
    je short oem_cache_24A4
oem_cache_24A1:
    add bp, 3
oem_cache_24A4:
    jmp bp
oem_cache_63AB:
    in al, 0x5f
oem_cache_63AD:
    test al, 0x80
oem_cache_63AF:
    je short oem_cache_63B4
oem_cache_63B1:
    jmp near oem_cache_6747
oem_cache_63B4:
    mov bp, oem_cache_63BD
oem_cache_63B7:
    call mp_cache_title
oem_cache_63BA:
    jmp short oem_cache_63CC
oem_cache_63BC:
    nop
oem_cache_63BD:
    db 0x43,0x41,0x43,0x48,0x45,0x20,0x54,0x45,0x53,0x54,0x20,0x20,0x20,0x20,0x20
oem_cache_63CC:
    mov dx, 0x2cf
oem_cache_63CF:
    mov bp, oem_cache_63D5
oem_cache_63D2:
    jmp near mp_cache_record_read
oem_cache_63D5:
    and al, 3
oem_cache_63D7:
    je short oem_cache_63F1
oem_cache_63D9:
    mov al, 0xe0
oem_cache_63DB:
    mov bp, oem_cache_63E1
oem_cache_63DE:
    jmp near oem_cache_23FC
oem_cache_63E1:
    and al, al
oem_cache_63E3:
    je short oem_cache_63F1
oem_cache_63E5:
    mov ax, 0xe0
oem_cache_63E8:
    mov bp, oem_cache_63EE
oem_cache_63EB:
    jmp near oem_cache_2407
oem_cache_63EE:
    jmp near oem_cache_669A
oem_cache_63F1:
    mov ax, 0xaae0
oem_cache_63F4:
    mov bp, oem_cache_63FA
oem_cache_63F7:
    jmp near oem_cache_2407
oem_cache_63FA:
    mov al, 0xe0
oem_cache_63FC:
    mov bp, oem_cache_6402
oem_cache_63FF:
    jmp near oem_cache_23FC
oem_cache_6402:
    cmp al, ah
oem_cache_6404:
    jne short oem_cache_63E5
oem_cache_6406:
    mov ax, 0x55e0
oem_cache_6409:
    mov bp, oem_cache_640F
oem_cache_640C:
    jmp near oem_cache_2407
oem_cache_640F:
    mov al, 0xe0
oem_cache_6411:
    mov bp, oem_cache_6417
oem_cache_6414:
    jmp near oem_cache_23FC
oem_cache_6417:
    cmp al, ah
oem_cache_6419:
    jne short oem_cache_63E5
oem_cache_641B:
    mov ax, 0xe0
oem_cache_641E:
    mov bp, oem_cache_6424
oem_cache_6421:
    jmp near oem_cache_2407
oem_cache_6424:
    mov al, 0xe2
oem_cache_6426:
    mov bp, oem_cache_642C
oem_cache_6429:
    jmp near oem_cache_23FC
oem_cache_642C:
    mov ah, al
oem_cache_642E:
    or ah, 2
oem_cache_6431:
    mov al, 0xe2
oem_cache_6433:
    mov bp, oem_cache_6439
oem_cache_6436:
    jmp near oem_cache_2407
oem_cache_6439:
    mov al, 0xe2
oem_cache_643B:
    mov bp, oem_cache_6441
oem_cache_643E:
    jmp near oem_cache_23FC
oem_cache_6441:
    cmp al, ah
oem_cache_6443:
    je short oem_cache_6448
oem_cache_6445:
    jmp near oem_cache_669A
oem_cache_6448:
    and ah, 0xfd
oem_cache_644B:
    mov al, 0xe2
oem_cache_644D:
    mov bp, oem_cache_6453
oem_cache_6450:
    jmp near oem_cache_2407
oem_cache_6453:
    mov al, 0xe2
oem_cache_6455:
    mov bp, oem_cache_645B
oem_cache_6458:
    jmp near oem_cache_23FC
oem_cache_645B:
    cmp al, ah
oem_cache_645D:
    je short oem_cache_6462
oem_cache_645F:
    jmp near oem_cache_669A
oem_cache_6462:
    mov dx, 0x2dd
oem_cache_6465:
    mov bp, oem_cache_646B
oem_cache_6468:
    jmp near mp_cache_record_read
oem_cache_646B:
    mov cl, al
oem_cache_646D:
    mov dx, 0x800c
oem_cache_6470:
    mov bp, oem_cache_6476
oem_cache_6473:
    jmp near mp_memory_ti_read
oem_cache_6476:
    test ah, 0x80
oem_cache_6479:
    jne short oem_cache_6485
oem_cache_647B:
    add dh, 0x10
oem_cache_647E:
    dec cl
oem_cache_6480:
    jne short oem_cache_6470
oem_cache_6482:
    jmp near oem_cache_6747
oem_cache_6485:
    mov bx, ax
oem_cache_6487:
    shl ebx, 0x10
oem_cache_648B:
    inc dl
oem_cache_648D:
    mov bp, oem_cache_6493
oem_cache_6490:
    jmp near mp_memory_ti_read
oem_cache_6493:
    mov bx, dx
oem_cache_6495:
    mov dx, ax
oem_cache_6497:
    shl edx, 0x10
oem_cache_649B:
    mov dx, bx
oem_cache_649D:
    inc dl
oem_cache_649F:
    mov bp, oem_cache_64A5
oem_cache_64A2:
    jmp near mp_memory_ti_read
oem_cache_64A5:
    mov cx, ax
oem_cache_64A7:
    shl ecx, 0x10
oem_cache_64AB:
    inc dl
oem_cache_64AD:
    mov bp, oem_cache_64B3
oem_cache_64B0:
    jmp near mp_memory_ti_read
oem_cache_64B3:
    shl eax, 0x10
oem_cache_64B7:
    xor ax, ax
oem_cache_64B9:
    mov bp, oem_cache_64BF
oem_cache_64BC:
    jmp near mp_memory_ti_write
oem_cache_64BF:
    dec dl
oem_cache_64C1:
    mov bp, oem_cache_64C7
oem_cache_64C4:
    jmp near mp_memory_ti_write
oem_cache_64C7:
    mov ax, 0x3000
oem_cache_64CA:
    mov es, ax
oem_cache_64CC:
    xor di, di
oem_cache_64CE:
    mov cx, 0x4000
oem_cache_64D1:
    mov ax, 0x5555
oem_cache_64D4:
    rep stosw
oem_cache_64D6:
    shr eax, 0x10
oem_cache_64DA:
    dec dl
oem_cache_64DC:
    mov bp, oem_cache_64E2
oem_cache_64DF:
    jmp near mp_memory_ti_write
oem_cache_64E2:
    shl eax, 0x10
oem_cache_64E6:
    shr ecx, 0x10
oem_cache_64EA:
    mov ax, cx
oem_cache_64EC:
    shl ecx, 0x10
oem_cache_64F0:
    dec dl
oem_cache_64F2:
    mov bp, oem_cache_64F8
oem_cache_64F5:
    jmp near mp_memory_ti_write
oem_cache_64F8:
    xor di, di
oem_cache_64FA:
    mov cx, 0x4000
oem_cache_64FD:
    mov ax, 0xaaaa
oem_cache_6500:
    rep stosw
oem_cache_6502:
    mov cx, 0x4000
oem_cache_6505:
    xor di, di
oem_cache_6507:
    repe scasw
oem_cache_6509:
    je short oem_cache_650E
oem_cache_650B:
    jmp near oem_cache_66AB
oem_cache_650E:
    shr ebx, 0x10
oem_cache_6512:
    mov ax, bx
oem_cache_6514:
    shl ebx, 0x10
oem_cache_6518:
    mov bp, oem_cache_651E
oem_cache_651B:
    jmp near mp_memory_ti_write
oem_cache_651E:
    inc dl
oem_cache_6520:
    mov bx, dx
oem_cache_6522:
    shr edx, 0x10
oem_cache_6526:
    mov ax, dx
oem_cache_6528:
    shl edx, 0x10
oem_cache_652C:
    mov dx, bx
oem_cache_652E:
    mov bp, oem_cache_6534
oem_cache_6531:
    jmp near mp_memory_ti_write
oem_cache_6534:
    mov cx, 0x4000
oem_cache_6537:
    xor di, di
oem_cache_6539:
    mov ax, 0x5555
oem_cache_653C:
    repe scasw
oem_cache_653E:
    je short oem_cache_6543
oem_cache_6540:
    jmp near oem_cache_66AB
oem_cache_6543:
    mov al, 0xe2
oem_cache_6545:
    mov bp, oem_cache_654B
oem_cache_6548:
    jmp near oem_cache_23FC
oem_cache_654B:
    or al, 2
oem_cache_654D:
    mov ah, al
oem_cache_654F:
    mov al, 0xe2
oem_cache_6551:
    mov cx, ax
oem_cache_6553:
    mov bp, oem_cache_6559
oem_cache_6556:
    jmp near oem_cache_2407
oem_cache_6559:
    mov ax, 0x1e0
oem_cache_655C:
    mov bp, oem_cache_6562
oem_cache_655F:
    jmp near oem_cache_2407
oem_cache_6562:
    mov ax, cx
oem_cache_6564:
    and ah, 0xfd
oem_cache_6567:
    mov bp, oem_cache_656D
oem_cache_656A:
    jmp near oem_cache_2407
oem_cache_656D:
    mov cx, 0x4000
oem_cache_6570:
    xor di, di
oem_cache_6572:
    mov ax, 0x5555
oem_cache_6575:
    repe scasw
oem_cache_6577:
    je short oem_cache_657C
oem_cache_6579:
    jmp near oem_cache_66AB
oem_cache_657C:
    shr ecx, 0x10
oem_cache_6580:
    mov ax, cx
oem_cache_6582:
    dec dl
oem_cache_6584:
    shl ecx, 0x10
oem_cache_6588:
    mov bp, oem_cache_658E
oem_cache_658B:
    jmp near mp_memory_ti_write
oem_cache_658E:
    shr eax, 0x10
oem_cache_6592:
    inc dl
oem_cache_6594:
    mov bp, oem_cache_659A
oem_cache_6597:
    jmp near mp_memory_ti_write
oem_cache_659A:
    shl eax, 0x10
oem_cache_659E:
    mov cx, 0x4000
oem_cache_65A1:
    xor di, di
oem_cache_65A3:
    mov ax, 0x5555
oem_cache_65A6:
    repe scasw
oem_cache_65A8:
    je short oem_cache_65AD
oem_cache_65AA:
    jmp near oem_cache_66AB
oem_cache_65AD:
    mov al, 0xe2
oem_cache_65AF:
    mov bp, oem_cache_65B5
oem_cache_65B2:
    jmp near oem_cache_23FC
oem_cache_65B5:
    or al, 2
oem_cache_65B7:
    mov ah, al
oem_cache_65B9:
    mov al, 0xe2
oem_cache_65BB:
    mov cx, ax
oem_cache_65BD:
    mov bp, oem_cache_65C3
oem_cache_65C0:
    jmp near oem_cache_2407
oem_cache_65C3:
    mov ax, 0x1e0
oem_cache_65C6:
    mov bp, oem_cache_65CC
oem_cache_65C9:
    jmp near oem_cache_2407
oem_cache_65CC:
    mov ax, cx
oem_cache_65CE:
    and ah, 0xfd
oem_cache_65D1:
    mov bp, oem_cache_65D7
oem_cache_65D4:
    jmp near oem_cache_2407
oem_cache_65D7:
    mov cx, 0x4000
oem_cache_65DA:
    xor di, di
oem_cache_65DC:
    mov ax, 0xaaaa
oem_cache_65DF:
    repe scasw
oem_cache_65E1:
    je short oem_cache_65E6
oem_cache_65E3:
    jmp near oem_cache_66AB
oem_cache_65E6:
    mov cx, 0x4000
oem_cache_65E9:
    xor di, di
oem_cache_65EB:
    mov ax, 0xaaaa
oem_cache_65EE:
    repe scasw
oem_cache_65F0:
    je short oem_cache_65F5
oem_cache_65F2:
    jmp near oem_cache_66AB
oem_cache_65F5:
    dec dl
oem_cache_65F7:
    shr ebx, 0x10
oem_cache_65FB:
    mov ax, bx
oem_cache_65FD:
    mov bp, oem_cache_6603
oem_cache_6600:
    jmp near mp_memory_ti_write
oem_cache_6603:
    inc dl
oem_cache_6605:
    mov bx, dx
oem_cache_6607:
    shr edx, 0x10
oem_cache_660B:
    mov ax, dx
oem_cache_660D:
    mov dx, bx
oem_cache_660F:
    mov bp, oem_cache_6615
oem_cache_6612:
    jmp near mp_memory_ti_write
oem_cache_6615:
    shr ecx, 0x10
oem_cache_6619:
    mov ax, cx
oem_cache_661B:
    inc dl
oem_cache_661D:
    mov bp, oem_cache_6623
oem_cache_6620:
    jmp near mp_memory_ti_write
oem_cache_6623:
    shr eax, 0x10
oem_cache_6627:
    inc dl
oem_cache_6629:
    mov bp, oem_cache_662F
oem_cache_662C:
    jmp near mp_memory_ti_write
oem_cache_662F:
    mov ax, 0xaaaa
oem_cache_6632:
    xor di, di
oem_cache_6634:
    mov bp, oem_cache_663A
oem_cache_6637:
    jmp near oem_cache_2454
oem_cache_663A:
    jmp short oem_cache_6640
oem_cache_663C:
    nop
oem_cache_663D:
    jmp short oem_cache_66A3
oem_cache_663F:
    nop
oem_cache_6640:
    mov ax, 0xffff
oem_cache_6643:
    mov di, 0x4000
oem_cache_6646:
    mov bp, oem_cache_664C
oem_cache_6649:
    jmp near oem_cache_2454
oem_cache_664C:
    jmp short oem_cache_6652
oem_cache_664E:
    nop
oem_cache_664F:
    jmp short oem_cache_66A3
oem_cache_6651:
    nop
oem_cache_6652:
    mov ax, 0x5555
oem_cache_6655:
    mov di, 0x8000
oem_cache_6658:
    mov bp, oem_cache_665E
oem_cache_665B:
    jmp near oem_cache_2454
oem_cache_665E:
    jmp short oem_cache_6664
oem_cache_6660:
    nop
oem_cache_6661:
    jmp short oem_cache_66A3
oem_cache_6663:
    nop
oem_cache_6664:
    mov al, 0xe2
oem_cache_6666:
    mov bp, oem_cache_666C
oem_cache_6669:
    jmp near oem_cache_23FC
oem_cache_666C:
    or al, 2
oem_cache_666E:
    mov ah, al
oem_cache_6670:
    mov al, 0xe2
oem_cache_6672:
    mov cx, ax
oem_cache_6674:
    mov bp, oem_cache_667A
oem_cache_6677:
    jmp near oem_cache_2407
oem_cache_667A:
    mov ax, 0xe0
oem_cache_667D:
    mov bp, oem_cache_6683
oem_cache_6680:
    jmp near oem_cache_2407
oem_cache_6683:
    mov ax, cx
oem_cache_6685:
    and ah, 0xfd
oem_cache_6688:
    mov bp, oem_cache_668E
oem_cache_668B:
    jmp near oem_cache_2407
oem_cache_668E:
    mov cx, 0x8000
oem_cache_6691:
    xor ax, ax
oem_cache_6693:
    xor di, di
oem_cache_6695:
    rep stosw
oem_cache_6697:
    jmp near mp_cache_pass
oem_cache_669A:
    mov bx, 0x354
oem_cache_669D:
    mov bp, oem_cache_673D
oem_cache_66A0:
    jmp near mp_cache_register_failed
oem_cache_66A3:
    mov bx, 0x35c
oem_cache_66A6:
    mov si, ax
oem_cache_66A8:
    jmp short oem_cache_6708
oem_cache_66AA:
    nop
oem_cache_66AB:
    mov bp, 0x358
oem_cache_66AE:
    mov si, ax
oem_cache_66B0:
    shl esp, 0x10
oem_cache_66B4:
    mov ax, word es:[di - 2]
oem_cache_66B8:
    mov sp, ax
oem_cache_66BA:
    shl ebp, 0x10
oem_cache_66BE:
    mov dl, 0xc
oem_cache_66C0:
    shr ebx, 0x10
oem_cache_66C4:
    mov ax, bx
oem_cache_66C6:
    mov bp, oem_cache_66CC
oem_cache_66C9:
    jmp near mp_memory_ti_write
oem_cache_66CC:
    mov bx, dx
oem_cache_66CE:
    shr edx, 0x10
oem_cache_66D2:
    mov ax, dx
oem_cache_66D4:
    mov dx, bx
oem_cache_66D6:
    inc dl
oem_cache_66D8:
    mov bp, oem_cache_66DE
oem_cache_66DB:
    jmp near mp_memory_ti_write
oem_cache_66DE:
    shr ecx, 0x10
oem_cache_66E2:
    mov ax, cx
oem_cache_66E4:
    inc dl
oem_cache_66E6:
    mov bp, oem_cache_66EC
oem_cache_66E9:
    jmp near mp_memory_ti_write
oem_cache_66EC:
    shr eax, 0x10
oem_cache_66F0:
    inc dl
oem_cache_66F2:
    mov bp, oem_cache_66F8
oem_cache_66F5:
    jmp near mp_memory_ti_write
oem_cache_66F8:
    mov ax, sp
oem_cache_66FA:
    shr esp, 0x10
oem_cache_66FE:
    mov word es:[di - 2], ax
oem_cache_6702:
    shr ebp, 0x10
oem_cache_6706:
    mov bx, bp
oem_cache_6708:
    mov dx, word es:[di - 2]
oem_cache_670C:
    mov al, 0xe2
oem_cache_670E:
    mov bp, oem_cache_6714
oem_cache_6711:
    jmp near oem_cache_23FC
oem_cache_6714:
    or al, 2
oem_cache_6716:
    mov ah, al
oem_cache_6718:
    mov al, 0xe2
oem_cache_671A:
    mov cx, ax
oem_cache_671C:
    mov bp, oem_cache_6722
oem_cache_671F:
    jmp near oem_cache_2407
oem_cache_6722:
    mov ax, 0xe0
oem_cache_6725:
    mov bp, oem_cache_672B
oem_cache_6728:
    jmp near oem_cache_2407
oem_cache_672B:
    mov ax, cx
oem_cache_672D:
    and ah, 0xfd
oem_cache_6730:
    mov bp, oem_cache_6736
oem_cache_6733:
    jmp near oem_cache_2407
oem_cache_6736:
    dec di
oem_cache_6737:
    dec di
oem_cache_6738:
    mov cx, si
oem_cache_673A:
    call mp_cache_data_failed
oem_cache_673D:
    mov si, 1
oem_cache_6740:
    mov bp, oem_cache_6746
oem_cache_6743:
    jmp near mp_cache_register_failed
oem_cache_6746:
    hlt
oem_cache_6747:
    xor ax, ax
oem_cache_6749:
    mov ah, 0x21
oem_cache_674B:
    jmp near mp_cache_return
%include "hardware/cache-policy.inc"
