---
name: manim-script-spec
description: Write reproducible manim scripts with clear scene structure, deterministic defaults, and reviewable assumptions.
---

# Manim Script Spec

Use this skill before rendering.

## Goal
Produce a runnable `manim` script that is deterministic, easy to review, and aligned with issue requirements.

## Workflow
1. Extract requirements from Issue/comments: topic, audience, target duration, style, language.
2. Lock assumptions when requirements are missing and list them explicitly.
3. Generate one primary Scene class (default: `MainScene`) with clear phases.
4. Keep script self-contained: stable imports, no hidden network calls, no runtime prompts.
5. Add a short in-file header comment with: objective, duration target, render command.

## Script Rules
- File path default: `outputs/manim/scene.py`.
- Use explicit Scene name and deterministic sequence in `construct()`.
- Prefer simple primitives first (`Text`, `MathTex`, `VGroup`, `Axes`) before custom complexity.
- Keep each visual step concise and bounded in time (`self.wait(...)`).
- Avoid magic numbers where readability is affected; assign key timings/sizes to variables.

## Output Checklist
- Script path exists.
- Scene class name is explicit.
- Command line for rendering is provided.
- Assumptions and known limitations are listed.

## References
- Manim Quickstart: https://docs.manim.community/en/stable/tutorials/quickstart.html
- A first Scene: https://docs.manim.community/en/stable/tutorials/quickstart.html#a-first-scene
- Building blocks (mobjects/animations): https://docs.manim.community/en/stable/tutorials/quickstart.html#building-blocks
