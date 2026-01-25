# Mater-Browser

Intelligent browser automation agent for job applications.

## Architecture

- **browser/** - Chrome CDP connection and page management
- **extractor/** - DOM and form element extraction
- **agent/** - Claude integration for form analysis
- **executor/** - Action execution on pages
- **profile/** - User profile management
- **core/** - Config and logging

## Usage

1. Start Chrome: `scripts\start_chrome.bat`
2. Run: `python main.py`

## Configuration

- `config/settings.yaml` - Browser and Claude settings
- `config/profile.yaml` - Your profile data for applications
