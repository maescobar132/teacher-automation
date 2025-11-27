"""Console script for teacher_automation."""

import typer
from rich.console import Console

from teacher_automation import utils

app = typer.Typer()
console = Console()


@app.command()
def main():
    """Console script for teacher_automation."""
    console.print("Replace this message by putting your code into "
               "teacher_automation.cli.main")
    console.print("See Typer documentation at https://typer.tiangolo.com/")
    utils.do_something_useful()


if __name__ == "__main__":
    app()
