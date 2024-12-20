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

### Python Development Setup
```bash 
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```warning
!!! IMPORTANT !!!
Only single gunicorn worker is supported at the moment.
```

### Run Gunicorn
```bash
gunicorn --worker-class gevent --workers 1 --bind 0.0.0.0:3003 --reload app:app
```