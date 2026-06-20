# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""heisenberg CLI entry point.

Subcommands (real implementations land in todo 24):
- setup-db
- run
- seed-admin
- update-ide
- backup
- version
"""

from __future__ import annotations

import sys

import click

from . import __version__


@click.group()
@click.version_option(__version__, prog_name="heisenberg")
def main() -> None:
    """Heisenberg launcher CLI."""


@main.command()
def version() -> None:
    """Print the launcher version."""
    click.echo(__version__)


@main.command("setup-db")
def setup_db() -> None:
    """Run alembic upgrade head against $HEISENBERG_DATABASE_URL. (todo 24)"""
    click.echo("setup-db: not yet wired (todo 24)", err=True)
    sys.exit(1)


@main.command("update-ide")
@click.option("--version", "version_", required=True, help="heisenberg-ide release tag, e.g. 0.1.0")
def update_ide(version_: str) -> None:
    """Download + verify + extract the heisenberg-ide bundle. (todo 24)"""
    click.echo(f"update-ide --version {version_}: not yet wired (todo 24)", err=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
