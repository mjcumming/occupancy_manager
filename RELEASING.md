# Release Process

This document outlines the process for releasing new versions of Occupancy Manager.

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

## Automated Release Process

The release process is automated via GitHub Actions. To create a new release:

### 1. Update CHANGELOG.md

Add your changes to the `[Unreleased]` section in `CHANGELOG.md`:

```markdown
## [Unreleased]

### Added
- New feature description

### Changed
- Changed behavior description

### Fixed
- Bug fix description
```

### 2. Commit and Push Changes

```bash
git add CHANGELOG.md
git commit -m "chore: prepare for release vX.Y.Z"
git push
```

### 3. Create and Push a Tag

Create a tag with the version number (prefixed with `v`):

```bash
git tag v0.1.1
git push origin v0.1.1
```

### 4. GitHub Actions Will Automatically:

1. Extract the version from the tag
2. Update `pyproject.toml` and `src/occupancy_manager/__init__.py` with the version
3. Generate a changelog from git commits since the last tag
4. Run all tests
5. Build the package
6. Publish to PyPI (requires PyPI API token configured in GitHub Secrets)
7. Create a GitHub Release with the changelog

## Manual Release (If Needed)

If you need to release manually:

```bash
# 1. Update version in pyproject.toml and __init__.py
# 2. Build the package
python -m build

# 3. Check the package
twine check dist/*

# 4. Upload to PyPI (requires credentials)
twine upload dist/*
```

## PyPI Configuration

For automated publishing, you need to:

1. Create a PyPI API token at https://pypi.org/manage/account/token/
2. Add it as a GitHub Secret named `PYPI_API_TOKEN` (if using username/password)
3. Or configure trusted publishing in PyPI (recommended for the workflow)

The workflow uses PyPI's trusted publishing feature, which requires:
- Repository must be public or have GitHub Actions enabled
- PyPI project must have the GitHub repository configured for trusted publishing

## Pre-release Checklist

- [ ] All tests pass locally
- [ ] CHANGELOG.md is updated
- [ ] Version numbers are correct
- [ ] Documentation is up to date
- [ ] No breaking changes (or version is MAJOR if there are)

