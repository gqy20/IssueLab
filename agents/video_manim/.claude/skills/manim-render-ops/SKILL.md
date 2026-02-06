---
name: manim-render-ops
description: Render manim videos with correct CLI flags, dependency checks, and bounded retry strategy.
---

# Manim Render Ops

Use this skill when moving from script to video output.

## Preflight
1. Confirm runtime dependencies are available (`ffmpeg` required by manim ecosystem).
2. Confirm script path and Scene class exist.
3. Create output folders if missing.

## Render Commands
- Fast validation render:
  - `manim -pql outputs/manim/scene.py MainScene`
- High-quality deliverable render:
  - `manim -pqh outputs/manim/scene.py MainScene`

## Quality Policy
- First run at low quality (`-ql`) for syntax/runtime validation.
- Final deliverable at higher quality (`-qh`) unless issue requires otherwise.
- If render fails, perform targeted fix and retry (max 2 retries).

## Failure Handling
- Capture and summarize the first actionable error.
- Patch only the minimal script region that caused failure.
- Re-run the same command and compare result.
- Stop after retry cap and output reproducible failure details.

## Output Checklist
- Render command used.
- Actual output file path (`.mp4`).
- Retry count and failure summary (if any).

## References
- Installing Manim (dependency context): https://docs.manim.community/en/stable/installation.html
- Installing locally (ffmpeg requirement): https://docs.manim.community/en/stable/installation/uv.html
- CLI output settings and quality flags: https://docs.manim.community/en/stable/tutorials/output_and_config.html
