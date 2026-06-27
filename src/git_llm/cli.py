"""Typer CLI: `gitllm <command>`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from git_llm import db as db_mod
from git_llm import extract as extract_mod
from git_llm import ingest as ingest_mod
from git_llm import label as label_mod
from git_llm import phases as phases_mod
from git_llm import search as search_mod

app = typer.Typer(
    help="Capture, label, search, and extract knowledge from LLM chat histories.",
    no_args_is_help=True,
)
console = Console()


def _db_option() -> typer.Option:
    return typer.Option(None, "--db", help="Path to SQLite DB (default: ~/.git-llm/chatdb.sqlite).")


@app.command()
def init(db: Path = typer.Option(None, "--db")) -> None:
    """Create the database and schema."""
    with db_mod.session(db) as conn:
        db_mod.init_schema(conn)
    console.print(f"[green]✓[/] Initialized DB at {db or db_mod.DEFAULT_DB_PATH}")


@app.command()
def ingest(
    path: Path = typer.Argument(..., exists=True, readable=True),
    title: str = typer.Option(None, "--title", help="Chat title (defaults to filename)."),
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Ingest a chat export (.jsonl preferred, .json or .md also accepted)."""
    with db_mod.session(db) as conn:
        chat_id = ingest_mod.ingest_file(conn, path, title=title)
        n = conn.execute("SELECT COUNT(*) AS n FROM turns WHERE chat_id = ?", (chat_id,)).fetchone()["n"]
    console.print(f"[green]✓[/] Ingested chat_id={chat_id} ({n} turns) from {path}")


@app.command()
def label(
    chat_id: int = typer.Argument(...),
    model: str = typer.Option(
        "stub", "--model", help="'stub' for offline heuristic; otherwise a LiteLLM model id (e.g. gpt-4o-mini)."
    ),
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Label every turn in a chat."""
    labeler: label_mod.Labeler
    if model == "stub":
        labeler = label_mod.StubLabeler()
    else:
        labeler = label_mod.LLMLabeler(model=model)
    with db_mod.session(db) as conn:
        n = label_mod.label_chat(conn, chat_id, labeler)
    console.print(f"[green]✓[/] Wrote {n} labels for chat {chat_id} using {labeler.name}")


@app.command(name="search")
def search_cmd(
    text: str = typer.Option(None, "--text", help="FTS5 query (e.g. 'sqlalchemy AND pool')."),
    label: str = typer.Option(None, "--label"),
    master_class: str = typer.Option(None, "--class", help="Expositive|Exercitive|Verdictive|Commissive|Behabitive"),
    chat_id: int = typer.Option(None, "--chat"),
    limit: int = typer.Option(20, "--limit"),
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Search turns across all chats."""
    with db_mod.session(db) as conn:
        hits = search_mod.search(
            conn,
            text=text,
            label=label,
            master_class=master_class,
            chat_id=chat_id,
            limit=limit,
        )

    if not hits:
        console.print("[yellow]No hits.[/]")
        return

    table = Table(show_lines=False, header_style="bold")
    table.add_column("chat", justify="right")
    table.add_column("turn", justify="right")
    table.add_column("role")
    table.add_column("labels", style="cyan")
    table.add_column("snippet", overflow="fold")
    for h in hits:
        table.add_row(
            f"{h.chat_id} {h.chat_title[:24]}",
            str(h.turn_idx),
            h.role,
            ", ".join(h.labels),
            h.snippet.replace("\n", " "),
        )
    console.print(table)


@app.command()
def phases(
    chat_id: int = typer.Argument(...),
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Show macro-phase compression for a chat."""
    with db_mod.session(db) as conn:
        ps = phases_mod.compute_phases(conn, chat_id)
    if not ps:
        console.print("[yellow]No phases — did you label this chat?[/]")
        return
    table = Table(title=f"Chat {chat_id} — Macro Phases", header_style="bold")
    table.add_column("turns")
    table.add_column("state", style="magenta")
    table.add_column("flow")
    table.add_column("dominant labels", style="cyan")
    for p in ps:
        table.add_row(
            f"{p.turn_start}-{p.turn_end}",
            p.state,
            " → ".join(c.value for c in p.flow),
            ", ".join(p.dominant_labels),
        )
    console.print(table)


@app.command()
def extract(
    chat_id: int = typer.Argument(...),
    out: Path = typer.Option(Path("./zettel"), "--out", help="Output directory for Zettelkasten notes."),
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Extract Zettelkasten notes + ADRs from a labeled chat."""
    with db_mod.session(db) as conn:
        arts = extract_mod.extract_all(conn, chat_id, out)
    console.print(f"[green]✓[/] Wrote {len(arts)} artifacts to {out}")
    for art in arts:
        console.print(f"  [{art.kind}] {art.file_path}")


@app.command(name="import-pi")
def import_pi(
    path: Path = typer.Argument(
        None, help="Single pi session JSONL file. Omit when using --all."
    ),
    bulk: bool = typer.Option(
        False, "--all", help="Bulk-import every session under --sessions-dir."
    ),
    sessions_dir: Path = typer.Option(
        None,
        "--sessions-dir",
        help="Pi sessions root (default: ~/.pi/agent/sessions).",
    ),
    repo: str = typer.Option(
        None,
        "--repo",
        help="Comma-separated repo name patterns (substring or glob). Bulk only.",
    ),
    since: str = typer.Option(None, "--since", help="YYYY-MM-DD (inclusive). Bulk only."),
    until: str = typer.Option(None, "--until", help="YYYY-MM-DD (inclusive). Bulk only."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Discover and report; do not write to DB."
    ),
    title: str = typer.Option(None, "--title", help="Single-file only."),
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Import pi.dev agent session(s). Use a path for one, --all for bulk."""
    if bulk and path is not None:
        raise typer.BadParameter("Provide either <path> OR --all, not both.")
    if not bulk and path is None:
        raise typer.BadParameter("Provide a <path> or use --all.")

    if path is not None:
        if not path.exists():
            raise typer.BadParameter(f"File not found: {path}")
        with db_mod.session(db) as conn:
            chat_id = ingest_mod.ingest_file(conn, path, title=title)
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM turns WHERE chat_id = ?", (chat_id,)
            ).fetchone()["n"]
        console.print(f"[green]✓[/] Imported pi session chat_id={chat_id} ({n} turns)")
        return

    # --- bulk path -----------------------------------------------------------
    from git_llm import pi_bulk

    sessions_root = sessions_dir or pi_bulk.DEFAULT_SESSIONS_DIR
    patterns = [p for p in (repo or "").split(",") if p.strip()] or None

    with db_mod.session(db) as conn:
        result = pi_bulk.bulk_import(
            conn,
            sessions_root,
            repo_patterns=patterns,
            since=since,
            until=until,
            dry_run=dry_run,
        )

    table = Table(title=f"pi bulk import — {sessions_root}", header_style="bold")
    table.add_column("metric")
    table.add_column("count", justify="right", style="cyan")
    table.add_row("discovered", str(result.discovered))
    table.add_row("imported", str(result.imported))
    table.add_row("skipped (dedup)", str(result.skipped_dedup))
    table.add_row("failed", str(result.failed))
    console.print(table)
    if result.failures:
        for p, err in result.failures[:10]:
            console.print(f"  [red]✗[/] {p}: {err}")
    if dry_run:
        console.print("[yellow]dry-run: nothing was written.[/]")


@app.command()
def convert(
    src: Path = typer.Argument(..., exists=True, readable=True, help="Markdown chat dump."),
    out: Path = typer.Argument(..., help="Destination .jsonl file."),
) -> None:
    """Convert a fragile markdown chat dump into canonical JSONL."""
    from git_llm.ingest import md_to_jsonl

    md = src.read_text(encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md_to_jsonl(md), encoding="utf-8")
    n = sum(1 for _ in out.read_text().splitlines() if _.strip())
    console.print(f"[green]✓[/] Wrote {n} turns to {out}")


@app.command(name="export-pi")
def export_pi(
    src: Path = typer.Argument(..., exists=True, readable=True, help="pi.dev session JSONL file."),
    out: Path = typer.Argument(..., help="Destination .json file (canonical envelope)."),
) -> None:
    """Export a pi.dev session to canonical ChatExport JSON."""
    from git_llm.export import write_json
    from git_llm.pi_import import parse_pi_file

    export = parse_pi_file(src)
    result = write_json(export, out)
    console.print(
        f"[green]✓[/] Exported {len(export.messages)} turns from "
        f"'{export.title}' to {result}"
    )


``@app.command()
def export(
    chat_id: int = typer.Argument(...),
    out: Path = typer.Argument(..., help="Destination .jsonl file."),
    db: Path = typer.Option(None, "--db"),
) -> None:
    """Export a stored chat as canonical JSONL (the round-tripable exchange format)."""
    with db_mod.session(db) as conn:
        chat, turns = ingest_mod.fetch_turns_with_meta(conn, chat_id)
    if not turns:
        console.print("[yellow]Chat has no turns.[/]")
        return
    from git_llm.schema import TurnExport

    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for t in turns:
        te = TurnExport(
            role=t.role.value,
            content=t.content,
            parent_id=t.parent_id,
        )
        lines.append(te.model_dump_json(exclude_none=True))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]✓[/] Exported chat {chat_id} ({len(turns)} turns) → {out}")


@app.command()
def chats(db: Path = typer.Option(None, "--db")) -> None:
    """List ingested chats."""
    with db_mod.session(db) as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.created_at, "
            "(SELECT COUNT(*) FROM turns t WHERE t.chat_id=c.id) AS n_turns "
            "FROM chats c ORDER BY c.id"
        ).fetchall()
    if not rows:
        console.print("[yellow]No chats yet. Use `gitllm ingest <file>`.[/]")
        return
    table = Table(header_style="bold")
    for col in ("id", "title", "turns", "created_at"):
        table.add_column(col)
    for r in rows:
        table.add_row(str(r["id"]), r["title"], str(r["n_turns"]), r["created_at"])
    console.print(table)


if __name__ == "__main__":
    app()
