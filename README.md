# Kdr Mono Font Builder

줄맞춤 강박에 시달리는 개발자들을 위한 한영일 고정폭 폰트 병합 시스템

A sophisticated font build system that combines English, Korean, and Japanese monospace fonts into perfectly aligned multilingual coding fonts.

---

## Key Features

### Multi-Language Font Merging
- **Three-Language Support**: English, Korean, and Japanese font integration
- **Priority System**: English → Korean → Japanese glyph precedence
- **Intelligent Overlap Resolution**: Automatic duplicate glyph removal between languages
- **Perfect Alignment**: 1:2 ratio (half:full width) maintained across all characters

### Advanced Build System
- **Profile System**: Multiple configuration profiles with inheritance support
- **Parallel Processing**: Multi-threaded builds with configurable worker count
- **Real-time Progress**: Terminal-based progress bars with inverted text effect
- **Rich Integration**: Optional Rich library support for enhanced parallel progress display

### Precise Character Control
- **Character Classification System**:
  - `no_center_ranges`: Characters that maintain original positioning (box-drawing, etc.)
  - `no_scale_ranges`: Characters exempt from scaling (symbols, arrows, etc.)
  - `halfwidth_ranges`: Force halfwidth treatment
  - `fullwidth_ranges`: Force fullwidth treatment
- **Language-Specific Adjustments**:
  - Vertical shift control per language
  - Independent X/Y scaling factors
  - Optional overlap removal

### Advanced Logging
- **Adaptive Terminal Support**: Works in both color and monochrome terminals
- **256-Color Palette**: Customizable color schemes
- **Inverted Progress Bars**: Visual progress indication using terminal inversion
- **Multi-Level Logging**: Separate console and file log levels
- **Timestamped Build Logs**: Detailed logs saved in `logs/` directory

---

## Project Structure

```
kdr-mono/
├── configs/              # Modular configuration system
│   ├── config.yaml       # Main config with profile definitions
│   ├── font.yaml         # Font metadata and metrics
│   ├── build.yaml        # Build settings and character rules
│   ├── logging.yaml      # Logging configuration
│   └── font-*.yaml       # Profile-specific overrides
├── ff_templates/         # Jinja2 templates for FontForge scripts
│   ├── en_processing.pe.j2
│   ├── kr_processing.pe.j2
│   ├── jp_processing.pe.j2
│   └── final_merge.pe.j2
├── source/               # Source font files
├── output/               # Generated fonts (versioned)
├── logs/                 # Build logs
├── backups/              # Temporary file backups (optional)
├── utils/                # Utility modules
│   └── simple_logger.py  # Enhanced logging system
└── run.py                # Main build script
```

---

## Quick Start

### Prerequisites

- **Python**: 3.8 or higher
- **FontForge**: With Python scripting support
- **Memory**: 4GB+ recommended for parallel builds

### Installation

```bash
# Clone repository
git clone https://github.com/kkotdari/kdr-mono.git
cd kdr-mono

# Install Python dependencies
pip install -r requirements.txt

# Verify FontForge installation
fontforge --version
```

### Basic Usage

```bash
# Build all styles with default configuration
python run.py

# Build specific styles
python run.py --styles regular bold

# Use a profile (e.g., condensed for narrower width)
python run.py --profile condensed

# Sequential processing (for debugging)
python run.py --sequential

# Custom worker count for parallel builds
python run.py --workers 2
```

### Available Profiles

- `default` - Standard configuration (1024/2048 width)
- `condensed` - Narrower width (1000/2000)
- `small` - Reduced overall size (scaled down x/y)
- `compressed` - Maximum horizontal compression (scaled x only)
- `test` - Quick testing mode

---

## Configuration System

### Important Notes

**Width Settings for Perfect 1:2 Ratio**
To maintain exact 1:2 half-width to full-width ratio across all even font sizes, use `width: 1024/2048`. This is the only configuration that guarantees pixel-perfect rendering at all sizes without rounding errors. Other width values (like 1000/2000) may cause ratio degradation at certain font sizes.

**Scale Factor Limits**
Keep vertical scale factors (`half_width_y`, `full_width_y`) at or below 1.0 to prevent glyph clipping. Values above 1.0 may cause the top or bottom of characters to be cut off, especially for characters with tall ascenders or deep descenders.

### Configuration Files

The build system uses modular YAML configuration files located in `configs/`:

```
configs/
├── config.yaml      # Main config with profile definitions
├── font.yaml        # Font metadata and metrics
├── build.yaml       # Build settings and character rules
├── logging.yaml     # Logging configuration
└── font-*.yaml      # Profile-specific font configs
```

### Key Configuration Options

#### Font Configuration (`font.yaml`)

```yaml
font:
  family: "Kdr Mono"
  version: "1.0.1"
  
# Character dimensions (em units)
width:
  half_width: 1024      # Half-width character width
  full_width: 2048      # Full-width character width (should be 2× half)
  threshold: 1536       # Auto-detection threshold for width classification

# Scaling factors (decimal values, 1.0 = 100%)
scale:
  half_width_x: 0.86    # Horizontal scale for half-width chars
  half_width_y: 0.94    # Vertical scale for half-width chars
  full_width_x: 1.04    # Horizontal scale for full-width chars
  full_width_y: 1.0     # Vertical scale for full-width chars

# Language-specific vertical adjustments
english:
  vertical_shift: 40    # Pixels to shift English glyphs vertically
korean:
  vertical_shift: -16   # Pixels to shift Korean glyphs
  remove_overlaps: true # Remove duplicate glyphs from English
japanese:
  vertical_shift: -8
  remove_overlaps: true # Remove duplicates from English & Korean
```

#### Build Configuration (`build.yaml`)

```yaml
# Language support toggles
languages:
  english: true
  korean: true
  japanese: true

# Build options
build:
  styles: "all"  # Options: "all", "regular", "bold", "italic", "bold_italic", or list
  skip_hinting: false
  skip_kerning_removal: false
  skip_overlap_removal: false

# Character classification for special handling
special_chars:
  # Characters that should not be centered
  no_center_ranges:
    - [0x2500, 0x257F]  # Box Drawing
    - [0x2580, 0x259F]  # Block Elements
  
  # Characters that should not be scaled
  no_scale_ranges:
    - [0x2190, 0x21FF]  # Arrows
    - [0xE0A0, 0xE0D4]  # Powerline symbols
  
  # Force specific width treatment
  halfwidth_ranges:
    - [0x0020, 0x007E]  # Basic ASCII
    - [0xFF61, 0xFF9F]  # Halfwidth Katakana
  
  fullwidth_ranges:
    - [0xFF01, 0xFF5E]  # Fullwidth ASCII variants
```

### Profile System

Profiles allow quick switching between different font configurations. Use with `-p` or `--profile`:

```bash
python run.py --profile condensed
```

### Creating Custom Configurations

#### 1. Copy and modify base config:
```bash
cp configs/font.yaml configs/font-custom.yaml
# Edit font-custom.yaml with your settings
```

#### 2. Use extends for inheritance:
```yaml
# font-custom.yaml
extends: "font.yaml"  # Inherit all settings from base

# Override only what you need
scale:
  half_width_x: 0.82  # Make it narrower
```

#### 3. Add to profile in config.yaml:
```yaml
profiles:
  custom:
    font: "font-custom.yaml"
    build: "build.yaml"
    logging: "logging.yaml"
```

---

## Visual Features

### Adaptive Terminal Display

The logger automatically adapts to your terminal capabilities:

- **Color Terminals**: 256-color palette with customizable schemes
- **Monochrome Terminals**: Uses terminal inversion and bold effects
- **Progress Bars**: Inverted text effect shows real-time progress

### Parallel Build Display

When using Rich library (`use_rich: true`):

```
────────────────────────────────────────────────────────
Thread Allocation:
  Thread 1: regular
  Thread 2: bold
  Thread 3: italic
  Thread 4: bold_italic
────────────────────────────────────────────────────────

Thread 1: [English] ████████Processing glyphs 73% (7300/10000)
Thread 2: [Korean] ██████░░░░░░░░░░Processing 40% (4000/10000)
Thread 3: [English] ✓ Complete
Thread 4: [Japanese] Removing overlaps...
```

---

## Advanced Features

### Temporary File Management

```yaml
output:
  save_temp_files: true  # Save generated scripts for debugging
```

When enabled, temporary FontForge scripts are saved to `backups/scripts_TIMESTAMP/`

### Custom Logging Colors

Configure 256-color codes in `logging.yaml`:

```yaml
logging:
  use_colors: true
  colors_256:
    red: 210      # Soft red for errors
    green: 114    # Soft green for success
    blue: 111     # Sky blue for progress
    gray: 252     # Light gray for debug
```

### Build Process Hooks

The build system includes several hooks for customization:

1. **Pre-processing**: Glyph exclusion before processing
2. **Language-specific**: Custom processing per language
3. **Post-processing**: Monospace metadata application
4. **Validation**: Font integrity checks

---

## Performance Optimization

### Width Configuration Comparison

| Half/Full Width | 1:2 Ratio Accuracy | Best For |
|-----------------|-------------------|----------|
| 1024/2048 | Perfect at all sizes | Mathematical precision |
| 1000/2000 | Perfect at 8-20pt, degrades at 24pt+ | Better spacing for coding |

### Parallel Processing

- **Default**: 4 workers for optimal performance
- **Adjust based on CPU**: `--workers N` where N = CPU cores
- **Memory consideration**: Reduce workers if experiencing memory issues

### Build Time Estimates

| Configuration | Time (approx) |
|--------------|---------------|
| All styles, 4 workers | 2-5 minutes |
| Single style, sequential | 30-60 seconds |
| Test profile | 10-30 seconds |

### Memory Usage

- **Per worker**: ~500MB-1GB
- **Peak usage**: Workers × 1GB + overhead
- **Recommendation**: 4GB+ RAM for 4 workers

---

## Troubleshooting

### Common Issues

#### FontForge Not Found
```bash
# macOS
brew install fontforge

# Ubuntu/Debian
sudo apt-get install fontforge python3-fontforge

# Windows - Add to PATH or use full path
set PATH=%PATH%;C:\Program Files (x86)\FontForgeBuilds\bin
```

#### Memory Issues
```bash
# Reduce parallel workers
python run.py --workers 1

# Use sequential mode
python run.py --sequential
```

#### Character Alignment Problems
1. Verify source fonts are truly monospace
2. Check `width.threshold` setting
3. Review character classification rules
4. Use even font sizes (10pt, 12pt, 14pt)

### Debug Mode

```bash
# Enable debug logging with test profile
python run.py --profile test

# Save temporary files for inspection
# Set in build.yaml:
output:
  save_temp_files: true
```

---

## Build Process

### 1. Font Validation
- Verifies all source font files exist
- Checks for monospace compatibility
- Validates configuration

### 2. Individual Language Processing
- **English**: Base font processing with character classification
- **Korean**: Overlap removal and CJK-specific adjustments
- **Japanese**: Overlap removal with Korean/English precedence

### 3. Font Merging
- Merges processed fonts in priority order
- Sets complete font metadata and licensing information
- Removes kerning and ligature tables for monospace consistency

### 4. Post-Processing
- Applies monospace metadata flags
- Validates generated fonts
- Creates final output in `output/vX.X.X/` directory

---

## Output

Generated fonts are saved in:
```
output/
└── v1.1.8/
    ├── KdrMono-Regular.ttf
    ├── KdrMono-Bold.ttf
    ├── KdrMono-Italic.ttf
    └── KdrMono-BoldItalic.ttf
```

Build logs are saved in:
```
logs/
└── build_YYYY-MM-DD_HH-MM-SS.log
```

---

## Requirements

### System Requirements
- **Python**: 3.8 or higher
- **FontForge**: With Python scripting support
- **Memory**: 4GB+ recommended for parallel builds
- **Storage**: 500MB+ for source fonts and output

### Python Dependencies
```
fonttools>=4.0.0
jinja2>=3.0.0
pyyaml>=6.0
rich>=12.0.0  # Optional, for enhanced progress display
```

### Font Requirements
**All source fonts must be monospace (fixed-width) fonts.**

Recommended source fonts:
- **English**: Meslo LG, JetBrains Mono, Fira Code, Source Code Pro
- **Korean**: Sarasa Fixed K, D2Coding, NanumGothicCoding
- **Japanese**: Sarasa Fixed J, Source Han Code JP

---

## License

### Font License
Generated fonts are licensed under **SIL Open Font License 1.1**

Based on:
- **Meslo LG** (Apache License 2.0)
- **Sarasa Gothic** (SIL OFL 1.1)

### Source Code
Build system code is provided under **Apache License 2.0**

```
Copyright (c) 2025, kkotdari

Licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
```

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test with multiple profiles
4. Submit a pull request

For bugs and feature requests, use the [GitHub issue tracker](https://github.com/kkotdari/kdr-mono/issues).

---

## Documentation

- [Configuration Guide](docs/configuration.md)
- [Character Classification](docs/characters.md)
- [Profile System](docs/profiles.md)
- [API Reference](docs/api.md)

---

## Acknowledgments

This project wouldn't be possible without:

- **Meslo LG** by André Berg
- **Sarasa Gothic** by Belleve Invis
- **FontForge** community
- All contributors and testers

---

**Version**: 1.0.1
**Author**: kkotdari  
**Repository**: https://github.com/kkotdari/kdr-mono