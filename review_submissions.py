#!/usr/bin/env python3
"""
Sequential review of submissions and their feedback.

Opens pairs of files (input submission + generated feedback) for manual review.
Press Enter to move to the next student, 'q' to quit.

Usage:
    python review_submissions.py --input ~/Downloads/a_pdf --feedback outputs_pdf/FI08/unidad_1/actividad_1.1

Requirements for side-by-side:
    sudo apt install wmctrl
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def get_monitors() -> list[dict]:
    """Get list of monitors with their dimensions and positions."""
    monitors = []

    try:
        import re
        result = subprocess.run(
            ["xrandr", "--current"],
            capture_output=True,
            text=True,
        )

        for line in result.stdout.split("\n"):
            if " connected" in line:
                # Format: "HDMI-1 connected 1536x864+1536+0"
                # or: "eDP-1 connected primary 1536x864+0+0"
                match = re.search(r"(\S+) connected.*?(\d+)x(\d+)\+(\d+)\+(\d+)", line)
                if match:
                    monitors.append({
                        "name": match.group(1),
                        "width": int(match.group(2)),
                        "height": int(match.group(3)),
                        "x": int(match.group(4)),
                        "y": int(match.group(5)),
                        "primary": "primary" in line,
                    })

    except Exception:
        pass

    # Sort by x position (leftmost first)
    monitors.sort(key=lambda m: m["x"])

    # Fallback if no monitors detected
    if not monitors:
        monitors = [{"name": "default", "width": 1920, "height": 1080, "x": 0, "y": 0, "primary": True}]

    return monitors


def get_screen_dimensions() -> tuple[int, int]:
    """Get screen width and height (total across all monitors)."""
    monitors = get_monitors()
    if monitors:
        # Return dimensions of primary monitor
        for m in monitors:
            if m["primary"]:
                return m["width"], m["height"]
        return monitors[0]["width"], monitors[0]["height"]

    return 1920, 1080


def position_window_left(window_title: str, width: int, height: int):
    """Position a window on the left half of the screen."""
    try:
        # Wait for window to appear
        time.sleep(0.5)

        # Find window by title (partial match)
        subprocess.run(
            ["wmctrl", "-r", window_title, "-e", f"0,0,0,{width//2},{height}"],
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # wmctrl not installed
    except Exception:
        pass


def position_window_right(window_title: str, width: int, height: int):
    """Position a window on the right half of the screen."""
    try:
        # Wait for window to appear
        time.sleep(0.3)

        # Find window by title (partial match)
        subprocess.run(
            ["wmctrl", "-r", window_title, "-e", f"0,{width//2},0,{width//2},{height}"],
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # wmctrl not installed
    except Exception:
        pass


def is_wayland() -> bool:
    """Check if running on Wayland."""
    import os
    return os.environ.get("XDG_SESSION_TYPE") == "wayland"


def position_windows_side_by_side(left_file: Path, right_file: Path, monitor: int = 2, debug: bool = False):
    """
    Position two windows side by side using wmctrl (X11) or print instructions (Wayland).

    Args:
        left_file: File to show on left half
        right_file: File to show on right half
        monitor: Which monitor to use (1 = primary, 2 = secondary)
        debug: If True, print debug information
    """
    # Check for Wayland - wmctrl doesn't work there
    if is_wayland():
        if debug:
            print("  DEBUG: Wayland detected - wmctrl cannot position windows")
        print("  Tip: Use Super+Left / Super+Right to tile windows")
        return

    try:
        monitors = get_monitors()

        if debug:
            print(f"  DEBUG: Detected {len(monitors)} monitors: {monitors}")

        # Select target monitor (0-indexed internally, 1-indexed for user)
        monitor_idx = min(monitor - 1, len(monitors) - 1)
        target = monitors[monitor_idx]

        mon_x = target["x"]
        mon_y = target["y"]
        mon_width = target["width"]
        mon_height = target["height"] - 80  # Leave space for taskbar

        if debug:
            print(f"  DEBUG: Target monitor {monitor}: x={mon_x}, y={mon_y}, w={mon_width}, h={mon_height}")

        # Poll for PDF windows to appear (they take time to launch)
        pdf_windows = []
        max_wait = 5.0  # Maximum seconds to wait
        poll_interval = 0.5
        waited = 0

        while waited < max_wait:
            time.sleep(poll_interval)
            waited += poll_interval

            result = subprocess.run(
                ["wmctrl", "-l"],
                capture_output=True,
                text=True,
            )
            windows = result.stdout.strip().split("\n")

            # Find PDF viewer windows
            pdf_windows = []
            for window in windows:
                parts = window.split(None, 3)
                if len(parts) < 4:
                    continue
                window_id = parts[0]
                window_title = parts[3] if len(parts) > 3 else ""

                window_lower = window_title.lower()
                if any(x in window_lower for x in [".pdf", "document viewer", "evince", "okular", "adobe", "pdf"]):
                    pdf_windows.append((window_id, window_title))

            # Need at least 2 PDF windows
            if len(pdf_windows) >= 2:
                break

            if debug:
                print(f"  DEBUG: Waiting for PDF windows... ({waited:.1f}s, found {len(pdf_windows)})")

        if debug:
            print(f"  DEBUG: All windows after waiting {waited:.1f}s:")
            for w in windows:
                print(f"    {w}")
            print(f"  DEBUG: Found {len(pdf_windows)} PDF windows: {[w[1][:50] for w in pdf_windows]}")

        # Position the two most recent PDF windows
        if len(pdf_windows) >= 2:
            left_win = pdf_windows[-2][0]
            right_win = pdf_windows[-1][0]

            # First, remove maximized state from both windows
            subprocess.run(
                ["wmctrl", "-i", "-r", left_win, "-b", "remove,maximized_vert,maximized_horz"],
                capture_output=True,
            )
            subprocess.run(
                ["wmctrl", "-i", "-r", right_win, "-b", "remove,maximized_vert,maximized_horz"],
                capture_output=True,
            )
            time.sleep(0.2)

            # Position left window (input)
            left_cmd = f"0,{mon_x},{mon_y},{mon_width//2},{mon_height}"
            if debug:
                print(f"  DEBUG: Left window {left_win} -> {left_cmd}")
            subprocess.run(
                ["wmctrl", "-i", "-r", left_win, "-e", left_cmd],
                capture_output=True,
            )

            # Position right window (feedback)
            right_cmd = f"0,{mon_x + mon_width//2},{mon_y},{mon_width//2},{mon_height}"
            if debug:
                print(f"  DEBUG: Right window {right_win} -> {right_cmd}")
            subprocess.run(
                ["wmctrl", "-i", "-r", right_win, "-e", right_cmd],
                capture_output=True,
            )

            # Bring both windows to front
            subprocess.run(["wmctrl", "-i", "-a", left_win], capture_output=True)
            subprocess.run(["wmctrl", "-i", "-a", right_win], capture_output=True)

        elif len(pdf_windows) == 1:
            win_id = pdf_windows[0][0]
            subprocess.run(
                ["wmctrl", "-i", "-r", win_id, "-b", "remove,maximized_vert,maximized_horz"],
                capture_output=True,
            )
            subprocess.run(
                ["wmctrl", "-i", "-r", win_id, "-e",
                 f"0,{mon_x},{mon_y},{mon_width},{mon_height}"],
                capture_output=True,
            )
        elif debug:
            print("  DEBUG: No PDF windows found to position")

    except FileNotFoundError:
        print("  Note: Install wmctrl for side-by-side view: sudo apt install wmctrl")
    except Exception as e:
        if debug:
            print(f"  DEBUG: Error positioning windows: {e}")


def find_matching_pairs(input_dir: Path, feedback_dir: Path) -> list[tuple[Path, Path | None]]:
    """
    Find matching pairs of input files and feedback files.

    Matches by student name extracted from the filename.
    """
    # Get all PDFs from input directory
    input_files = sorted(input_dir.glob("*.pdf"))

    # Get all PDFs from feedback directory
    feedback_files = {f.stem.lower(): f for f in feedback_dir.glob("*.pdf")}

    pairs = []
    for input_file in input_files:
        # Try to find matching feedback file
        input_stem = input_file.stem.lower()

        # Try exact match first
        feedback_file = feedback_files.get(input_stem)

        # If no exact match, try partial match (feedback might have shorter name)
        if not feedback_file:
            for fb_stem, fb_path in feedback_files.items():
                if fb_stem in input_stem or input_stem in fb_stem:
                    feedback_file = fb_path
                    break

        pairs.append((input_file, feedback_file))

    return pairs


def open_pdf(file_path: Path) -> subprocess.Popen | None:
    """Open a PDF file with the default viewer."""
    if not file_path.exists():
        return None

    try:
        # Try different PDF viewers
        viewers = ["xdg-open", "evince", "okular", "firefox", "google-chrome"]

        for viewer in viewers:
            try:
                proc = subprocess.Popen(
                    [viewer, str(file_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return proc
            except FileNotFoundError:
                continue

        print(f"  Warning: No PDF viewer found for {file_path.name}")
        return None

    except Exception as e:
        print(f"  Error opening {file_path.name}: {e}")
        return None


def close_process(proc: subprocess.Popen | None):
    """Close a subprocess if it's running."""
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except:
            try:
                proc.kill()
            except:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Review submissions and feedback sequentially",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python review_submissions.py --input ~/Downloads/a_pdf --feedback outputs_pdf/FI08/unidad_1/actividad_1.1
    python review_submissions.py -i ~/Downloads/a_pdf -f outputs_pdf/FI08/unidad_1/actividad_1.1 --start 5
        """
    )

    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Directory with input PDFs (student submissions)",
    )
    parser.add_argument(
        "-f", "--feedback",
        required=True,
        help="Directory with feedback PDFs",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Start from student number N (default: 1)",
    )
    parser.add_argument(
        "--input-only",
        action="store_true",
        help="Only open input files (no feedback)",
    )
    parser.add_argument(
        "--feedback-only",
        action="store_true",
        help="Only open feedback files (no input)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=2,
        help="Which monitor to display on (1=primary, 2=secondary, default: 2)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug information for window positioning",
    )

    args = parser.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    feedback_dir = Path(args.feedback).expanduser().resolve()

    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    if not feedback_dir.exists() and not args.input_only:
        print(f"Error: Feedback directory not found: {feedback_dir}", file=sys.stderr)
        sys.exit(1)

    # Find matching pairs
    pairs = find_matching_pairs(input_dir, feedback_dir)

    if not pairs:
        print("No files found to review.")
        sys.exit(0)

    print("=" * 60)
    print("SEQUENTIAL SUBMISSION REVIEW")
    print("=" * 60)
    print(f"Input directory:    {input_dir}")
    print(f"Feedback directory: {feedback_dir}")
    print(f"Total submissions:  {len(pairs)}")

    if is_wayland():
        print(f"\nNote: Wayland detected - auto window positioning unavailable")
        print(f"  Use Super+Left / Super+Right to tile windows manually")

    print("=" * 60)
    print("\nControls:")
    print("  Enter     - Next student")
    print("  b         - Previous student")
    print("  g <num>   - Go to student number")
    print("  q         - Quit")
    print("=" * 60)

    current_idx = args.start - 1  # Convert to 0-indexed
    input_proc = None
    feedback_proc = None

    try:
        while True:
            # Bounds check
            if current_idx < 0:
                current_idx = 0
            if current_idx >= len(pairs):
                print("\n✓ All submissions reviewed!")
                break

            input_file, feedback_file = pairs[current_idx]

            # Close previous files
            close_process(input_proc)
            close_process(feedback_proc)
            input_proc = None
            feedback_proc = None

            # Display current student
            print(f"\n[{current_idx + 1}/{len(pairs)}] {input_file.stem[:60]}")

            # Open files
            if not args.feedback_only:
                print(f"  📄 Input: {input_file.name}")
                input_proc = open_pdf(input_file)

            if not args.input_only:
                if feedback_file:
                    print(f"  📝 Feedback: {feedback_file.name}")
                    feedback_proc = open_pdf(feedback_file)
                else:
                    print("  ⚠️  No feedback file found")

            # Position windows side by side on target monitor
            if input_proc and feedback_proc and feedback_file:
                position_windows_side_by_side(input_file, feedback_file, monitor=args.monitor, debug=args.debug)

            # Wait for user input
            try:
                user_input = input("\n> ").strip().lower()
            except EOFError:
                break

            if user_input == 'q':
                print("\nExiting...")
                break
            elif user_input == 'b':
                current_idx -= 1
            elif user_input.startswith('g '):
                try:
                    num = int(user_input[2:])
                    current_idx = num - 1
                except ValueError:
                    print("Invalid number. Use: g <number>")
            else:
                # Default: next student
                current_idx += 1

    finally:
        # Cleanup
        close_process(input_proc)
        close_process(feedback_proc)


if __name__ == "__main__":
    main()
