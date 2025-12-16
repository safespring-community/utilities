#!/usr/bin/env python3
"""CLI entry point for OpenStack migration utilities."""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel

from migration import __version__
from migration.client import connect, validate_connection
from migration.converter import check_qemu_img
from migration.snapshot import migrate_single_snapshot, select_images_interactive
from migration.state import (
    MigrationState,
    clear_state,
    get_remaining_items,
    load_state,
    save_state,
)
from migration.utils import (
    confirm,
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    setup_logging,
)
from migration.volume import migrate_single_volume, select_volumes_interactive

app = typer.Typer(
    name="migrate",
    help="OpenStack migration utilities for Safespring cloud platforms.",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"[bold]migrate[/bold] version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """OpenStack migration utilities for Safespring cloud platforms."""
    pass


@app.command()
def volume(
    source: Annotated[str, typer.Argument(help="Source cloud name from clouds.yaml")],
    dest: Annotated[
        str, typer.Argument(help="Destination cloud name from clouds.yaml")
    ],
    volumes: Annotated[
        Optional[str],
        typer.Option(
            "--volume",
            "-v",
            help="Volume name(s) to migrate (comma-separated for batch)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview actions without executing"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
    insecure: Annotated[
        bool,
        typer.Option("--insecure", help="Disable SSL certificate verification"),
    ] = False,
    log_file: Annotated[
        Optional[Path],
        typer.Option("--log-file", help="Log file path"),
    ] = Path("migration.log"),
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase verbosity"),
    ] = 0,
    resume: Annotated[
        bool,
        typer.Option("--resume", help="Resume from last saved state"),
    ] = False,
    no_cleanup: Annotated[
        bool,
        typer.Option("--no-cleanup", help="Keep temp files on failure"),
    ] = False,
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", help="Working directory for temp files"),
    ] = Path.cwd(),
) -> None:
    """Migrate volumes from source cloud to destination cloud.

    Examples:

        # Interactive selection
        python migrate.py volume v1 v2

        # Migrate specific volumes
        python migrate.py volume v1 v2 --volume my-volume

        # Migrate multiple volumes
        python migrate.py volume v1 v2 --volume "vol1,vol2,vol3"

        # Dry run to preview
        python migrate.py volume v1 v2 --dry-run
    """
    # Setup logging
    setup_logging(log_file, verbose)

    # Show banner
    console.print(
        Panel.fit(
            f"[bold blue]OpenStack Volume Migration[/bold blue]\n"
            f"Source: [cyan]{source}[/cyan] -> Destination: [cyan]{dest}[/cyan]",
            border_style="blue",
        )
    )

    # Check qemu-img
    try:
        check_qemu_img()
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Handle resume
    state: MigrationState | None = None
    if resume:
        state = load_state()
        if state is None:
            print_warning("No saved state found. Starting fresh.")
        elif state.operation != "volume":
            print_error(
                f"Saved state is for '{state.operation}' operation, not 'volume'"
            )
            raise typer.Exit(1)
        elif state.source_cloud != source or state.dest_cloud != dest:
            print_warning(
                f"Saved state is for different clouds "
                f"({state.source_cloud} -> {state.dest_cloud})"
            )
            if not yes and not confirm("Continue with saved state anyway?"):
                raise typer.Exit(0)

    # Connect to clouds
    print_info(f"\nConnecting to source cloud '{source}'...")
    try:
        source_conn = connect(source, verify_ssl=not insecure)
    except Exception as e:
        print_error(f"Failed to connect to source: {e}")
        raise typer.Exit(1)

    print_info(f"Connecting to destination cloud '{dest}'...")
    try:
        dest_conn = connect(dest, verify_ssl=not insecure)
    except Exception as e:
        print_error(f"Failed to connect to destination: {e}")
        raise typer.Exit(1)

    print_success("Connected to both clouds successfully!")

    # Determine volumes to migrate
    if state and resume:
        volumes_to_migrate = get_remaining_items(state)
        if not volumes_to_migrate:
            print_success("All items from previous run completed!")
            clear_state()
            raise typer.Exit(0)
        print_info(f"\nResuming with {len(volumes_to_migrate)} remaining volumes")
    elif volumes:
        volumes_to_migrate = [v.strip() for v in volumes.split(",")]
    else:
        volumes_to_migrate = select_volumes_interactive(source_conn)

    if not volumes_to_migrate:
        print_warning("No volumes selected. Exiting.")
        raise typer.Exit(0)

    # Confirm migration
    print_info(f"\nVolumes to migrate: {', '.join(volumes_to_migrate)}")
    if not dry_run and not yes:
        if not confirm("\nProceed with migration?", default=True):
            raise typer.Exit(0)

    # Create or update state
    if state is None:
        state = MigrationState(
            operation="volume",
            source_cloud=source,
            dest_cloud=dest,
            items_to_migrate=volumes_to_migrate,
        )
        save_state(state)

    # Migrate each volume
    success_count = 0
    fail_count = 0

    for vol_name in volumes_to_migrate:
        if state is not None and vol_name in state.completed_items:
            print_info(f"\nSkipping '{vol_name}' (already completed)")
            continue

        success = migrate_single_volume(
            source_conn,
            dest_conn,
            vol_name,
            state,
            dry_run=dry_run,
            work_dir=work_dir,
        )

        if success:
            success_count += 1
        else:
            fail_count += 1
            if not yes and not confirm("\nContinue with remaining volumes?"):
                break

    # Summary
    console.print("\n" + "=" * 50)
    print_info("Migration Summary:")
    print_success(f"  Successful: {success_count}")
    if fail_count > 0:
        print_error(f"  Failed: {fail_count}")

    # Clean up state if all done
    if fail_count == 0 and not dry_run:
        clear_state()

    if fail_count > 0:
        raise typer.Exit(1)


@app.command()
def snapshot(
    source: Annotated[str, typer.Argument(help="Source cloud name from clouds.yaml")],
    dest: Annotated[
        str, typer.Argument(help="Destination cloud name from clouds.yaml")
    ],
    images: Annotated[
        Optional[str],
        typer.Option(
            "--image",
            "-i",
            help="Image/snapshot name(s) to migrate (comma-separated for batch)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview actions without executing"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
    insecure: Annotated[
        bool,
        typer.Option("--insecure", help="Disable SSL certificate verification"),
    ] = False,
    log_file: Annotated[
        Optional[Path],
        typer.Option("--log-file", help="Log file path"),
    ] = Path("migration.log"),
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase verbosity"),
    ] = 0,
    resume: Annotated[
        bool,
        typer.Option("--resume", help="Resume from last saved state"),
    ] = False,
    no_cleanup: Annotated[
        bool,
        typer.Option("--no-cleanup", help="Keep temp files on failure"),
    ] = False,
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", help="Working directory for temp files"),
    ] = Path.cwd(),
) -> None:
    """Migrate instance snapshots/images from source cloud to destination cloud.

    Examples:

        # Interactive selection
        python migrate.py snapshot v1 v2

        # Migrate specific image
        python migrate.py snapshot v1 v2 --image my-snapshot

        # Migrate multiple images
        python migrate.py snapshot v1 v2 --image "snap1,snap2,snap3"

        # Dry run to preview
        python migrate.py snapshot v1 v2 --dry-run
    """
    # Setup logging
    setup_logging(log_file, verbose)

    # Show banner
    console.print(
        Panel.fit(
            f"[bold blue]OpenStack Snapshot Migration[/bold blue]\n"
            f"Source: [cyan]{source}[/cyan] -> Destination: [cyan]{dest}[/cyan]",
            border_style="blue",
        )
    )

    # Check qemu-img
    try:
        check_qemu_img()
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Handle resume
    state: MigrationState | None = None
    if resume:
        state = load_state()
        if state is None:
            print_warning("No saved state found. Starting fresh.")
        elif state.operation != "snapshot":
            print_error(
                f"Saved state is for '{state.operation}' operation, not 'snapshot'"
            )
            raise typer.Exit(1)
        elif state.source_cloud != source or state.dest_cloud != dest:
            print_warning(
                f"Saved state is for different clouds "
                f"({state.source_cloud} -> {state.dest_cloud})"
            )
            if not yes and not confirm("Continue with saved state anyway?"):
                raise typer.Exit(0)

    # Connect to clouds
    print_info(f"\nConnecting to source cloud '{source}'...")
    try:
        source_conn = connect(source, verify_ssl=not insecure)
    except Exception as e:
        print_error(f"Failed to connect to source: {e}")
        raise typer.Exit(1)

    print_info(f"Connecting to destination cloud '{dest}'...")
    try:
        dest_conn = connect(dest, verify_ssl=not insecure)
    except Exception as e:
        print_error(f"Failed to connect to destination: {e}")
        raise typer.Exit(1)

    print_success("Connected to both clouds successfully!")

    # Determine images to migrate
    if state and resume:
        images_to_migrate = get_remaining_items(state)
        if not images_to_migrate:
            print_success("All items from previous run completed!")
            clear_state()
            raise typer.Exit(0)
        print_info(f"\nResuming with {len(images_to_migrate)} remaining images")
    elif images:
        images_to_migrate = [i.strip() for i in images.split(",")]
    else:
        images_to_migrate = select_images_interactive(source_conn)

    if not images_to_migrate:
        print_warning("No images selected. Exiting.")
        raise typer.Exit(0)

    # Confirm migration
    print_info(f"\nImages to migrate: {', '.join(images_to_migrate)}")
    if not dry_run and not yes:
        if not confirm("\nProceed with migration?", default=True):
            raise typer.Exit(0)

    # Create or update state
    if state is None:
        state = MigrationState(
            operation="snapshot",
            source_cloud=source,
            dest_cloud=dest,
            items_to_migrate=images_to_migrate,
        )
        save_state(state)

    # Migrate each image
    success_count = 0
    fail_count = 0

    for img_name in images_to_migrate:
        if state is not None and img_name in state.completed_items:
            print_info(f"\nSkipping '{img_name}' (already completed)")
            continue

        success = migrate_single_snapshot(
            source_conn,
            dest_conn,
            img_name,
            state,
            dry_run=dry_run,
            work_dir=work_dir,
        )

        if success:
            success_count += 1
        else:
            fail_count += 1
            if not yes and not confirm("\nContinue with remaining images?"):
                break

    # Summary
    console.print("\n" + "=" * 50)
    print_info("Migration Summary:")
    print_success(f"  Successful: {success_count}")
    if fail_count > 0:
        print_error(f"  Failed: {fail_count}")

    # Clean up state if all done
    if fail_count == 0 and not dry_run:
        clear_state()

    if fail_count > 0:
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show current migration state."""
    state = load_state()
    if state is None:
        print_info("No active migration state found.")
        return

    console.print(
        Panel.fit(
            f"[bold]Migration State[/bold]\n\n"
            f"Operation: [cyan]{state.operation}[/cyan]\n"
            f"Source: [cyan]{state.source_cloud}[/cyan]\n"
            f"Destination: [cyan]{state.dest_cloud}[/cyan]\n"
            f"Current item: [yellow]{state.current_item or 'None'}[/yellow]\n"
            f"Current step: [yellow]{state.step.value}[/yellow]\n"
            f"Completed: [green]{len(state.completed_items)}[/green]\n"
            f"Failed: [red]{len(state.failed_items)}[/red]\n"
            f"Remaining: [blue]{len(get_remaining_items(state))}[/blue]\n"
            f"Created: {state.created_at}\n"
            f"Updated: {state.updated_at}",
            border_style="blue",
        )
    )

    if state.completed_items:
        print_success(f"\nCompleted: {', '.join(state.completed_items)}")
    if state.failed_items:
        print_error(f"Failed: {', '.join(state.failed_items)}")
    if state.temp_files:
        print_warning(f"Temp files: {', '.join(state.temp_files)}")


@app.command()
def clean() -> None:
    """Clear saved migration state."""
    state = load_state()
    if state is None:
        print_info("No migration state to clear.")
        return

    if confirm("Clear saved migration state?"):
        clear_state()
        print_success("Migration state cleared.")


if __name__ == "__main__":
    app()
