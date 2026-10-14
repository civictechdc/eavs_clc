# Pipeline Runner

import sys
from pathlib import Path

# Add the parent directory of 'eavs' to the system path to allow module import
sys.path.append(str(Path(__file__).parent))

from eavs.clean import main
from loguru import logger as log

if __name__ == '__main__':
    log.info("Starting consolidated EAVS cleaning pipeline test run...")
    try:
        main()
    except Exception as e:
        log.error(f"Pipeline crashed during execution: {e}")
    log.info("Test run finished.")