import hashlib
from pathlib import Path
import sys

def calculate_sha256(filepath: Path):
    """Calculates the SHA256 hash for a given file."""
    if not filepath.exists():
        print(f"Error: File not found at {filepath}")
        return

    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Read and update hash string value in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        calculated_hash = sha256_hash.hexdigest()
        print("-" * 50)
        print(f"File Path: {filepath}")
        print(f"SHA256 Checksum: {calculated_hash}")
        print("-" * 50)

    except Exception as e:
        print(f"An error occurred while reading the file: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        target_path = Path("data") / "raw" / "2024" / "1.0" / "2024_EAVS_for_Public_Release_V1_xlsx.xlsx"
    else:
        # Allow passing the path as a command-line argument
        target_path = Path(sys.argv[1])
        
    calculate_sha256(target_path)