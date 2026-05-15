# wxcc-remove-skill-definition

A command-line Python utility for safely deleting skill definitions from a Webex Contact Center (WxCC) tenant.

Before deleting a skill, the tool:
- **Automatically** removes the skill from any Skill Profiles that reference it
- **Asks for confirmation** before removing it from Queues or flagging it in Flows
- Supports **dry-run** mode to preview changes without touching anything

## Quick start

```bash
# 1. Clone and enter the repo
git clone https://github.com/dwolgast-lab/wxcc-remove-skill-definition.git
cd wxcc-remove-skill-definition

# 2. Create a virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env — set WXCC_ORG_ID and one authentication option

# 4. Run
python main.py --interactive
python main.py --skill "Spanish Language"
python main.py --csv skills_to_delete.csv --dry-run
```

## Authentication options

| Method | Best for | Setup effort |
|--------|----------|--------------|
| **Personal Bearer Token** | One-off / testing | None — token from developer.webex.com |
| **Service App (OAuth2)** | Client / recurring use | ~10 minutes — see [User Guide](docs/USER_GUIDE.md) |

## CSV format

One skill per row. The column can be named `name`, `id`, `skill`, `skill_name`, or `name_or_id`.  
A single-column file with no header also works.

```csv
name
Spanish Language
English Support
abc-123-skill-id
```

## Options

```
--skill NAME_OR_ID    Delete a single skill by name or ID
--csv FILE            Bulk-delete skills from a CSV file
--interactive         Prompt for skills one at a time
--org-id ORG_ID       Override WXCC_ORG_ID from .env
--region REGION       WxCC region (us1 us2 eu1 eu2 anz1 jp1 ca1 in1)
--dry-run             Preview actions without making changes
--env FILE            Use a specific .env file (default: .env)
```

## Documentation

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for full setup, provisioning, and usage instructions.

## Versioning

This project follows [Semantic Versioning](https://semver.org). See [CHANGELOG.md](CHANGELOG.md).

## License

MIT
