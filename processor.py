"""Core skill-deletion logic: find references, confirm, clean up, delete."""

import csv
import json
from datetime import datetime

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from client import WxCCClient, WxCCAPIError

console = Console()


# ---------------------------------------------------------------------------
# Helpers for normalising the varied shapes WxCC uses for skill references
# ---------------------------------------------------------------------------

def _skill_id_from_detail(detail: dict) -> str:
    """Extract skill definition ID from a skillsDetails / skills entry."""
    if "skillId" in detail:
        return detail["skillId"]
    if "skillDefinition" in detail:
        sd = detail["skillDefinition"]
        return sd.get("id", "") if isinstance(sd, dict) else str(sd)
    return ""


def _skills_key(obj: dict) -> str:
    """Return whichever key this object uses to store skill entries."""
    for k in ("activeSkills", "queueSkillRequirements", "skillsDetails", "skills", "skillRequirements"):
        if k in obj:
            return k
    return "activeSkills"


def _ref_type(ref: dict) -> str:
    """Extract a normalised type string from an incoming-reference entry."""
    raw = (
        ref.get("_entity_type")
        or ref.get("type")
        or ref.get("entityType")
        or ref.get("refType")
        or ""
    )
    return raw.upper().replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

class SkillDeletionProcessor:
    def __init__(self, client: WxCCClient, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run
        self.results: list[dict] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process(self, skill_identifier: str) -> bool:
        """Resolve, check references, confirm, clean up, and delete one skill.

        Returns True on success (or successful dry-run), False on abort/not-found.
        """
        result: dict = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "input": skill_identifier,
            "skill_name": "",
            "skill_id": "",
            "status": "",
            "profiles_updated": 0,
            "queues_updated": 0,
            "flows_flagged": 0,
            "notes": "",
        }

        console.rule(f"[bold]{skill_identifier}")

        with console.status("Resolving skill definition..."):
            skill = self.client.find_skill(skill_identifier)

        if not skill:
            console.print(f"[red]Not found:[/red] {skill_identifier!r}")
            result["status"] = "NOT_FOUND"
            self.results.append(result)
            return False

        skill_id: str = skill["id"]
        skill_name: str = skill.get("name", skill_id)
        result["skill_name"] = skill_name
        result["skill_id"] = skill_id
        console.print(
            f"[green]Found:[/green] {skill_name}  "
            f"[dim]ID={skill_id}  type={skill.get('type', '?')}[/dim]"
        )

        # Discover all references via the incoming-references endpoint
        with console.status("Scanning for references..."):
            profiles, queues, flows = self._find_all_refs(skill_id)

        result["flows_flagged"] = len(flows)
        self._print_summary(profiles, queues, flows)

        # Flows block deletion — the WxCC API will reject the delete while a flow
        # still references the skill. Tell the user to fix them first and stop.
        if flows:
            flow_names = [f.get("name", f.get("id", "?")) for f in flows]
            console.print(
                "\n[bold red]Cannot delete[/bold red] — this skill is referenced by "
                f"{len(flows)} flow(s). Remove the skill from the following flow(s) in "
                "WxCC Flow Designer, then run this tool again:\n"
                + "".join(f"  • {n}\n" for n in flow_names)
            )
            result["status"] = "BLOCKED_BY_FLOW"
            result["notes"] = "Remove skill from flows first: " + ", ".join(flow_names)
            self.results.append(result)
            return False

        if self.dry_run:
            console.print("[dim]DRY RUN — no changes made.[/dim]")
            result["status"] = "DRY_RUN"
            parts = []
            if profiles:
                parts.append(f"{len(profiles)} profile(s) would be updated")
            if queues:
                parts.append(f"{len(queues)} queue(s) affected")
            result["notes"] = "; ".join(parts) if parts else "No references found"
            self.results.append(result)
            return True

        # Decide confirmation strategy (no flows at this point)
        if not self._get_approval(skill_name, profiles, queues):
            console.print("[yellow]Aborted.[/yellow]")
            result["status"] = "ABORTED"
            self.results.append(result)
            return False

        # 1. Auto-remove from skill profiles
        for profile in profiles:
            if self._remove_from_profile(profile, skill_id):
                result["profiles_updated"] += 1

        # 2. Remove direct skill references from queues
        for queue in queues:
            if self._remove_from_queue(queue, skill_id):
                result["queues_updated"] += 1

        # 4. Delete the skill definition itself
        try:
            with console.status(f"Deleting skill definition '{skill_name}'..."):
                self.client.delete_skill_definition(skill_id)
        except WxCCAPIError as exc:
            console.print(f"[red]✗[/red] Delete failed: {exc}")
            result["status"] = "ERROR"
            result["notes"] = (result["notes"] + "; " if result["notes"] else "") + str(exc)
            self.results.append(result)
            return False

        console.print(f"\n[bold green]✓[/bold green] Deleted skill: [bold]{skill_name}[/bold]")
        result["status"] = "SUCCESS"
        self.results.append(result)
        return True

    # ------------------------------------------------------------------
    # Reference discovery
    # ------------------------------------------------------------------

    def _find_all_refs(self, skill_id: str) -> tuple[list[dict], list[dict], list[dict]]:
        """Call incoming-references and split into profiles / queues / flows."""
        profiles, queues, flows = [], [], []
        for ref in self.client.get_skill_references(skill_id):
            t = _ref_type(ref)
            if "PROFILE" in t:
                profiles.append(ref)
            elif "QUEUE" in t or "CONTACT_SERVICE" in t:
                queues.append(ref)
            elif "FLOW" in t:
                flows.append(ref)
        return profiles, queues, flows

    # ------------------------------------------------------------------
    # Console output
    # ------------------------------------------------------------------

    def _print_summary(self, profiles: list, queues: list, flows: list):
        if not profiles and not queues and not flows:
            console.print("[dim]No references found.[/dim]")
            return

        if profiles:
            tbl = Table(title="Skill Profiles  [dim](auto-removed)[/dim]", style="cyan")
            tbl.add_column("Name")
            tbl.add_column("ID", style="dim")
            for p in profiles:
                tbl.add_row(p.get("name", "—"), p.get("id", "—"))
            console.print(tbl)

        if queues:
            tbl = Table(title="Queues  [dim](confirmation required)[/dim]", style="yellow")
            tbl.add_column("Name")
            tbl.add_column("ID", style="dim")
            for q in queues:
                tbl.add_row(q.get("name", "—"), q.get("id", "—"))
            console.print(tbl)

        if flows:
            tbl = Table(title="Flows  [dim](blocks deletion — must be removed first)[/dim]", style="red")
            tbl.add_column("Name")
            tbl.add_column("ID", style="dim")
            for f in flows:
                tbl.add_row(f.get("name", "—"), f.get("id", "—"))
            console.print(tbl)

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def _get_approval(self, skill_name: str, profiles: list, queues: list) -> bool:
        if self.dry_run:
            return True

        if queues:
            console.print(
                "\n[bold yellow]Warning:[/bold yellow] Proceeding will:\n"
                + (f"  • Remove this skill from [bold]{len(profiles)}[/bold] skill profile(s)\n" if profiles else "")
                + f"  • Remove this skill from [bold]{len(queues)}[/bold] queue(s)\n"
                + f"  • Permanently delete skill definition [bold]{skill_name!r}[/bold]"
            )
            return Confirm.ask("Proceed?", default=False)

        return True

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def _remove_from_profile(self, profile: dict, skill_id: str) -> bool:
        pid = profile["id"]
        try:
            fresh = self.client.get_skill_profile(pid)
            key = _skills_key(fresh)
            original_count = len(fresh.get(key, []))
            fresh[key] = [
                d for d in fresh.get(key, []) if _skill_id_from_detail(d) != skill_id
            ]
            removed = original_count - len(fresh[key])
            self.client.update_skill_profile(pid, fresh)
            console.print(
                f"  [green]✓[/green] Skill profile [bold]{fresh.get('name', pid)}[/bold]"
                f" — removed {removed} entry"
            )
            return True
        except WxCCAPIError as exc:
            console.print(f"  [red]✗[/red] Could not update profile {pid}: {exc}")
            return False

    def _remove_from_queue(self, queue: dict, skill_id: str) -> bool:
        qid = queue["id"]
        try:
            fresh = self.client.get_queue(qid)
            key = _skills_key(fresh)
            if key in fresh:
                original_count = len(fresh[key])
                fresh[key] = [
                    d for d in fresh[key] if _skill_id_from_detail(d) != skill_id
                ]
                removed = original_count - len(fresh[key])
                self.client.update_queue(qid, fresh)
                console.print(
                    f"  [green]✓[/green] Queue [bold]{fresh.get('name', qid)}[/bold]"
                    f" — removed {removed} direct skill entry"
                )
            return True
        except WxCCAPIError as exc:
            console.print(f"  [red]✗[/red] Could not update queue {qid}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def write_report(self, path: str) -> None:
        if not self.results:
            return
        fieldnames = [
            "timestamp", "input", "skill_name", "skill_id", "status",
            "profiles_updated", "queues_updated", "flows_flagged", "notes",
        ]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.results)
        console.print(f"\n[dim]Report saved → {path}[/dim]")
