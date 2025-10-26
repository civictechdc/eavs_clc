from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env file if it exists
load_dotenv()

# Paths
PROJ_ROOT = Path(__file__).resolve().parents[1]
logger.info(f"PROJ_ROOT path is: {PROJ_ROOT}")

# Project data directory
DATA_DIR = PROJ_ROOT / "data"
PROJ_CLEANED_DATA_DIR = DATA_DIR / "cleaned"
PROJ_ENRICHED_DATA_DIR = DATA_DIR / "enriched"

# Module data directory for USDA ERS
MOD_DATA_DIR = DATA_DIR / "external" / "usda_ers"
RAW_DATA_DIR = MOD_DATA_DIR / "raw"
PROC_DATA_DIR = MOD_DATA_DIR / "processed"

# If tqdm is installed, configure loguru with tqdm.write
# https://github.com/Delgan/loguru/issues/135
try:
    from tqdm import tqdm

    logger.remove(0)
    logger.add(lambda msg: tqdm.write(msg, end=""), colorize=True)
except ModuleNotFoundError:
    pass
