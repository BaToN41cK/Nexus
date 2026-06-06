# Nexus pip Installation Enhancement - Task List

## Required Changes

- [ ] Add package_data to pyproject.toml to include locale files and config templates
- [ ] Create MANIFEST.in to ensure non-Python files are included in sdist
- [ ] Update README.md with proper pip install instructions
- [ ] Verify the entry point works correctly
- [ ] Test pip install in a clean environment
- [ ] Test building wheel and sdist packages
- [ ] Verify package data (locale, config) is included in built packages

## Package Data to Include
- nexus/locale/*.json (translation files)
- config/nexus.yaml (default config template)
- config/.env.example (env template)

## Implementation Steps
1. Update pyproject.toml with package_data
2. Create MANIFEST.in
3. Update README.md with simple install instructions
4. Test the build
5. Test clean install