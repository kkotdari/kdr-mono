#!/usr/bin/env python3
"""
Enhanced Simple Logger with Adaptive Terminal Inversion
Simplified version with only inverted progress bars and no indent management
"""

import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from enum import IntEnum, Enum
import threading
import queue
import time

# Rich imports - optional
try:
    from rich.console import Console
    from rich.progress import Progress
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class LogLevel(IntEnum):
    """Log levels"""
    ERROR = 10
    WARNING = 20
    INFO = 30
    SUCCESS = 35
    DEBUG = 40


class ColorScheme(Enum):
    """Color scheme names for easy reference"""
    RED = 'red'
    GREEN = 'green'
    YELLOW = 'yellow'
    BLUE = 'blue'
    GRAY = 'gray'
    CYAN = 'cyan'
    MAGENTA = 'magenta'
    WHITE = 'white'


class ColorConfig:
    """Color configuration with 256-color support and adaptive inversion"""

    # Default 256-color palette
    DEFAULT_256_COLORS = {
        'red': 210,      # Soft red
        'green': 114,    # Soft green
        'yellow': 229,   # Bright light yellow
        'blue': 111,     # Sky blue
        'gray': 252,     # Very light gray
        'cyan': 116,     # Soft cyan
        'magenta': 219,  # Soft magenta
        'white': 255,    # White
    }

    # Basic ANSI effects that work in all terminals
    BASIC_ANSI = {
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m',
        'ITALIC': '\033[3m',
        'UNDERLINE': '\033[4m',
        'INVERT': '\033[7m',      # Swap foreground/background
        'NO_INVERT': '\033[27m',   # Cancel inversion
    }

    def __init__(self, colors_256: Optional[Dict[str, int]] = None):
        """Initialize color configuration"""
        self.colors_256 = self.DEFAULT_256_COLORS.copy()

        # Override with provided colors
        if colors_256:
            for color_name, color_code in colors_256.items():
                if 0 <= color_code <= 255:
                    self.colors_256[color_name] = color_code

        # Generate ANSI codes
        self.generate_ansi_codes()

    def generate_ansi_codes(self):
        """Generate ANSI escape codes from 256-color numbers"""
        self.ANSI = self.BASIC_ANSI.copy()

        # Generate color codes
        for name, code in self.colors_256.items():
            self.ANSI[name.upper()] = f'\033[38;5;{code}m'
            self.ANSI[f'BG_{name.upper()}'] = f'\033[48;5;{code}m'

    def get_ansi(self, color: ColorScheme) -> str:
        """Get ANSI code for a color scheme"""
        return self.ANSI.get(color.value.upper(), '')

    def get_256_code(self, color: ColorScheme) -> int:
        """Get 256-color code number"""
        return self.colors_256.get(color.value, 255)

    def get_adaptive_effect(self, effect_type: str) -> str:
        """Get adaptive effect that works in monochrome

        Args:
            effect_type: Type of effect ('highlight', 'error', 'warning', 'success', 'info')

        Returns:
            ANSI escape sequence for the effect
        """
        effects = {
            'highlight': self.BASIC_ANSI['INVERT'],
            'error': self.BASIC_ANSI['BOLD'] + self.BASIC_ANSI['INVERT'],
            'warning': self.BASIC_ANSI['BOLD'],
            'success': self.BASIC_ANSI['BOLD'],
            'info': self.BASIC_ANSI['DIM'],
            'debug': self.BASIC_ANSI['DIM'],
            'progress': self.BASIC_ANSI['INVERT'],
        }
        return effects.get(effect_type, '')


class SimpleLogger:
    """Simple logger with inverted progress bars and adaptive terminal support"""

    def __init__(self,
                 console_level: str = "INFO",
                 file_level: str = "DEBUG",
                 log_to_file: bool = True,
                 log_dir: Optional[Path] = None,
                 use_colors: bool = True,
                 use_rich: bool = False,
                 colors_256: Optional[Dict[str, int]] = None,
                 font_version: Optional[str] = None,
                 **kwargs):
        """
        Initialize logger

        Args:
            console_level: Minimum level for console output
            file_level: Minimum level for file output
            log_to_file: Whether to log to file
            log_dir: Directory for log files
            use_colors: Whether to use colors in console output
            use_rich: Whether to use Rich for progress display (if available)
            colors_256: Dictionary of 256-color codes for each color name
            font_version: Font version to display in header
        """
        self.console_level = getattr(LogLevel, console_level.upper(), LogLevel.INFO)
        self.file_level = getattr(LogLevel, file_level.upper(), LogLevel.DEBUG)
        self.log_to_file = log_to_file
        self.use_colors = use_colors and sys.stdout.isatty()
        self.use_rich = use_rich and RICH_AVAILABLE
        self.log_file = None
        self.file_lock = threading.Lock()
        self.font_version = font_version or '1.0.0'

        # Initialize color configuration
        self.color_config = ColorConfig(colors_256=colors_256)

        # Rich components for parallel progress
        self.console = None
        self.parallel_progress = {}
        self.live_display = None
        self.progress_thread = None
        self.stop_progress_event = threading.Event()

        if self.use_rich:
            self.console = Console(
                no_color=not self.use_colors,
                force_terminal=True,
                highlight=False,
                soft_wrap=True,
                style="bright"
            )

        if self.log_to_file:
            if log_dir is None:
                log_dir = Path.cwd() / "logs"

            log_dir = Path(log_dir)
            log_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            log_file_path = log_dir / f"build_{timestamp}.log"
            self.log_file = open(log_file_path, 'w', encoding='utf-8')
            self._write_to_file(f"Log started at {timestamp}")
            self._write_to_file("-" * 70)

        self.progress_active = False
        self.log_buffer = []
        self.buffer_lock = threading.Lock()

    # ========== PROGRESS BAR ==========

    def progress_bar(self, current: int, total: int, prefix: str = "", static_prefix: str = ""):
        """Display progress bar with optional static prefix and inverted progress text"""
        if not prefix:
            prefix = "Processing"

        if not self.progress_active:
            self.progress_active = True

        percent = int((current / total) * 100) if total > 0 else 0

        # Create inverted progress text
        progress_text = self._create_inverted_progress(prefix, percent)

        # Combine static prefix (no effect) + progress text (with effect)
        bar_str = f"\r{static_prefix}{progress_text} {percent}% ({current}/{total})"

        sys.stdout.write(bar_str)
        sys.stdout.flush()

        if current >= total:
            print()
            self._flush_log_buffer()
            self.progress_active = False

    def _create_inverted_progress(self, text: str, percent: int) -> str:
        """Create text with terminal inversion progress effect

        Args:
            text: The text to apply progress effect to
            percent: Progress percentage (0-100)

        Returns:
            Text with terminal inversion showing progress
        """
        text_len = len(text)
        filled_chars = int(text_len * percent / 100)

        if filled_chars == 0:
            return text

        # Split text into inverted and normal portions
        inverted_part = text[:filled_chars]
        normal_part = text[filled_chars:]

        # Apply inversion only to filled portion
        result = (
            f"{self.color_config.BASIC_ANSI['INVERT']}"
            f"{inverted_part}"
            f"{self.color_config.BASIC_ANSI['NO_INVERT']}"
            f"{normal_part}"
        )

        return result

    # ========== RICH PARALLEL PROGRESS ==========

    def start_parallel_progress(self, styles: List[str], progress_queue: queue.Queue):
        """Start parallel progress display with inversion effect"""
        if not self.use_rich:
            return

        self.parallel_progress = {
            style: {
                'current': 0,
                'total': 0,
                'phase': 'Initializing',
                'step': '',
                'language': '',
                'complete': False,
                'error': False
            } for style in styles
        }

        # Start progress monitoring thread
        self.stop_progress_event.clear()
        self.progress_thread = threading.Thread(
            target=self._process_progress_queue,
            args=(progress_queue,),
            daemon=True
        )
        self.progress_thread.start()

        # Use Rich's renderable for parallel progress
        self.live_display = Live(
            self._create_rich_progress_display(),
            console=self.console,
            refresh_per_second=20,
            transient=False
        )
        self.live_display.start()

    def _create_rich_progress_display(self):
        """Create a Rich-compatible progress display with inversion"""
        from rich.text import Text

        # Create text content
        content = Text()

        # Header - use only blue color
        content.append("─" * 60 + "\n")
        blue_code = self.color_config.get_256_code(ColorScheme.BLUE)
        content.append("Thread Allocation:\n", style=f"bold color({blue_code})" if self.use_colors else "bold")

        for idx, (style, _) in enumerate(self.parallel_progress.items(), 1):
            content.append(f"  Thread {idx}: ")
            # Use green instead of yellow
            green_code = self.color_config.get_256_code(ColorScheme.GREEN)
            content.append(f"{style}\n", style=f"color({green_code})" if self.use_colors else None)

        content.append("─" * 60 + "\n\n")

        # Progress for each thread
        for idx, (style, info) in enumerate(self.parallel_progress.items(), 1):
            if info['complete']:
                content.append(f"Thread {idx}: ")
                green_code = self.color_config.get_256_code(ColorScheme.GREEN)
                content.append("✓ Complete\n", style=f"color({green_code})" if self.use_colors else "bold")
            elif info['error']:
                error_msg = info['phase'].replace("Error: ", "")
                content.append(f"Thread {idx}: ")
                # Keep red for errors as it's important
                red_code = self.color_config.get_256_code(ColorScheme.RED)
                content.append(f"✗ {error_msg}\n", style=f"color({red_code})" if self.use_colors else "reverse")
            else:
                language = info.get('language', '')
                phase = info['phase']
                current = info['current']
                total = info['total']

                progress_keywords = ['processing']
                show_progress = any(keyword in phase.lower() for keyword in progress_keywords) and total > 0

                if show_progress:
                    percent = int((current / total) * 100)

                    content.append(f"Thread {idx}: [{language}] ")

                    # Create phase text with inversion for progress
                    phase_len = len(phase)
                    filled = int(phase_len * percent / 100)

                    # Use Rich's reverse style for inversion
                    if filled > 0:
                        content.append(phase[:filled], style="reverse")
                    if filled < phase_len:
                        content.append(phase[filled:])

                    # Use blue instead of cyan for percentage
                    blue_code = self.color_config.get_256_code(ColorScheme.BLUE)
                    content.append(f" {percent}% ({current}/{total})\n", style=f"color({blue_code})" if self.use_colors else None)
                else:
                    content.append(f"Thread {idx}: [{language}] {phase}\n")

        return content

    def _process_progress_queue(self, progress_queue: queue.Queue):
        """Process progress updates from queue"""
        while not self.stop_progress_event.is_set():
            try:
                msg = progress_queue.get(timeout=0.1)
                style = msg.get('style')

                if style not in self.parallel_progress:
                    continue

                msg_type = msg.get('type')

                if msg_type == 'step_start':
                    step = msg.get('step', '')
                    self.parallel_progress[style]['step'] = step
                    self.parallel_progress[style]['language'] = step
                    self.parallel_progress[style]['phase'] = f"{msg.get('step', '')}..."

                elif msg_type == 'progress':
                    self.parallel_progress[style]['current'] = msg.get('current', 0)
                    self.parallel_progress[style]['total'] = msg.get('total', 0)
                    if 'phase' in msg:
                        self.parallel_progress[style]['phase'] = msg['phase']

                elif msg_type == 'phase':
                    phase = msg.get('phase', '')
                    if phase:
                        self.parallel_progress[style]['phase'] = phase

                elif msg_type == 'style_complete':
                    self.parallel_progress[style]['complete'] = True
                    self.parallel_progress[style]['phase'] = 'Complete'

                elif msg_type == 'style_error':
                    self.parallel_progress[style]['error'] = True
                    self.parallel_progress[style]['phase'] = f"Error: {msg.get('error', 'Unknown')}"

                # Update display
                if self.live_display:
                    self.live_display.update(self._create_rich_progress_display())

            except queue.Empty:
                continue
            except Exception:
                pass

    def stop_parallel_progress(self):
        """Stop parallel progress display"""
        if self.progress_thread:
            self.stop_progress_event.set()
            self.progress_thread.join(timeout=1.0)

        if self.live_display:
            self.live_display.stop()
            self.live_display = None

    # ========== FILE-ONLY LOGGING ==========

    def file_log(self, message: str, level: str = 'DEBUG'):
        """Log directly to file without console output"""
        if not self.log_to_file:
            return

        # Skip progress-related messages
        if any(keyword in message.upper() for keyword in ['PROGRESS:', 'PROGRESS_BAR', 'PERCENT:', '%']):
            return

        log_level = getattr(LogLevel, level.upper(), LogLevel.DEBUG)
        if log_level > self.file_level:
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        formatted_msg = f"[{timestamp}] [{level}] {message}"

        with self.file_lock:
            self._write_to_file(formatted_msg)

    # ========== LOGGING METHODS ==========

    def _log(self, message: str, prefix: str = "", color_scheme: Optional[ColorScheme] = None,
             level: LogLevel = LogLevel.INFO, effect_type: Optional[str] = None):
        """Internal logging method with color scheme and adaptive effect support"""
        if prefix:
            console_msg = f"{prefix} {message}"
        else:
            console_msg = message

        # File output (always immediate, skip progress messages)
        if self.log_to_file and level <= self.file_level:
            if 'PROGRESS:' not in message.upper():
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                file_msg = f"[{timestamp}] {console_msg}"
                with self.file_lock:
                    self._write_to_file(file_msg)

        # Console output (buffer if progress is active)
        if level <= self.console_level:
            if self.progress_active:
                # Buffer the log during progress
                with self.buffer_lock:
                    if self.use_rich and self.console:
                        # Store Rich-formatted output
                        if self.use_colors and color_scheme:
                            color_code = self.color_config.get_256_code(color_scheme)
                            # Store as lambda to execute later
                            self.log_buffer.append(
                                lambda msg=console_msg, code=color_code:
                                self.console.print(msg, style=f"color({code})", highlight=False)
                            )
                        elif not self.use_colors and effect_type:
                            style_map = {
                                'error': 'reverse bold',
                                'warning': 'bold',
                                'success': 'bold',
                                'info': 'dim',
                                'debug': 'dim',
                            }
                            self.log_buffer.append(
                                lambda msg=console_msg, st=style_map.get(effect_type, None):
                                self.console.print(msg, style=st, highlight=False)
                            )
                        else:
                            self.log_buffer.append(
                                lambda msg=console_msg:
                                self.console.print(msg, highlight=False)
                            )
                    elif self.use_colors and color_scheme:
                        ansi_code = self.color_config.get_ansi(color_scheme)
                        formatted = f"{ansi_code}{console_msg}{self.color_config.ANSI['RESET']}"
                        self.log_buffer.append(formatted)
                    elif not self.use_colors and effect_type:
                        effect = self.color_config.get_adaptive_effect(effect_type)
                        formatted = f"{effect}{console_msg}{self.color_config.BASIC_ANSI['RESET']}"
                        self.log_buffer.append(formatted)
                    else:
                        self.log_buffer.append(console_msg)
            else:
                # Normal immediate output when no progress
                if self.use_rich and self.console:
                    if self.use_colors and color_scheme:
                        color_code = self.color_config.get_256_code(color_scheme)
                        rich_style = f"color({color_code})"
                        self.console.print(console_msg, style=rich_style, highlight=False)
                    elif not self.use_colors and effect_type:
                        style_map = {
                            'error': 'reverse bold',
                            'warning': 'bold',
                            'success': 'bold',
                            'info': 'dim',
                            'debug': 'dim',
                        }
                        self.console.print(console_msg, style=style_map.get(effect_type, None), highlight=False)
                    else:
                        self.console.print(console_msg, highlight=False)
                elif self.use_colors and color_scheme:
                    ansi_code = self.color_config.get_ansi(color_scheme)
                    print(f"{ansi_code}{console_msg}{self.color_config.ANSI['RESET']}")
                elif not self.use_colors and effect_type:
                    effect = self.color_config.get_adaptive_effect(effect_type)
                    print(f"{effect}{console_msg}{self.color_config.BASIC_ANSI['RESET']}")
                else:
                    print(console_msg)

    def _flush_log_buffer(self):
        """Flush all buffered logs to console"""
        with self.buffer_lock:
            for log_entry in self.log_buffer:
                if callable(log_entry):
                    # Execute Rich-formatted output
                    log_entry()
                else:
                    # Plain string output
                    print(log_entry)
            self.log_buffer.clear()

    # Add method to handle progress interruption (e.g., on error)
    def stop_progress(self):
        """Stop progress and flush buffer"""
        if self.progress_active:
            print()  # New line after progress
            self._flush_log_buffer()
            self.progress_active = False

    def debug(self, message: str):
        """Debug message"""
        self._log(message, "[DEBUG]", ColorScheme.GRAY, LogLevel.DEBUG, 'debug')

    def info(self, message: str):
        """Info message"""
        self._log(message, "", None, LogLevel.INFO, 'info')

    def warning(self, message: str):
        """Warning message"""
        self._log(message, "[WARN]", ColorScheme.YELLOW, LogLevel.WARNING, 'warning')

    def error(self, message: str):
        """Error message"""
        self._log(message, "[ERROR]", ColorScheme.RED, LogLevel.ERROR, 'error')

    def success(self, message: str):
        """Success message"""
        self._log(message, "✓", ColorScheme.GREEN, LogLevel.SUCCESS, 'success')

    def progress(self, message: str):
        """Progress message (in blue) - not logged to file"""
        console_msg = message

        if self.use_rich and self.console:
            if self.use_colors:
                color_code = self.color_config.get_256_code(ColorScheme.BLUE)
                self.console.print(console_msg, style=f"color({color_code})", highlight=False)
            else:
                self.console.print(console_msg, style="dim", highlight=False)
        elif self.use_colors:
            ansi_code = self.color_config.get_ansi(ColorScheme.BLUE)
            print(f"{ansi_code}{console_msg}{self.color_config.ANSI['RESET']}")
        else:
            # Use dim effect for progress in monochrome
            effect = self.color_config.BASIC_ANSI['DIM']
            print(f"{effect}{console_msg}{self.color_config.BASIC_ANSI['RESET']}")

    # ========== SPECIAL OUTPUT METHODS ==========

    def header(self, title: str, width: int = 60):
        """Print a header with ASCII art"""
        if title == "Kdr Mono Font Processor":
            # ASCII art with dynamic version
            version = self.font_version
            ascii_art = f"""

    ██    ██      ██           ██    ██
    ██ ██     ██████  █████    ███  ███   █████   ██████    █████
    ██  ██   ██   ██  ██       ██ ██ ██  ██   ██  ██   ██  ██   ██
    ██    ██  ██████  ██       ██    ██   █████   ██   ██   █████
                                                     Version {version}

    줄맞춤 강박에 시달리는 개발자들을 위한 고정폭 폰트 병합 시스템

            """

            if self.use_rich and self.console:
                if self.use_colors:
                    color_code = self.color_config.get_256_code(ColorScheme.GREEN)
                    self.console.print(ascii_art, style=f"color({color_code})", highlight=False)
                else:
                    self.console.print(ascii_art, style="bold", highlight=False)
            else:
                for line in ascii_art.strip().split('\n'):
                    if self.use_colors:
                        ansi_code = self.color_config.get_ansi(ColorScheme.GREEN)
                        print(f"{ansi_code}{line}{self.color_config.ANSI['RESET']}")
                    else:
                        # Use bold for header in monochrome
                        print(f"{self.color_config.BASIC_ANSI['BOLD']}{line}{self.color_config.BASIC_ANSI['RESET']}")
        else:
            # Regular header - use BLUE instead of CYAN
            if self.use_rich and self.console:
                if self.use_colors:
                    color_code = self.color_config.get_256_code(ColorScheme.BLUE)
                    self.console.rule(f"[bold color({color_code})]{title}[/bold color({color_code})]")
                else:
                    self.console.rule(f"[bold]{title}[/bold]")
            else:
                separator = "=" * width
                if not self.use_colors:
                    # Use inverted separator for emphasis
                    effect = self.color_config.BASIC_ANSI['INVERT']
                    print(f"{effect}{separator}{self.color_config.BASIC_ANSI['RESET']}")
                    print(f"{self.color_config.BASIC_ANSI['BOLD']}{title}{self.color_config.BASIC_ANSI['RESET']}")
                    print(f"{effect}{separator}{self.color_config.BASIC_ANSI['RESET']}")
                else:
                    self.info(separator)
                    self.info(title)
                    self.info(separator)

    def stage(self, stage_num: int, total_stages: int, stage_name: str):
        """Print stage header"""
        self.info("")
        stage_text = f"STAGE {stage_num}/{total_stages}: {stage_name}"

        if self.use_rich and self.console:
            if self.use_colors:
                color_code = self.color_config.get_256_code(ColorScheme.CYAN)
                self.console.print(f"[bold color({color_code})]{stage_text}[/bold color({color_code})]")
            else:
                self.console.print(f"[reverse]{stage_text}[/reverse]")
            self.console.print("")
        elif not self.use_colors:
            # Use inverted text for stage headers in monochrome
            effect = self.color_config.BASIC_ANSI['INVERT']
            print(f"{effect}{stage_text}{self.color_config.BASIC_ANSI['RESET']}")
        else:
            self.info(stage_text)

    def section(self, title: str):
        """Print a section header"""
        self.info(title)

    def summary_table(self, results: List[Tuple[str, bool, str]], elapsed_time: float):
        """Print summary table of build results with adaptive display"""
        if not results:
            self.warning("No results to display")
            return

        if self.use_rich and self.console:
            from rich.box import SIMPLE

            cyan_code = self.color_config.get_256_code(ColorScheme.CYAN)
            green_code = self.color_config.get_256_code(ColorScheme.GREEN)
            red_code = self.color_config.get_256_code(ColorScheme.RED)

            if self.use_colors:
                table = Table(show_header=True, box=SIMPLE, title_style="bold", show_edge=False)
                table.add_column("Style", style=f"color({cyan_code})", width=15)
                table.add_column("Status", justify="center", width=10)
                table.add_column("Details", width=40)
            else:
                table = Table(show_header=True, box=SIMPLE, show_edge=False)
                table.add_column("Style", width=15)
                table.add_column("Status", justify="center", width=10)
                table.add_column("Details", width=40)

            self.console.print("\nBUILD SUMMARY", style="bold reverse" if not self.use_colors else "bold")

            for result in results:
                if result and len(result) >= 3:
                    style, success, message = result
                    status = "✓" if success else "✗"
                    if self.use_colors:
                        status_style = f"color({green_code})" if success else f"color({red_code})"
                        status_display = f"[{status_style}]{status}[/{status_style}]"
                    else:
                        status_display = f"[bold]{status}[/bold]" if success else f"[reverse]{status}[/reverse]"

                    if message:
                        details = message.split('\n')[0][:40] if not success else "Success"
                    else:
                        details = "Success" if success else "Failed"
                    table.add_row(
                        style or "Unknown",
                        status_display,
                        details
                    )

            self.console.print(table)
            self.console.print(f"\nTotal time: {elapsed_time:.2f}s")
        else:
            # Non-Rich summary with adaptive effects
            separator = "=" * 60
            if not self.use_colors:
                print(f"\n{self.color_config.BASIC_ANSI['INVERT']}{separator}{self.color_config.BASIC_ANSI['RESET']}")
                print(f"{self.color_config.BASIC_ANSI['BOLD']}BUILD SUMMARY{self.color_config.BASIC_ANSI['RESET']}")
                print(f"{self.color_config.BASIC_ANSI['INVERT']}{separator}{self.color_config.BASIC_ANSI['RESET']}")
            else:
                self.info("\n" + separator)
                self.info("BUILD SUMMARY")
                self.info(separator)

            for result in results:
                if result and len(result) >= 3:
                    style, success, message = result
                    status = "SUCCESS" if success else "FAILED"
                    style_name = style or "Unknown"

                    if self.use_colors:
                        color_scheme = ColorScheme.GREEN if success else ColorScheme.RED
                        self._log(f"{style_name:<15} {status:<10}", "", color_scheme, LogLevel.INFO)
                    else:
                        # Use bold for success, invert for failure in monochrome
                        if success:
                            effect = self.color_config.BASIC_ANSI['BOLD']
                        else:
                            effect = self.color_config.BASIC_ANSI['INVERT']
                        print(f"{effect}{style_name:<15} {status:<10}{self.color_config.BASIC_ANSI['RESET']}")

            self.info(f"\nTotal time: {elapsed_time:.2f}s")

    # ========== FILE OPERATIONS ==========

    def _write_to_file(self, message: str):
        """Write to log file"""
        if self.log_file and not self.log_file.closed:
            self.log_file.write(message + '\n')
            self.log_file.flush()

    def close(self):
        """Close log file and cleanup"""
        self.stop_parallel_progress()

        if self.log_file and not self.log_file.closed:
            self._write_to_file("-" * 70)
            self._write_to_file(f"Log ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.log_file.close()
            self.log_file = None

    def __del__(self):
        """Destructor"""
        try:
            self.close()
        except:
            pass

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# ========== USAGE EXAMPLE ==========

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test adaptive logger")
    parser.add_argument('--no-color', action='store_true', help='Disable colors')
    parser.add_argument('--no-rich', action='store_true', help='Disable Rich library')
    args = parser.parse_args()

    # Simulate loading config
    config = yaml.safe_load("""
    logging:
        console_level: INFO
        file_level: DEBUG
        use_colors: true
        use_rich: true
        colors_256:
            red: 210
            green: 114
            yellow: 229
            blue: 111
            gray: 252
            cyan: 116
            magenta: 219
            white: 255
    """)

    # Extract logging config
    log_config = config.get("logging", {})
    log_config['font_version'] = '1.1.2'

    # Apply command line arguments
    if args.no_color:
        log_config['use_colors'] = False
    if args.no_rich:
        log_config['use_rich'] = False

    # Create logger with all parameters
    with SimpleLogger(**log_config) as logger:

        logger.header("K Mono Font Processor")

        if not log_config['use_colors']:
            logger.info("Running in monochrome mode with adaptive terminal effects!")

        logger.stage(1, 3, "Initialization")
        logger.info("Loading configuration...")
        logger.success("Configuration loaded")

        logger.stage(2, 3, "Processing")
        logger.section("Font Processing")
        logger.debug("Processing font files...")
        logger.warning("Large file detected")

        # Progress bar example with inverted text
        for i in range(101):
            logger.progress_bar(i, 100, prefix="Processing glyphs with character classification")
            time.sleep(0.01)

        logger.stage(3, 3, "Finalization")
        logger.error("Example error message")
        logger.success("Build complete!")

        # Summary
        results = [
            ("regular", True, "Success"),
            ("bold", True, "Success"),
            ("italic", False, "Font file not found"),
        ]
        logger.summary_table(results, 12.34)