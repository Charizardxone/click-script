"""Click Script - Windows image-recognition workflow automation."""

__version__ = "0.1.0"


def main() -> None:
    """Run the desktop application."""
    from click_script.app import main as run_app

    run_app()
