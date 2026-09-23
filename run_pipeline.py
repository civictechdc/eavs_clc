# Pipeline Runner

import sys
from pathlib import Path

# Add the parent directory of 'eavs' to the system path to allow module import
sys.path.append(str(Path(__file__).parent))

from eavs.aggregate import main as aggregate_main
from eavs.build_dashboard import main as dashboard_main
from eavs.build_dashboard_p2 import main as dashboard_p2_main
from eavs.clean import main
from eavs.clean_cps import main as clean_cps_main
from loguru import logger as log

if __name__ == '__main__':
    log.info("Starting consolidated EAVS cleaning pipeline test run...")
    try:
        main()
    except Exception as e:
        log.error(f"Pipeline crashed during execution: {e}")

    log.info("Starting state-level aggregation...")
    try:
        aggregate_main()
    except Exception as e:
        log.error(f"Aggregation stage crashed: {e}")

    log.info("Starting CPS voting clean...")
    try:
        clean_cps_main()
    except Exception as e:
        log.error(f"CPS clean crashed: {e}")

    log.info("Starting dashboard build...")
    try:
        dashboard_main()
    except Exception as e:
        log.error(f"Dashboard build crashed: {e}")

    log.info("Starting Page 2 dashboard build...")
    try:
        dashboard_p2_main()
    except Exception as e:
        log.error(f"Page 2 dashboard build crashed: {e}")

    log.info("Test run finished.")