# wxcc-remove-skill-definition — User Guide

**Version:** 0.1.0  
**Last updated:** 2026-05-15

---

## Table of contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
4. [Authentication setup](#4-authentication-setup)
   - 4A. [Personal Bearer Token (quick / testing)](#4a-personal-bearer-token-quick--testing)
   - 4B. [Service App — OAuth2 (recommended for recurring use)](#4b-service-app--oauth2-recommended-for-recurring-use)
5. [Configuration (.env file)](#5-configuration-env-file)
6. [Running the tool](#6-running-the-tool)
   - 6A. [Delete a single skill](#6a-delete-a-single-skill)
   - 6B. [Bulk delete from CSV](#6b-bulk-delete-from-csv)
   - 6C. [Interactive mode](#6c-interactive-mode)
   - 6D. [Dry-run (preview only)](#6d-dry-run-preview-only)
7. [What the tool does — step by step](#7-what-the-tool-does--step-by-step)
8. [Reference cascade and confirmation rules](#8-reference-cascade-and-confirmation-rules)
9. [CSV file format](#9-csv-file-format)
10. [Command-line options reference](#10-command-line-options-reference)
11. [Troubleshooting](#11-troubleshooting)
12. [Versioning and updating](#12-versioning-and-updating)

---

## 1. Overview

`wxcc-remove-skill-definition` is a command-line Python utility that safely deletes skill definitions from a Webex Contact Center (WxCC) tenant.

Skill definitions cannot be deleted in the WxCC UI while they are still referenced by other objects (skill profiles, queues, flows). This tool automates the cleanup cascade before performing the deletion.

**Key behaviour:**
- Skill Profiles that reference the skill are updated automatically (no confirmation required)
- Queues and Flows that reference the skill require your confirmation before any changes are made
- `--dry-run` mode lets you see exactly what *would* happen without touching anything

---

## 2. Prerequisites

| Requirement | Details |
|-------------|---------|
| Python 3.11 or later | Check with `python --version` or `py --version` (Windows) |
| pip | Included with Python |
| Internet access | Must be able to reach `api.wxcc-us1.cisco.com` and `webexapis.com` |
| WxCC admin access | Your Webex account must have the **Full Administrator** or **Read/Write** role in Control Hub |

---

## 3. Installation

```bash
# Clone the repository
git clone https://github.com/dwolgast-lab/wxcc-remove-skill-definition.git
cd wxcc-remove-skill-definition

# Create and activate a virtual environment (recommended)
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

You only need to do this once. To update to a new version later:

```bash
git pull
pip install -r requirements.txt
```

---

## 4. Authentication setup

The tool supports two authentication methods. **Choose one.**

---

### 4A. Personal Bearer Token (quick / testing)

A personal developer token is the fastest way to get started. It does not require any app registration and works immediately.

**Limitations:** Expires approximately every 12 hours. You must manually regenerate it each time it expires.

**Steps:**

1. Open [https://developer.webex.com](https://developer.webex.com) in your browser.
2. Sign in with the admin Webex account for the target WxCC tenant.
3. Click your profile picture (top-right) → **Copy token**.
4. Paste the token into your `.env` file as `WXCC_BEARER_TOKEN` (see [Section 5](#5-configuration-env-file)).

> **Security note:** Treat this token like a password. Do not share it or commit it to source control.

---

### 4B. Service App — OAuth2 (recommended for recurring use)

A Webex Service App uses the OAuth 2.0 client-credentials grant. Tokens auto-refresh, so the tool can be used repeatedly without manual token renewal. This is the recommended method for client deployments.

#### Step 1 — Create the Service App

1. Open [https://developer.webex.com/my-apps](https://developer.webex.com/my-apps).
2. Sign in with a Webex account. This does **not** need to be the tenant admin — it's the developer account that owns the app definition.
3. Click **Create a New App**.
4. Select **Service App**.
5. Fill in:
   - **Name:** `WxCC Skill Manager` (or any descriptive name)
   - **Description:** Optional, but helpful for auditing
   - **Icon:** Optional
6. Under **Scopes**, select **at minimum**:
   - `cjp:config` — general WxCC configuration access
   - `cjp:config_read` — read WxCC configuration
   - `cjp:config_write` — modify WxCC configuration
7. Click **Add Service App**.
8. On the confirmation page, copy and save:
   - **Client ID**
   - **Client Secret** (shown only once — save it securely)

#### Step 2 — Authorize the Service App in Control Hub

The Service App will not work until a **Full Administrator** of the target WxCC organization authorizes it. This step must be performed by someone with admin rights in that specific org.

1. Sign in to [https://admin.webex.com](https://admin.webex.com) with the org's Full Administrator account.
2. In the left navigation, go to **Apps** → **Service Apps**.  
   *(If you don't see "Service Apps", go to **Apps** → **Connected Apps** and look for the Service Apps tab.)*
3. Click **Authorize Service App**.
4. In the search box, enter the **Client ID** of the app created in Step 1.
5. Select the app from the results.
6. Review the requested scopes (`cjp:config`, `cjp:config_read`, `cjp:config_write`) and click **Authorize**.

> **Note for self-service clients:** If you are setting this up for your own tenant, you can perform both steps above yourself as long as you have both developer.webex.com access and Full Administrator rights in Control Hub.

#### Step 3 — Configure the .env file

Paste the Client ID and Client Secret into your `.env` file (see [Section 5](#5-configuration-env-file)).

---

## 5. Configuration (.env file)

Copy the example file and edit it:

```bash
cp .env.example .env
```

Open `.env` in a text editor. It should look like this:

```dotenv
# WxCC tenant settings
WXCC_ORG_ID=174bc2cb-6f00-48c5-b5ce-f4a93ffec5df
WXCC_REGION=us1

# --- Choose ONE authentication option ---

# Option A: Personal Bearer Token
WXCC_BEARER_TOKEN=MTlm...your-token-here...

# Option B: Service App OAuth2 (leave WXCC_BEARER_TOKEN blank if using this)
WXCC_CLIENT_ID=C1a2b3...
WXCC_CLIENT_SECRET=abc123...
```

**Finding your Org ID:**

- In Control Hub ([admin.webex.com](https://admin.webex.com)), go to **Account** → the org ID is shown at the top of the page, or in the browser URL after `https://admin.webex.com/o/`
- Alternatively: go to **https://developer.webex.com/docs/api/v1/organizations/list-organizations** and run the API call while signed in

**Regions:**

| Region code | Datacenter |
|-------------|-----------|
| `us1` | United States — West |
| `us2` | United States — East |
| `eu1` | Europe — Frankfurt |
| `eu2` | Europe — Amsterdam |
| `anz1` | Australia & New Zealand |
| `jp1` | Japan |
| `ca1` | Canada |
| `in1` | India |

If you are unsure of your region, check with your Cisco partner or look at the WxCC tenant URL in the Webex App or Control Hub.

---

## 6. Running the tool

Make sure your virtual environment is activated first (`source .venv/bin/activate` or `.venv\Scripts\Activate.ps1`).

### 6A. Delete a single skill

```bash
python main.py --skill "Spanish Language"
```

You can use the skill's **display name** (case-insensitive) or its **UUID**:

```bash
python main.py --skill abc-123-skill-uuid
```

### 6B. Bulk delete from CSV

```bash
python main.py --csv skills_to_delete.csv
```

The tool processes each skill in the file sequentially. See [Section 9](#9-csv-file-format) for the expected file format.

### 6C. Interactive mode

```bash
python main.py --interactive
```

You will be prompted to type a skill name or ID one at a time. Type `quit` to exit.

### 6D. Dry-run (preview only)

Add `--dry-run` to any command to see what *would* happen without making any API calls that change data:

```bash
python main.py --skill "Spanish Language" --dry-run
python main.py --csv skills_to_delete.csv --dry-run
```

A dry-run is strongly recommended the first time you use the tool in a new tenant.

---

## 7. What the tool does — step by step

For each skill, the tool follows this sequence:

1. **Resolve the skill** — looks up the skill definition by name or ID using the WxCC API. If not found, the tool reports an error and moves on.

2. **Scan for references** — queries three resource types:
   - Skill Profiles (`/skill-profile`)
   - Queues (`/queue`)
   - Flows (`/flow`)

3. **Display a summary** — shows a colour-coded table of everything that references the skill, categorised by how it will be handled.

4. **Request confirmation** — if Queues or Flows are affected, you are shown a warning and must type `y` to proceed. If only Skill Profiles are affected, a simpler confirmation is shown. You can always answer `n` to abort without any changes.

5. **Remove from Skill Profiles** — the tool fetches each affected Skill Profile, removes the skill entry, and PUTs the updated profile back. This happens automatically without per-profile confirmation.

6. **Remove from Queues** — only queues with a *direct* skill reference are modified (the skill entry is removed from the queue object). Queues that are affected *indirectly* because they use an affected Skill Profile are shown for awareness but do not require a queue-level change.

7. **Flag Flows for manual review** — programmatic modification of WxCC Flow definitions is not supported. If flows are found that reference the skill ID, the tool lists them and asks you to review them manually in WxCC Flow Builder.

8. **Delete the skill definition** — once all references are cleared, the skill definition is deleted.

---

## 8. Reference cascade and confirmation rules

| Object type | How handled |
|-------------|------------|
| **Skill Profiles** | Automatically updated — skill entry removed, no confirmation needed |
| **Queues (direct ref)** | Requires confirmation — queue object updated to remove skill |
| **Queues (via Skill Profile)** | Shown for awareness only — no queue update needed (profile update covers it) |
| **Flows** | Requires confirmation to proceed with deletion — flows listed for manual review in Flow Builder |

---

## 9. CSV file format

The CSV file must have one skill per row. The tool auto-detects the column; you can use any of these header names:

- `name`
- `id`
- `skill`
- `skill_name`
- `name_or_id`

A single-column file with no header also works.

**Example — named column:**

```csv
name
Spanish Language
English Support
Technical Support Tier 2
```

**Example — by UUID:**

```csv
id
abc-123-0000-0000-skill
def-456-0000-0000-skill
```

**Example — mixed names and IDs, no header:**

```csv
Spanish Language
abc-123-0000-0000-skill
English Support
```

Lines where the skill column is empty are skipped. The file should be UTF-8 encoded.

---

## 10. Command-line options reference

```
usage: wxcc_remove_skill [-h] [--version] [--org-id ORG_ID] [--region REGION]
                          [--dry-run] [--env FILE]
                          [--skill NAME_OR_ID | --csv FILE | --interactive]

options:
  -h, --help            Show this help message and exit
  --version             Show program version and exit
  --org-id ORG_ID       WxCC Org ID (overrides WXCC_ORG_ID in .env)
  --region REGION       WxCC datacenter region (overrides WXCC_REGION in .env)
                        Choices: us1 us2 eu1 eu2 anz1 jp1 ca1 in1
  --dry-run             Preview actions without making any API changes
  --env FILE            Path to .env file (default: .env in current directory)

modes (mutually exclusive):
  --skill NAME_OR_ID    Delete a single skill by exact name or ID
  --csv FILE            Bulk-delete skills listed in a CSV file
  --interactive         Prompt for skills one at a time
```

---

## 11. Troubleshooting

### "No authentication configured"

Your `.env` file is missing credentials. Make sure you have set either:
- `WXCC_BEARER_TOKEN`, or
- Both `WXCC_CLIENT_ID` and `WXCC_CLIENT_SECRET`

### "Token refresh failed (401)"

For Service App auth: the Client ID or Secret is wrong, or the app has not been authorized in Control Hub for this org. Repeat [Section 4B, Step 2](#step-2--authorize-the-service-app-in-control-hub).

For personal token: the token has expired. Return to [developer.webex.com](https://developer.webex.com) and copy a fresh token.

### "HTTP 403: Forbidden"

Your account or service app does not have the required WxCC scopes (`cjp:config_read`, `cjp:config_write`). Check the app's scopes in [developer.webex.com/my-apps](https://developer.webex.com/my-apps) and re-authorize in Control Hub.

### "Skill not found: [name]"

The skill name does not match exactly (matching is case-insensitive but otherwise exact). Try using the skill's UUID instead. You can retrieve all skill definitions by running:

```bash
python main.py --interactive
```

and entering an invalid name — the tool will list what it found (or check the WxCC Provisioning UI under **Skills**).

### "HTTP 409: Conflict" when deleting

Another reference still exists that the tool did not find. This can happen if the WxCC API's `/flow` endpoint was unavailable and a flow still references the skill. Review flows manually in WxCC Flow Builder, remove the skill reference, and re-run the tool.

### Tool hangs or times out

Check that your machine can reach `api.wxcc-us1.cisco.com` (or your region's equivalent). Corporate firewalls sometimes block access to Cisco cloud APIs. If you are on a VPN, try with and without it.

---

## 12. Versioning and updating

This project follows [Semantic Versioning](https://semver.org):
- **MAJOR** — breaking changes (incompatible API or behaviour)
- **MINOR** — new features, backward-compatible
- **PATCH** — bug fixes

To update to the latest version:

```bash
git pull
pip install -r requirements.txt
```

Check [CHANGELOG.md](../CHANGELOG.md) for what changed between versions.
