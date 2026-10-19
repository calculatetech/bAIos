# Public source and private inputs

This repository starts with a source snapshot. It excludes private development history, personal files, local agent configuration, and build output.

The MIT license covers original bAIos source and documentation. It does not grant rights to vendor firmware, manuals, operating systems, or third-party tools. Those inputs are not tracked in Git. Downloadable flash images include retained VGA firmware under its original terms. Supply copies that you have permission to use.

Port documentation records hardware observations and reverse-engineering results. References to local ROMs, disassemblies, PDFs, and historical build results describe private research inputs. Those paths will not exist in a fresh clone. The input manifest records file names, sizes, and hashes without distributing their contents.

## Required ROM inputs

See [private-inputs.json](private-inputs.json) for exact identities. Build scripts retain their input checks.

- PB430: `pb430/reference/pb430-m27c1001.bin`, `pb430/reference/acc386.BIN`, and `pb430/reference/gd542x-141-vga60.rom` for the default build. The `--stock-vga` build does not require the separate VGA60 file.
- Presario 800: `presario-800/reference/COMPAQ_PROLINEA_MT_05-02-94.BIN`, `presario-800/reference/gd5428_1-41.bin`, and `presario-800/reference/baios-presario800-vga141-bus07.bin` for the default build.
- Other hardware and comparison tests require the ROMs and media named in their port documentation. A checksum match identifies an input; it does not grant distribution rights.

Native APM and RTC DOS tests use `BAIOS_DOS_VHD` for the source VHD. The CD boot test accepts `--iso`. Test media must contain the software expected by each test. Tests make disposable copies before changing disk contents.

## Public checks

Run `python -B tools/check-public-source.py` in the public checkout. It checks tracked paths, common credential formats, host-specific paths, Python syntax, and JSON syntax. It also checks that excluded input classes have not entered the index. This publication guard cannot detect every possible secret.

CI also exercises the existing emulator-launch isolation test. CI does not flash hardware or distribute vendor ROMs. Local ROM verification and physical testing remain separate requirements.

Keep original ROMs, extracted firmware, manuals, media, photographs, personal configuration, and logs outside Git. Do not force-add ignored inputs. Never publish the private development history as another branch or tag.

Historical RAM/cache comparison code is retained as original-source fixtures in `m919/tests/baselines/`. PB430 shared-source comparisons use a checked-in hash table. These checks do not require private Git objects. The completed private document-relocation audit is retired from this distribution.
