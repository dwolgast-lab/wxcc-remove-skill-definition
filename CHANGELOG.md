# Changelog

All notable changes to this project are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.2.0] — 2026-05-15

### Added
- CSV report output — every run writes a timestamped `wxcc_report_*.csv` with per-skill
  status, counts of objects updated, and notes (use `--report FILE` to name it explicitly)
- `--report FILE` CLI option to specify a custom report path

### Changed
- Reference discovery now uses the dedicated `/skill/{id}/incoming-references` API instead
  of scanning all skill profiles, queues, and flows — faster and more accurate
- Flow references **block deletion** immediately with a clear message listing which flows
  must be updated in Flow Designer before retrying; no confirmation prompt is shown
- Confirmation prompt now only appears when queue references require modification;
  profile-only and no-reference deletions proceed automatically
- Corrected all WxCC REST API endpoint paths based on live testing:
  - Skills: `/organization/{orgId}/skill`
  - Skill profiles: `/organization/{orgId}/skill-profile` (GET: `?includeSkillDetails=`, PUT: `?skillProfileDTO=`)
  - Queues: `/organization/{orgId}/v2/contact-service-queue`
- Skill profile skill entries now correctly identified under `activeSkills` key
- Queue skill entries now correctly identified under `queueSkillRequirements` key
- Fixed OAuth2 scope names in docs: `cjp:config_read` / `cjp:config_write` (underscores)
- Report CSVs and input CSV files excluded from version control via `.gitignore`

---

## [0.1.0] — 2026-05-15

### Added
- Initial release
- Delete skill definitions by name or ID (`--skill`)
- Bulk deletion from a CSV file (`--csv`) with auto-detection of column name
- Interactive prompt mode (`--interactive`)
- Automatic removal of the skill from all referencing Skill Profiles
- Confirmation prompt before removing the skill from Queues or flagging it in Flows
- Dry-run mode (`--dry-run`) to preview changes without any API mutations
- OAuth2 client-credentials authentication for Webex Service Apps (auto-refresh)
- Personal Bearer Token authentication for development / one-off use
- Configurable WxCC region (`--region` or `WXCC_REGION` env var)
- Configurable org ID (`--org-id` or `WXCC_ORG_ID` env var)
- Pagination support for large tenants
- Exponential back-off on HTTP 429 rate-limit responses
- Rich terminal output: colour-coded tables, progress status, confirmation prompts
- `docs/USER_GUIDE.md` covering full provisioning and usage

[Unreleased]: https://github.com/dwolgast-lab/wxcc-remove-skill-definition/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/dwolgast-lab/wxcc-remove-skill-definition/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dwolgast-lab/wxcc-remove-skill-definition/releases/tag/v0.1.0
