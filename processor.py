"""Core skill-deletion logic: find references, confirm, clean up, delete."""

import json

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
    for k in ("skillsDetails", "skills", "skillRequirements"):
        if k in obj:
            return k
    return "skillsDetails"


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

class SkillDeletionProcessor:
    def __init__(self, client: WxCCClient, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process(self, skill_identifier: str) -> bool:
        """Resolve, check references, confirm, clean up, and delete one skill.

        Returns True on success (or successful dry-run), False on abort/not-found.
        """
        console.rule(f"[bold]{skill_identifier}")

        with console.status("Resolving skill definition..."):
            skill = self.client.find_skill(skill_identifier)

        if not skill:
            console.print(f"[red]Not found:[/red] {skill_identifier!r}")
            return False

        skill_id: str = skill["id"]
        skill_name: str = skill.get("name", skill_id)
        console.print(
            f"[green]Found:[/green] {skill_name}  "
            f"[dim]ID={skill_id}  type={skill.get('type', '?')}[/dim]"
        )

        # Discover all references
        with console.status("Scanning for references (skill profiles, queues, flows)..."):
            profiles = self._find_profile_refs(skill_id)
            queues = self._find_queue_refs(skill_id, profiles)
            flows = self._find_flow_refs(skill_id)

        self._print_summary(profiles, queues, flows)

        # Decide confirmation strategy
        if not self._get_approval(skill_name, profiles, queues, flows):
            console.print("[yellow]Aborted.[/yellow]")
            return False

        if self.dry_run:
            console.print("[dim]DRY RUN — no changes made.[/dim]")
            return True

        # 1. Auto-remove from skill profiles
        for profile in profiles:
            self._remove_from_profile(profile, skill_id)

        # 2. Remove direct skill references from queues (indirect queue impacts
        #    are handled by the profile update above)
        for entry in queues:
            if entry["reason"] == "direct":
                self._remove_from_queue(entry["queue"], skill_id)

        # 3. Flows: programmatic modification is out of scope; advise manual review
        if flows:
            console.print(
                "\n[yellow]NOTE:[/yellow] The following flows reference this skill ID. "
                "Please review them manually in WxCC Flow Builder:"
            )
            for flow in flows:
                console.print(f"  • {flow.get('name', flow.get('id', '?'))}")

        # 4. Delete the skill definition itself
        with console.status(f"Deleting skill definition '{skill_name}'..."):
            self.client.delete_skill_definition(skill_id)

        console.print(f"\n[bold green]✓[/bold green] Deleted skill: [bold]{skill_name}[/bold]")
        return True

    # ------------------------------------------------------------------
    # Reference discovery
    # ------------------------------------------------------------------

    def _find_profile_refs(self, skill_id: str) -> list[dict]:
        """Return all skill profiles whose skillsDetails contain skill_id."""
        result = []
        for profile in self.client.get_skill_profiles():
            key = _skills_key(profile)
            for detail in profile.get(key, []):
                if _skill_id_from_detail(detail) == skill_id:
                    result.append(profile)
                    break
        return result

    def _find_queue_refs(self, skill_id: str, affected_profiles: list[dict]) -> list[dict]:
        """Return queues with a direct skill reference OR that use an affected skill profile.

        Each entry is {"queue": <dict>, "reason": "direct" | "via_profile"}.
        The "via_profile" entries are informational — they don't require a queue
        update, but the user should know their routing behaviour will change.
        """
        profile_ids = {p["id"] for p in affected_profiles}
        seen_ids: set[str] = set()
        result = []

        for queue in self.client.get_queues():
            qid = queue.get("id", "")
            if qid in seen_ids:
                continue

            # Direct skill reference on the queue object
            key = _skills_key(queue)
            for detail in queue.get(key, []):
                if _skill_id_from_detail(detail) == skill_id:
                    result.append({"queue": queue, "reason": "direct"})
                    seen_ids.add(qid)
                    break
            else:
                # Indirect: queue's skill profile contains the skill
                q_profile = queue.get("skillProfileId", "")
                if q_profile and q_profile in profile_ids:
                    result.append({"queue": queue, "reason": "via_profile"})
                    seen_ids.add(qid)

        return result

    def _find_flow_refs(self, skill_id: str) -> list[dict]:
        """Search flow definitions (JSON dump) for the skill ID string."""
        result = []
        for flow in self.client.get_flows():
            if skill_id in json.dumps(flow):
                result.append(flow)
        return result

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
            tbl.add_column("Impact")
            for entry in queues:
                q = entry["queue"]
                impact = (
                    "Direct skill reference — will be removed"
                    if entry["reason"] == "direct"
                    else "Uses an affected skill profile — routing will change"
                )
                tbl.add_row(q.get("name", "—"), q.get("id", "—"), impact)
            console.print(tbl)

        if flows:
            tbl = Table(title="Flows  [dim](manual review needed after deletion)[/dim]", style="red")
            tbl.add_column("Name")
            tbl.add_column("ID", style="dim")
            for f in flows:
                tbl.add_row(f.get("name", "—"), f.get("id", "—"))
            console.print(tbl)

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def _get_approval(
        self,
        skill_name: str,
        profiles: list,
        queues: list,
        flows: list,
    ) -> bool:
        if self.dry_run:
            return True

        if queues or flows:
            console.print(
                "\n[bold yellow]Warning:[/bold yellow] Proceeding will:\n"
                + (f"  • Remove this skill from [bold]{len(profiles)}[/bold] skill profile(s)\n" if profiles else "")
                + (f"  • Modify or affect [bold]{len(queues)}[/bold] queue(s)\n" if queues else "")
                + (f"  • Leave [bold]{len(flows)}[/bold] flow(s) requiring manual review\n" if flows else "")
                + f"  • Permanently delete skill definition [bold]{skill_name!r}[/bold]"
            )
            return Confirm.ask("Proceed?", default=False)

        if profiles:
            return Confirm.ask(
                f"Remove from {len(profiles)} skill profile(s) and delete "
                f"[bold]{skill_name!r}[/bold]?",
                default=False,
            )

        # No references at all
        return Confirm.ask(
            f"No references found. Delete skill [bold]{skill_name!r}[/bold]?",
            default=False,
        )

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def _remove_from_profile(self, profile: dict, skill_id: str):
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
        except WxCCAPIError as exc:
            console.print(f"  [red]✗[/red] Could not update profile {pid}: {exc}")

    def _remove_from_queue(self, queue: dict, skill_id: str):
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
        except WxCCAPIError as exc:
            console.print(f"  [red]✗[/red] Could not update queue {qid}: {exc}")
