#!/usr/bin/env python3
"""
Auto-Trader API Server
Script to start the Auto-Trader API server using platform-appropriate WSGI server
(gunicorn for Unix/Linux/Mac, waitress for Windows)
"""

import os
import sys
import json
import platform
import argparse
import subprocess
import importlib.util
from dotenv import load_dotenv
from core.logging_config import get_logger

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = get_logger('autotrader.server', 'server')

def check_and_install_dependencies():
    """
    Check for required dependencies and install them if needed
    """
    logger.info("Checking dependencies...")
    try:
        # First, ensure pip is available
        import pip
    except ImportError:
        logger.error("pip is not available. Please install pip first.")
        return
        
    # Get platform-specific WSGI server
    is_windows = platform.system() == 'Windows'
    
    # Find requirements.txt file
    requirements_path = "requirements.txt"
    if not os.path.exists(requirements_path):
        # Check if we're running from a different directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        requirements_path = os.path.join(script_dir, "requirements.txt")
        if not os.path.exists(requirements_path):
            logger.error(f"Could not find requirements.txt")
            return
    
    # Read requirements
    try:
        with open(requirements_path, 'r') as f:
            requirements = [line.strip() for line in f.readlines() 
                        if line.strip() and not line.strip().startswith('#')]
    except Exception as e:
        logger.error(f"Error reading requirements.txt: {str(e)}")
        return
        
    # Install missing requirements
    missing_deps = []
    for req in requirements:
        # Extract package name (everything before any comparison operator)
        package_name = req.split('>=')[0].split('==')[0].split('>')[0].split('<')[0].split('<=')[0].strip()
        
        if not importlib.util.find_spec(package_name.replace('-', '_')):
            missing_deps.append(req)
    
    if missing_deps:
        logger.info(f"Installing missing dependencies: {', '.join(missing_deps)}")
        try:
            # Install all missing dependencies at once for efficiency
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_deps)
            logger.info("Successfully installed all missing dependencies.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {str(e)}")
            logger.error("Please manually install them with: pip install -r requirements.txt")
    else:
        logger.info("All dependencies are already installed.")
        
    # Double-check platform-specific WSGI server is available
    # This is especially important since it's critical for the app to start
    if is_windows and importlib.util.find_spec("waitress") is None:
        logger.warning("Waitress is still not installed. Attempting to install it directly...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "waitress>=2.0.0"])
            logger.info("Successfully installed waitress.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install waitress: {str(e)}")
            logger.error("Please manually install it with: pip install waitress>=2.0.0")
    elif not is_windows and importlib.util.find_spec("gunicorn") is None:
        logger.warning("Gunicorn is still not installed. Attempting to install it directly...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "gunicorn>=20.1.0"])
            logger.info("Successfully installed gunicorn.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install gunicorn: {str(e)}")
            logger.error("Please manually install it with: pip install gunicorn>=20.1.0")

def main():
    """
    Start the API server using appropriate WSGI server based on platform
    """
    try:
        # Check and install required dependencies
        check_and_install_dependencies()
        
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Start the Auto-Trader API server')
        parser.add_argument('--realmoney', action='store_true', 
                           help='Use real money trading configuration instead of paper trading')
        args = parser.parse_args()
        
        # Set environment variable for connection config based on the flag
        config_path = 'connection_real.json' if args.realmoney else 'connection.json'
        os.environ['CONNECTION_CONFIG'] = config_path
        try:
            with open(config_path, 'r') as config_file:
                connection_config = json.load(config_file)
            account_suffix = str(connection_config.get('account_id') or '')[-4:] or 'none'
            logger.warning(
                "Using %s: port=%s, readonly=%s, account=****%s, client_id=%s",
                config_path,
                connection_config.get('port', 'unset'),
                connection_config.get('readonly', True),
                account_suffix,
                connection_config.get('client_id', 1)
            )
        except (OSError, ValueError) as error:
            logger.warning("Could not inspect %s before startup: %s", config_path, error)
        
        # Get port from environment variable or use default (changed from 5000 to 8000)
        port = os.environ.get('PORT', '8000')
        requested_workers = int(os.environ.get('WORKERS', '1'))
        workers = 1
        if requested_workers != workers:
            logger.warning(
                "Ignoring WORKERS=%s: IB order tracking requires one web worker "
                "to preserve a single API client identity",
                requested_workers
            )
        
        # Check if port is available
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', int(port)))
        sock.close()
        
        if result == 0:
            logger.error(f"Port {port} is already in use. Please stop the existing process or use a different port.")
            logger.info(f"Try: PORT={int(port)+1} python3 run_api.py")
            sys.exit(1)
        
        # Detect operating system
        is_windows = platform.system() == 'Windows'
        
        if is_windows:
            # Windows: Use waitress
            logger.info(f"Starting Auto-Trader API server on port {port} with waitress (Windows)")
            # We need to import here to avoid issues if waitress is not installed
            try:
                from waitress import serve
                from app import app
                # Start the server
                serve(app, host='0.0.0.0', port=int(port), threads=workers)
            except ImportError:
                logger.error("Waitress is not installed. Please install it with: pip install waitress")
                sys.exit(1)
        else:
            # Unix/Linux/Mac: Use gunicorn
            logger.info(f"Starting Auto-Trader API server on port {port} with {workers} workers using gunicorn")
            try:
                # Build the gunicorn command
                cmd = [
                    'gunicorn', f'--workers={workers}',
                    f'--bind=127.0.0.1:{port}', 'app:app'
                ]
                subprocess.call(cmd)
            except Exception as e:
                logger.error(f"Error starting gunicorn: {str(e)}")
                
                # Fallback to Flask development server
                logger.info("Falling back to Flask development server")
                from app import app
                app.run(host='0.0.0.0', port=int(port))
        
    except Exception as e:
        logger.error(f"Error starting API server: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main() 
