# Update ports after a shared change

This guide is for developers. Port-specific inputs, emulator requirements and validation details belong to the port's developer documentation and `validation.json`.

## Requirements

Use Git, Python, NASM and PowerShell. Run Python with `-B` and PowerShell with `-NoProfile`. Supply the private inputs and installed resources declared by the selected ports. The pipeline does not download them.

## Run the pipeline

From the repository root, list the declared checks without building firmware:

```powershell
python -B tools/update-ports.py --list
```

Run the complete update with:

```powershell
python -B tools/update-ports.py
```

The pipeline selects eligible ports from their declarations. A held port is excluded from routine selection. Its own documentation explains the reason and how its independent development works.

For a focused diagnosis, use `--port` with a port directory name and `--check` with a check ID from the listing. A partial run cannot promote candidates or establish complete validation.

## Understand the result

The pipeline copies current source and required inputs into a disposable workspace. Builds and checks run there, including builders with fixed output paths. The original source, retained inputs and approved images remain in place.

Commands run sequentially, with one emulator at a time. Failed preparation blocks its dependent checks. Independent checks can continue.

Read `.agent/test-results/port-update/current.json` for the current result and retained workspace paths. Each command records its arguments, result and log. A new run replaces the previous current report.

After every required current check passes, the pipeline builds candidates. It records image sizes and programmer checksums, then copies each port's output into that port's `build/review/shared-update/` directory. Use the [candidate policy](repository-layout.md) to complete and name a candidate.

If a check, input, artifact or cleanup operation fails, the pipeline reports failure and retains the workspace for diagnosis. It does not promote a candidate. Software validation does not establish physical electrical margins.

## Maintain declarations

Each port owns preparation, current checks, optional historical checks, required inputs and artifact declarations in `validation.json`. Add a new runnable check there when its source is added. Use `case_sets` for explicit dispatcher cases and `wrapped_tests` only for existing covering commands.

Historical checks keep their original conditions. They do not count as current passes. Use `--historical` only with the original required inputs.

After changing the pipeline or declarations, run `python -B tools/test-port-updates.py`. Detailed port results, guest observations and fixture limitations belong in port developer documents, not this instruction guide.
