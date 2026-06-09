# Releases

## GitHub Direct Install

`main` is the stable direct-install source for Predict Anything.

## Release Tags

Create release tags on stable collection releases so direct-install users have a fixed pin target.

## OpenCode Version Pinning

OpenCode can pin a release tag, branch, or other git ref with:

```json
{
  "plugin": ["abel@git+https://github.com/Abel-ai-lab/PredictAnything.git#v1.4.2"]
}
```

## ClawHub Publication

Build the ClawHub bundle artifact from collection source into `dist/clawhub/abel`,
then publish it with `clawhub package publish`. Do not commit generated release
artifacts.

For step-by-step maintainer build commands, see [developer-builds.md](developer-builds.md).

## Manual Publish

```bash
python3 scripts/build_clawhub_release.py
python3 scripts/publish_clawhub_release.py
```

## GitHub Actions Publish

The `publish-clawhub.yml` workflow supports manual dispatch and tag-triggered publication.
