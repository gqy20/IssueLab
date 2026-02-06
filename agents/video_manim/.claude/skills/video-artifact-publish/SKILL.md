---
name: video-artifact-publish
description: Package rendered video outputs as GitHub Actions artifacts and provide traceable links in the final response.
---

# Video Artifact Publish

Use this skill after successful render.

## Goal
Make outputs downloadable and traceable from workflow run links.

## Workflow
1. Collect artifacts:
- `outputs/manim/**`
- `media/videos/**`
2. Upload with `actions/upload-artifact@v4` and explicit retention days.
3. Include run URL and artifact name in final issue comment.
4. Add evidence/source URLs used for script content.

## Traceability Rules
- Final answer must include:
- workflow run URL
- artifact name
- video file relative path
- source links used for factual content
- uncertainty statement (if assumptions remain)

## Output Template
- Run: `https://github.com/<owner>/<repo>/actions/runs/<run_id>`
- Artifact: `<artifact_name>`
- Video: `<relative_path>.mp4`
- Sources:
  - `<url_1>`
  - `<url_2>`

## References
- GitHub Docs: Store and share workflow data as artifacts: https://docs.github.com/actions/using-workflows/storing-workflow-data-as-artifacts
- upload-artifact action (v4): https://github.com/actions/upload-artifact
