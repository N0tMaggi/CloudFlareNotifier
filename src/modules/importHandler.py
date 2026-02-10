#  handles imports for the project
import sys
import subprocess
import importlib

# Helper function to install and import modules
def _get_module(module_name, package_name=None):
    if package_name is None:
        package_name = module_name
    try:
        return importlib.import_module(module_name)
    except ImportError:
        print(f"Module {module_name} not found. Installing {package_name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"{package_name} installed successfully.")
            return importlib.import_module(module_name)
        except Exception as e:
            print(f"Failed to install {package_name}: {e}")
            raise

# Expose modules for the rest of the project
# Standard libraries
os = _get_module("os")
time = _get_module("time")
json = _get_module("json")
logging = _get_module("logging")
asyncio = _get_module("asyncio")
threading = _get_module("threading")
traceback = _get_module("traceback")
configparser = _get_module("configparser")
datetime = _get_module("datetime")
typing = _get_module("typing")

# 3rd Party libraries
aiohttp = _get_module("aiohttp")

importsOK = True

def imports_ready():
    """
    Checks if importHandler has successfully loaded everything.
    Since loading this module runs the checks, this just returns True.
    """
    return importsOK
