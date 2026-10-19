# Presario 800 build policy

Use `presario-800/build` as the sole active approved build directory. Keep both VGA speeds there as `baios-presario800-vga50.bin` and `baios-presario800-vga60.bin`, with one shared system ROM. Both speeds of a pending candidate belong in one candidate directory. On physical approval, consolidate the pair into the main build directory and remove the pending directory.

Keep current requirements in `presario-800/README.md` and the executable CD boot contract in `presario-800/docs/plans/presario-800-cdboot.md`. Keep one concise CD boot handoff record at `.agent/test-results/presario-800-cdboot.md` until physical testing and final review finish.
