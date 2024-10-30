### Build and run the container:
```bash
docker-compose up --build
```

### Python Development Setup
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Unix or MacOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create requirements.txt (when adding new packages)
pip freeze > requirements.txt
```