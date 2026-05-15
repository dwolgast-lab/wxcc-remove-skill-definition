# Changelog

All notable changes to this project are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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

[Unreleased]: https://github.com/dwolgast-lab/wxcc-remove-skill-definition/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dwolgast-lab/wxcc-remove-skill-definition/releases/tag/v0.1.0
