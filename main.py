#!/usr/bin/env python3
"""
wxcc-remove-skill-definition  v0.1.0
Safely delete WxCC skill definitions and clean up their references.

Usage:
  python main.py --skill "Spanish Language"
  python main.py --skill abc-123-skill-id --dry-run
  python main.py --csv skills_to_delete.csv
  python main.py --interactive
"""

import argparse
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt

from auth import build_auth
from client import WxCCClient, VALID_REGIONS
from processor import SkillDeletionProcessor

__version__ = "0.1.0"

console = Console()


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wxcc_remove_skill",
        description="Delete WxCC skill definitions and remove all their references.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --skill "Spanish Language"
  %(prog)s --skill abc-123-skill-id
  %(prog)s --csv skills_to_delete.csv
  %(prog)s --interactive
  %(prog)s --skill "Test Skill" --dry-run
  %(prog)s --skill "My Skill" --org-id YOUR_ORG_ID --region eu1
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--org-id",
        metavar="ORG_ID",
        help="WxCC Org ID (overrides WXCC_ORG_ID in .env)",
    )
    parser.add_argument(
        "--region",
        choices=VALID_REGIONS,
        metavar="REGION",
        help=f"WxCC datacenter region (overrides WXCC_REGION; choices: {', '.join(VALID_REGIONS)})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without making any changes",
    )
    parser.add_argument(
        "--env",
        default=".env",
        metavar="FILE",
        help="Path to .env file (default: .env in current directory)",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--skill",
        metavar="NAME_OR_ID",
        help="Delete a single skill by exact name or ID",
    )
    mode.add_argument(
        "--csv",
        metavar="FILE",
        help="Bulk-delete skills listed in a CSV file",
    )
    mode.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for skills one at a time",
    )

    return parser


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(args: argparse.Namespace) -> dict:
    load_dotenv(args.env)
    env = dict(os.environ)

    org_id = (args.org_id or env.get("WXCC_ORG_ID", "")).strip()
    if not org_id:
        console.print(
            "[red]Error:[/red] Org ID not set. "
            "Use [bold]--org-id[/bold] or set [bold]WXCC_ORG_ID[/bold] in your .env file."
        )
        sys.exit(1)

    region = (args.region or env.get("WXCC_REGION", "us1")).strip()
    if region not in VALID_REGIONS:
        console.print(
            f"[red]Error:[/red] Unknown region '{region}'. "
            f"Valid values: {', '.join(VALID_REGIONS)}"
        )
        sys.exit(1)

    return {"org_id": org_id, "region": region, "env": env}


# ---------------------------------------------------------------------------
# Bulk CSV mode
# ---------------------------------------------------------------------------

def process_csv_file(processor: SkillDeletionProcessor, csv_path: str) -> None:
    path = Path(csv_path)
    if not path.exists():
        console.print(f"[red]Error:[/red] CSV file not found: {csv_path}")
        sys.exit(1)

    skills: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = [h.lower().strip() for h in (reader.fieldnames or [])]

        # Detect which column holds the skill name/ID
        col = next(
            (h for h in headers if h in ("name_or_id", "skill_name", "skill", "name", "id")),
            None,
        )
        if col is None and len(headers) == 1:
            col = headers[0]
        if col is None:
            console.print(
                f"[red]CSV Error:[/red] Cannot determine skill column.\n"
                f"Headers found: {headers}\n"
                "Expected a column named: name, id, skill, skill_name, or name_or_id"
            )
            sys.exit(1)

        for row in reader:
            val = {k.lower().strip(): v.strip() for k, v in row.items()}.get(col, "")
            if val:
                skills.append(val)

    if not skills:
        console.print("[yellow]No skills found in CSV file.[/yellow]")
        return

    console.print(f"[bold]Processing {len(skills)} skill(s) from {path.name}[/bold]\n")
    success, failed = 0, 0
    for skill in skills:
        ok = processor.process(skill)
        if ok:
            success += 1
        else:
            failed += 1

    console.rule()
    console.print(
        f"[bold]Summary:[/bold] "
        f"[green]{success} succeeded[/green]  "
        f"[red]{failed} failed / skipped[/red]"
    )


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def interactive_mode(processor: SkillDeletionProcessor) -> None:
    console.print(
        "[bold]Interactive mode[/bold] — enter a skill name or ID, "
        "or [dim]'quit'[/dim] to exit.\n"
    )
    while True:
        try:
            skill = Prompt.ask("Skill name or ID (or 'quit')").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nExiting.")
            break

        if skill.lower() in ("quit", "exit", "q", ""):
            console.print("Goodbye.")
            break

        processor.process(skill)
        console.print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.dry_run:
        console.print("[bold yellow]DRY RUN — no changes will be made[/bold yellow]\n")

    config = load_config(args)

    try:
        auth = build_auth(config["env"])
    except ValueError as exc:
        console.print(f"[red]Auth Error:[/red] {exc}")
        sys.exit(1)

    client = WxCCClient(config["org_id"], auth, config["region"])
    processor = SkillDeletionProcessor(client, dry_run=args.dry_run)

    if args.skill:
        ok = processor.process(args.skill)
        sys.exit(0 if ok else 1)
    elif args.csv:
        process_csv_file(processor, args.csv)
    else:
        interactive_mode(processor)


if __name__ == "__main__":
    main()
