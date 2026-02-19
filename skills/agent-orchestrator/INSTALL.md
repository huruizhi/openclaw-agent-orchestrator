# Installation

## Requirements

- Python 3.10 or higher
- pip (Python package manager)

## Install Dependencies

### Option 1: Install to user directory (recommended)

```bash
pip3 install --user -r requirements.txt
```

### Option 2: Install to virtual environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Option 3: System-wide installation

```bash
pip3 install -r requirements.txt
```

## Verify Installation

Run the import test:

```bash
python3 test_imports.py
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| jsonschema | >=4.26.0 | JSON Schema validation |
| python-dotenv | >=1.0.0 | Load environment variables from .env |

## First Time Setup

1. Install dependencies:
   ```bash
   pip3 install --user -r requirements.txt
   ```

2. Copy environment template:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and add your LLM API credentials:
   ```bash
   vim .env  # or your preferred editor
   ```

4. Verify setup and preflight:
   ```bash
   python3 test_imports.py
   bash scripts/run_preflight.sh
   ```

## Troubleshooting

### ImportError: No module named 'jsonschema'

```bash
pip3 install --user jsonschema
```

### ImportError: No module named 'dotenv'

```bash
pip3 install --user python-dotenv
```

### pip not found

```bash
# Ubuntu/Debian
sudo apt-get install python3-pip

# CentOS/RHEL
sudo yum install python3-pip

# macOS
brew install python3
```

## Next

- Runtime config: `CONFIG.md`
- First workflow run: `QUICKSTART.md`
- Operations and recovery: `OPERATIONS.md`
