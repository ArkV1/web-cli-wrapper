import os
import shutil
import subprocess
import sys
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_git_installed():
    try:
        result = subprocess.run(['git', '--version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE,
                              text=True)
        if result.returncode == 0:
            logger.info("Git is installed: %s", result.stdout.strip())
            return True
        else:
            logger.error("Git check failed: %s", result.stderr)
            return False
    except FileNotFoundError:
        logger.error("Git is not installed")
        return False

def clone_repository():
    repo_url = "https://github.com/ArkV1/web-cli-js-scripts"
    scripts_dir = Path("scripts")
    temp_dir = Path("temp_clone")

    logger.info("Starting repository clone process")
    logger.info("Scripts directory: %s", scripts_dir.absolute())

    # Create scripts directory if it doesn't exist
    scripts_dir.mkdir(exist_ok=True)

    try:
        # Remove temp directory if it exists
        if temp_dir.exists():
            logger.info("Removing existing temp directory")
            shutil.rmtree(temp_dir)

        # Clone the repository to a temporary directory
        logger.info("Cloning repository from %s", repo_url)
        result = subprocess.run(['git', 'clone', repo_url, str(temp_dir)], 
                              capture_output=True,
                              text=True,
                              check=True)
        
        if result.stdout:
            logger.info("Clone output: %s", result.stdout)

        # Copy contents to scripts directory
        logger.info("Copying repository contents to scripts directory")
        for item in temp_dir.iterdir():
            if item.name != '.git':  # Skip .git directory
                destination = scripts_dir / item.name
                if destination.exists():
                    logger.info("Removing existing %s", destination)
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink()
                if item.is_dir():
                    logger.info("Copying directory %s to %s", item, destination)
                    shutil.copytree(item, destination)
                else:
                    logger.info("Copying file %s to %s", item, destination)
                    shutil.copy2(item, destination)

        logger.info("Repository contents successfully copied to scripts directory")

    except subprocess.CalledProcessError as e:
        logger.error("Error cloning repository: %s", e)
        logger.error("Git output: %s", e.output)
        raise
    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        raise
    finally:
        # Clean up temporary directory
        if temp_dir.exists():
            logger.info("Cleaning up temporary directory")
            shutil.rmtree(temp_dir)

def main():
    try:
        logger.info("Starting build process")
        if not check_git_installed():
            logger.error("Git is not installed")
            sys.exit(1)

        clone_repository()
        logger.info("Build process completed successfully")
        return True
    except Exception as e:
        logger.error("Build process failed: %s", e, exc_info=True)
        return False

if __name__ == "__main__":
    main() 