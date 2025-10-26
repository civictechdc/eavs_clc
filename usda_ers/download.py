from hashlib import sha256
from pathlib import Path
from urllib import parse

import httpx
from loguru import logger
import pandas as pd

from usda_ers.config import RAW_DATA_DIR

MANIFEST_PATH = Path(__file__).parent / "assets" / "manifest.json"


def load_manifest() -> pd.DataFrame:
    df = pd.read_json(MANIFEST_PATH, lines=False)
    return df


def download_data():
    df = load_manifest()
    for row in df.itertuples():
        url = row.url
        parsed_url = parse.urlparse(url)
        filename = parsed_url.path.split("/")[-1]
        dest = (
            RAW_DATA_DIR / 
            str(row.measure) /
            str(row.year) / 
            str(row.version) / 
            filename
        )
        
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            logger.info(
                f"Downloading {url} for USDA-ERS data of "
                f"{row.measure} {row.year} (v{row.version}) to {dest}."
            )
            dest.write_bytes(httpx.get(url).content)
        else:
            logger.info(f"{dest} already exists, skipping download.")

        # Verify the checksum
        sha256_hash = sha256(dest.read_bytes()).hexdigest()
        if sha256_hash != row.sha256sum:
            logger.warning(
                f"Checksum mismatch for {dest}. Expected {row.sha256sum}, got {sha256_hash}."
            )
            dest.unlink()
    logger.success("Data download complete.")


if __name__ == "__main__":
    download_data()
