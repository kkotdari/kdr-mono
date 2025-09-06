#!/usr/bin/env python3
"""
Parallel Font Processing Script with Profile Support
"""

import sys
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
import tempfile
import yaml
from jinja2 import Template
import time
import argparse
import copy
import traceback
from typing import Dict, List, Tuple, Optional
from multiprocessing import Manager, Queue
import queue
import shutil
from utils.simple_logger import SimpleLogger

# Third-party imports
from fontTools.ttLib import TTFont

def load_yaml(path: Path) -> dict:
    """Load YAML file"""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries"""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result

def load_config_with_extends(config_dir: Path, filename: str, loaded_files: set = None) -> dict:
    """Load config file with extends support"""
    if loaded_files is None:
        loaded_files = set()

    # Prevent circular imports
    if filename in loaded_files:
        print(f"WARNING: Circular reference detected for {filename}")
        return {}

    loaded_files.add(filename)

    file_path = config_dir / filename
    if not file_path.exists():
        return {}

    config = load_yaml(file_path)

    # Handle extends
    if 'extends' in config:
        base_filename = config.pop('extends')
        base_config = load_config_with_extends(config_dir, base_filename, loaded_files)
        config = deep_merge(base_config, config)

    return config

def load_config_with_profile(base_dir: Path, profile: Optional[str] = None) -> dict:
    """Load configuration with optional profile override"""

    # Config directory
    config_dir = base_dir / "configs"

    # Load main config
    main_config_path = config_dir / "config.yaml"
    if not main_config_path.exists():
        print(f"ERROR: config.yaml not found in {config_dir}")
        sys.exit(1)

    main_config = load_yaml(main_config_path)

    # Determine which config files to load
    config_files = main_config.get('configs', {})

    # Apply profile override if specified
    if profile:
        profiles = main_config.get('profiles', {})
        if profile in profiles:
            print(f"Using profile: {profile}")
            profile_configs = profiles[profile]
            config_files.update(profile_configs)
        else:
            print(f"WARNING: Profile '{profile}' not found in config.yaml")

    # Load individual config files with fallback and extends support
    merged_config = {}

    for config_type in ['font', 'build', 'logging']:
        # Try profile-specific file first (if profile given)
        if profile:
            profile_file = f"{config_type}-{profile}.yaml"
            profile_path = config_dir / profile_file
            if profile_path.exists():
                print(f"  Loading: {profile_file}")
                config_data = load_config_with_extends(config_dir, profile_file)
                merged_config = deep_merge(merged_config, config_data)
                continue

        # Try file specified in config
        if config_type in config_files:
            config_file = config_files[config_type]
            config_path = config_dir / config_file
            if config_path.exists():
                print(f"  Loading: {config_file}")
                config_data = load_config_with_extends(config_dir, config_file)
                merged_config = deep_merge(merged_config, config_data)
                continue

        # Fallback to default file
        default_file = f"{config_type}.yaml"
        default_path = config_dir / default_file
        if default_path.exists():
            print(f"  Loading: {default_file} (default)")
            config_data = load_config_with_extends(config_dir, default_file)
            merged_config = deep_merge(merged_config, config_data)
        else:
            print(f"  WARNING: No {config_type} configuration found")

    return merged_config

def save_temp_files(tmpdir_path: Path, base_dir: Path, logger) -> Optional[Path]:
    """Save temporary files to backups folder with timestamp"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = base_dir / "backups" / f"scripts_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy all temporary files
        for item in tmpdir_path.iterdir():
            if item.is_dir():
                shutil.copytree(item, backup_dir / item.name)
            else:
                shutil.copy2(item, backup_dir)

        logger.info(f"Temp files saved to: {backup_dir}")
        return backup_dir
    except Exception as e:
        logger.warning(f"Failed to save temp files: {e}")
        return None

def process_font_file(font_file: Path, logger, half_width: int) -> bool:
    """Apply monospace metadata to font"""
    try:
        if not font_file.exists():
            logger.warning(f"Font file not found: {font_file.name}")
            return False

        font = TTFont(font_file)

        # Set monospace flags
        if 'post' in font:
            if hasattr(font['post'], 'isFixedPitch'):
                font['post'].isFixedPitch = 1

        if 'OS/2' in font:
            os2_table = font['OS/2']
            if hasattr(os2_table, 'panose'):
                os2_table.panose.bProportion = 9
            if hasattr(os2_table, 'xAvgCharWidth'):
                os2_table.xAvgCharWidth = half_width

        font.save(font_file)
        return True
    except Exception as e:
        logger.error(f"Error processing {font_file.name}: {e}")
        return False

def generate_style_scripts(style: str, config: dict, fonts: dict, tmpdir: Path,
                          base_dir: Path) -> Dict[str, Path]:
    """Generate FontForge scripts for style"""
    template_dir = base_dir / "ff_templates"
    style_tmpdir = tmpdir / style
    style_tmpdir.mkdir(parents=True, exist_ok=True)

    output_dir = base_dir / "output" / f"v{config['font']['version']}"
    output_dir.mkdir(parents=True, exist_ok=True)

    style_config = copy.deepcopy(config)
    if 'build' not in style_config:
        style_config['build'] = {}
    style_config['build']['styles'] = style

    languages = config.get('languages', {})

    # Template variables
    template_vars = {
        'tmpdir': str(style_tmpdir).replace('\\', '/'),
        'output_dir': str(output_dir).replace('\\', '/'),
        'fonts': {k: str(v.resolve()).replace('\\', '/') for k, v in fonts.items()},
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'logging': config.get('logging', {}),
        **style_config
    }

    scripts = {}
    templates = []

    # Add templates based on languages
    if languages.get('english', False):
        templates.append(('english', 'en_processing.pe.j2'))
    if languages.get('korean', False):
        templates.append(('korean', 'kr_processing.pe.j2'))
    if languages.get('japanese', False):
        templates.append(('japanese', 'jp_processing.pe.j2'))

    templates.append(('merge', 'final_merge.pe.j2'))

    for script_name, template_file in templates:
        template_path = template_dir / template_file
        if not template_path.exists():
            if script_name == 'japanese':
                continue
        with open(template_path, 'r', encoding='utf-8') as f:
            template = Template(f.read())
        script_content = template.render(**template_vars)
        script_path = style_tmpdir / f"{style}_{script_name}.pe"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        scripts[script_name] = script_path

    return scripts

# In run.py, update run_fontforge_with_queue function:

def run_fontforge_with_queue(script_path: Path, style: str, step_name: str,
                             progress_queue: Optional[Queue] = None,
                             log_queue: Optional[Queue] = None,
                             timeout: int = 300,
                             logger: Optional[SimpleLogger] = None) -> Tuple[bool, str]:
    """Execute FontForge script with progress tracking"""
    try:
        process = subprocess.Popen(
            ["fontforge", "-script", str(script_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )

        full_log = []
        current_phase = "Initializing"
        last_phase_displayed = None

        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line: continue
            full_log.append(line)

            is_progress_msg = line.startswith("PROGRESS:")

            # Log to file (skip progress)
            if log_queue and not is_progress_msg:
                log_queue.put({'style': style, 'step': step_name, 'message': line})
            elif logger and not is_progress_msg:
                logger.file_log(f"[{style}:{step_name}] {line}")

            # Track phase changes
            if line.startswith("PHASE:"):
                current_phase = line.replace("PHASE:", "").strip()

                # Display phase in sequential mode
                if logger and current_phase != last_phase_displayed:
                    if last_phase_displayed and "Processing" in last_phase_displayed:
                        pass  # progress_bar already handled newline

                    logger.info(f"[{step_name}] {current_phase}")
                    last_phase_displayed = current_phase

                if progress_queue:
                    progress_queue.put({
                        'type': 'phase',
                        'style': style,
                        'step': step_name,
                        'phase': current_phase
                    })

            elif line.startswith("PROGRESS:"):
                try:
                    parts = line.split(":")
                    current = int(parts[2])
                    total = int(parts[3])

                    if progress_queue:
                        progress_queue.put({
                            'type': 'progress',
                            'style': style,
                            'step': step_name,
                            'current': current,
                            'total': total,
                            'phase': current_phase
                        })
                    elif logger:
                        logger.progress_bar(
                            current, total,
                            prefix=f"{current_phase}",
                            static_prefix=f"[{step_name}] "
                        )

                        # Track phases with progress bar
                        if current_phase != last_phase_displayed:
                            last_phase_displayed = current_phase
                except (ValueError, IndexError):
                    pass

            elif line.startswith(("STYLE_START:", "STYLE_END:", "GENERATED:")):
                if log_queue:
                    log_queue.put({'style': style, 'step': step_name, 'message': line, 'important': True})
                elif logger:
                    logger.info(f"[{style}:{step_name}] {line}")

            elif line.startswith("ERROR:") or line.startswith("WARNING:"):
                if log_queue:
                    log_queue.put({'style': style, 'step': step_name, 'message': line, 'error': line.startswith("ERROR:")})
                elif logger:
                    # Stop progress if there's an error
                    if line.startswith("ERROR:") and logger.progress_active:
                        logger.stop_progress()

                    level = 'ERROR' if line.startswith("ERROR:") else 'WARNING'
                    if level == 'ERROR':
                        logger.error(f"[{style}:{step_name}] {line}")
                    else:
                        logger.warning(f"[{style}:{step_name}] {line}")

        retcode = process.wait(timeout=timeout)

        # Ensure progress is stopped if still active
        if logger and logger.progress_active:
            logger.stop_progress()

        full_output = "\n".join(full_log)
        return retcode == 0, full_output

    except subprocess.TimeoutExpired:
        process.kill()
        if logger and logger.progress_active:
            logger.stop_progress()
        return False, f"Timeout after {timeout}s"
    except Exception as e:
        if logger and logger.progress_active:
            logger.stop_progress()
        return False, str(e)

def process_single_style(style: str, config: dict, fonts: dict, tmpdir: Path,
                        base_dir: Path, progress_queue: Optional[Queue] = None,
                        log_queue: Optional[Queue] = None,
                        logger: Optional[SimpleLogger] = None) -> Tuple[str, bool, str]:
    """Process single font style"""
    try:
        scripts = generate_style_scripts(style, config, fonts, tmpdir, base_dir)
        steps = []

        if 'english' in scripts:
            steps.append(("English", scripts['english'], 300))
        if 'korean' in scripts:
            steps.append(("Korean", scripts['korean'], 600))
        if 'japanese' in scripts:
            steps.append(("Japanese", scripts['japanese'], 600))
        if 'merge' in scripts:
            steps.append(("Merge", scripts['merge'], 600))

        for name, script_path, timeout in steps:
            if progress_queue:
                progress_queue.put({'type': 'step_start', 'style': style, 'step': name})
            elif logger:
                logger.info(f"Step: {name}")

            if log_queue:
                log_queue.put({'style': style, 'step': name, 'message': f"=== Starting {name} ===", 'important': True})

            success, log = run_fontforge_with_queue(script_path, style, name, progress_queue, log_queue, timeout, logger)

            if not success:
                if progress_queue:
                    progress_queue.put({'type': 'style_error', 'style': style, 'error': f"Step '{name}' failed"})
                if log_queue:
                    log_queue.put({'style': style, 'step': name, 'message': f"=== {name} Failed ===", 'important': True})
                return (style, False, f"Step '{name}' failed:\n{log}")

            if log_queue:
                log_queue.put({'style': style, 'step': name, 'message': f"=== {name} Completed ===", 'important': True})

        if progress_queue:
            progress_queue.put({'type': 'style_complete', 'style': style})
        elif logger:
            logger.success(f"Style {style} completed successfully")

        return (style, True, "Completed successfully")
    except Exception as e:
        if progress_queue:
            progress_queue.put({'type': 'style_error', 'style': style, 'error': str(e)})
        return (style, False, f"An unexpected error occurred: {str(e)}")

def process_log_queue(log_queue: Queue, logger: SimpleLogger, stop_event):
    """Process log messages from queue"""
    while not stop_event.is_set() or not log_queue.empty():
        try:
            msg = log_queue.get(timeout=0.1)
            style = msg.get('style', 'unknown')
            step = msg.get('step', 'unknown')
            message = msg.get('message', '')
            is_error = msg.get('error', False)
            is_important = msg.get('important', False)

            if 'PROGRESS:' in message:
                continue

            if is_error:
                logger.file_log(f"[{style}:{step}] {message}", level='ERROR')
            elif is_important:
                logger.file_log(f"[{style}:{step}] {message}", level='INFO')
            else:
                logger.file_log(f"[{style}:{step}] {message}", level='DEBUG')

        except queue.Empty:
            continue
        except Exception as e:
            logger.file_log(f"[LOG_PROCESSOR] Error: {e}", level='ERROR')

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Parallel Font Processor")
    parser.add_argument("-p", "--profile",
                        help="Configuration profile to use")

    parser.add_argument("-s", "--styles",
                        nargs="+",
                        help="Styles to process (e.g., regular bold italic)")

    parser.add_argument("-w", "--workers",
                        type=int,
                        default=4,
                        help="Number of parallel workers (default: 4)")

    parser.add_argument("-seq", "--sequential",
                        action="store_true",
                        help="Process fonts sequentially instead of parallel")

    args = parser.parse_args()

    base_dir = Path(__file__).parent.resolve()

    # Load configuration with profile
    config = load_config_with_profile(base_dir, args.profile)

    # Initialize logger
    log_config = config.get("logging", {})
    if 'font' in config and 'version' in config['font']:
        log_config['font_version'] = config['font']['version']
    logger = SimpleLogger(**log_config)

    try:
        # Determine styles to process
        styles_to_process = args.styles or config.get("build", {}).get("styles", [])

        if isinstance(styles_to_process, str):
            if styles_to_process == "all":
                styles_to_process = ['regular', 'bold', 'italic', 'bold_italic']
            else:
                styles_to_process = [styles_to_process]
        elif not styles_to_process or "all" in styles_to_process:
            styles_to_process = ['regular', 'bold', 'italic', 'bold_italic']

        if not isinstance(styles_to_process, list):
            styles_to_process = [styles_to_process]

        logger.header("Kdr Mono Font Processor")
        if args.profile:
            logger.info(f"Profile: {args.profile}")
        logger.info(f"Styles: {', '.join(styles_to_process)}")

        source_dir = base_dir / "source"
        languages = config.get('languages', {})

        # Validate fonts
        validation_errors = []

        for style in styles_to_process:
            if languages.get('english', False):
                file = config['source_files']['english'].get(style)
                if not file or not (source_dir / file).exists():
                    validation_errors.append(f"  - English {style}: {file or 'NOT SPECIFIED'}")

            if languages.get('korean', False):
                file = config['source_files']['korean'].get(style)
                if not file or not (source_dir / file).exists():
                    validation_errors.append(f"  - Korean {style}: {file or 'NOT SPECIFIED'}")

            if languages.get('japanese', False):
                file = config['source_files']['japanese'].get(style)
                if not file or not (source_dir / file).exists():
                    validation_errors.append(f"  - Japanese {style}: {file or 'NOT SPECIFIED'}")

        if validation_errors:
            logger.error("FONT VALIDATION FAILED")
            logger.error("Missing required font files:")
            for error in validation_errors:
                logger.error(error)
            return 1

        logger.success("Font validation passed")

        # Load font paths
        fonts = {}

        if languages.get('english', False):
            s_en = config['source_files']['english']
            fonts.update({
                'en_regular': source_dir / s_en.get('regular'),
                'en_bold': source_dir / s_en.get('bold'),
                'en_italic': source_dir / s_en.get('italic'),
                'en_bold_italic': source_dir / s_en.get('bold_italic'),
            })

        if languages.get('korean', False):
            s_kr = config['source_files']['korean']
            fonts.update({
                'kr_regular': source_dir / s_kr.get('regular'),
                'kr_bold': source_dir / s_kr.get('bold'),
                'kr_italic': source_dir / s_kr.get('italic'),
                'kr_bold_italic': source_dir / s_kr.get('bold_italic'),
            })

        if languages.get('japanese', False):
            s_jp = config['source_files']['japanese']
            fonts.update({
                'jp_regular': source_dir / s_jp.get('regular'),
                'jp_bold': source_dir / s_jp.get('bold'),
                'jp_italic': source_dir / s_jp.get('italic'),
                'jp_bold_italic': source_dir / s_jp.get('bold_italic'),
            })

        config['build']['styles'] = styles_to_process

        overall_start = time.time()
        results = []

        logger.stage(1, 3, "FONTFORGE PROCESSING")

        # Check if save_temp_files is enabled
        save_temp = config.get('output', {}).get('save_temp_files', False)

        with tempfile.TemporaryDirectory(prefix="parallel_font_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            if args.sequential or len(styles_to_process) == 1:
                logger.info("Running in sequential mode...")
                for style in styles_to_process:
                    logger.info(f"Processing style: {style}")
                    result = process_single_style(style, config, fonts, tmpdir_path, base_dir,
                                                progress_queue=None, log_queue=None, logger=logger)
                    results.append(result)
                    if not result[1]:
                        logger.error(f"Style {style} failed: {result[2][:200]}")

            else:
                logger.info(f"Running in parallel with {args.workers} workers...")

                manager = Manager()
                progress_queue = manager.Queue()
                log_queue = manager.Queue()

                # Start log thread
                import threading
                stop_log_thread = threading.Event()
                log_thread = threading.Thread(
                    target=process_log_queue,
                    args=(log_queue, logger, stop_log_thread),
                    daemon=True
                )
                log_thread.start()

                logger.start_parallel_progress(styles_to_process, progress_queue)

                with ProcessPoolExecutor(max_workers=args.workers) as executor:
                    futures = {
                        executor.submit(process_single_style, style, config, fonts, tmpdir_path, base_dir, progress_queue, log_queue): style
                        for style in styles_to_process
                    }

                    for future in as_completed(futures):
                        style = futures[future]
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            result = (style, False, f"Worker process crashed: {e}")
                            results.append(result)
                            progress_queue.put({'type': 'style_error', 'style': style, 'error': "Worker crashed"})

                logger.stop_parallel_progress()
                stop_log_thread.set()
                log_thread.join(timeout=2.0)

            # Save temp files if enabled
            if save_temp:
                save_temp_files(tmpdir_path, base_dir, logger)

        logger.stage(2, 3, "POST-PROCESSING")
        version_dir = base_dir / "output" / f"v{config['font']['version']}"

        successful_builds = [res for res in results if res[1]]

        logger.section("Applying monospace metadata")
        if successful_builds:
            fontfamily_short = config['font']['family_short']

            for style, success, _ in successful_builds:
                if not success:
                    continue

                style_filename = {
                    'regular': 'Regular',
                    'bold': 'Bold',
                    'italic': 'Italic',
                    'bold_italic': 'BoldItalic'
                }.get(style, style.capitalize())

                font_file = version_dir / f"{fontfamily_short}-{style_filename}.ttf"

                if font_file.exists():
                    logger.progress(f"Processing {font_file.name}...")
                    if not process_font_file(font_file, logger, config['width']['half_width']):
                        logger.error(f"Failed to apply metadata to {font_file.name}")
                else:
                    logger.warning(f"Font file not found: {font_file.name}")

        logger.stage(3, 3, "SUMMARY")
        logger.summary_table(results, time.time() - overall_start)

        failed_styles = [res for res in results if not res[1]]
        return 0 if not failed_styles else 1

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.debug(traceback.format_exc())
        return 1
    finally:
        logger.close()

if __name__ == "__main__":
    sys.exit(main())