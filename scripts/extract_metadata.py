# Reads manifest.csv and extracts EXIF datetime + image dimensions.
# Merges ML output columns from ml_outputs.csv
# NEW: Enhanced error logging, validation, and row integrity checks

import csv
import logging
from pathlib import Path
from datetime import datetime

# Try to import optional dependencies
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL not installed, image dimension extraction disabled")

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False
    print("Warning: exifread not installed, EXIF datetime extraction disabled")

# Setup logging
LOG_FILE = Path("data/outputs/metadata_log.txt")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MANIFEST = Path("data/outputs/manifest.csv")
OUT_CSV = Path("data/outputs/metadata.csv")
ML_OUT = Path("data/outputs/ml_outputs.csv")
ERROR_LOG = Path("data/outputs/metadata_errors.csv")

# Required output columns
FIELDNAMES = [
    "file_id", "file_name", "local_file_name",
    "exif_datetime", "date", "time",
    "width", "height",
    "has_animal", "is_blank", "species", "count", "model_certainty"
]


def get_exif_datetime(path: Path) -> tuple[str, str]:
    """
    Extract EXIF datetime from image.
    Returns (datetime_string, error_message)
    """
    if not HAS_EXIFREAD:
        return "", "exifread_not_installed"
    
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
        
        for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
            if key in tags:
                return str(tags[key]), ""
        
        return "", "no_exif_datetime"
    except FileNotFoundError:
        return "", "file_not_found"
    except Exception as e:
        return "", f"exif_error: {repr(e)}"


def split_date_time(dt_str: str) -> tuple[str, str]:
    """Split EXIF datetime string into date and time components."""
    if not dt_str:
        return "", ""
    try:
        date_part, time_part = dt_str.split(" ", 1)
        # Convert YYYY:MM:DD to YYYY-MM-DD
        return date_part.replace(":", "-"), time_part
    except Exception:
        return "", ""


def get_image_size(path: Path) -> tuple[int | str, int | str, str]:
    """
    Get image dimensions.
    Returns (width, height, error_message)
    """
    if not HAS_PIL:
        return "", "", "pil_not_installed"
    
    try:
        with Image.open(path) as img:
            return img.width, img.height, ""
    except FileNotFoundError:
        return "", "", "file_not_found"
    except Exception as e:
        return "", "", f"image_error: {repr(e)}"


def load_ml_outputs() -> dict:
    """Load ML outputs keyed by file_id."""
    if not ML_OUT.exists():
        logger.warning(f"ML outputs not found: {ML_OUT}")
        return {}
    
    out = {}
    with open(ML_OUT, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = row.get("file_id", "")
            if fid:
                out[fid] = row
    
    logger.info(f"Loaded {len(out)} ML outputs")
    return out


def log_error(error_rows: list, file_id: str, file_name: str, error_type: str, message: str):
    """Log an error for later review."""
    error_rows.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "file_id": file_id,
        "file_name": file_name,
        "error_type": error_type,
        "message": message,
    })


def write_error_log(error_rows: list):
    """Write error log to CSV."""
    if not error_rows:
        return
    
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ERROR_LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "file_id", "file_name", "error_type", "message"])
        w.writeheader()
        w.writerows(error_rows)
    logger.info(f"Wrote {len(error_rows)} errors to {ERROR_LOG}")


def validate_row(row: dict, ml: dict) -> list[str]:
    """
    Validate a row for completeness.
    Returns list of validation warnings.
    """
    warnings = []
    
    if not row.get("file_id"):
        warnings.append("missing_file_id")
    
    if not row.get("date") and not row.get("time"):
        warnings.append("missing_datetime")
    
    if not row.get("width") or not row.get("height"):
        warnings.append("missing_dimensions")
    
    # Check ML columns
    if not ml:
        warnings.append("no_ml_data")
    elif ml.get("has_animal") == "":
        warnings.append("ml_not_processed")
    
    return warnings


def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 50)
    logger.info("Starting metadata extraction")
    
    if not MANIFEST.exists():
        raise FileNotFoundError(f"manifest.csv not found at {MANIFEST}. Run make_manifest.py first.")
    
    # Load ML outputs
    ml_by_id = load_ml_outputs()
    
    rows_out = []
    error_rows = []
    stats = {
        "total": 0,
        "with_exif": 0,
        "with_dimensions": 0,
        "with_ml": 0,
        "animals": 0,
        "blanks": 0,
        "broken": 0,
    }
    
    with open(MANIFEST, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            stats["total"] += 1
            file_id = row.get("file_id", "")
            file_name = row.get("file_name", "")
            local_file_name = row.get("local_file_name", "")
            path = Path(row.get("local_path", ""))
            
            # Extract EXIF datetime
            exif_dt, exif_error = get_exif_datetime(path)
            date, time = split_date_time(exif_dt)
            
            if exif_dt:
                stats["with_exif"] += 1
            elif exif_error:
                log_error(error_rows, file_id, file_name, "EXIF_ERROR", exif_error)
            
            # Get image dimensions
            width, height, size_error = get_image_size(path)
            
            if width and height:
                stats["with_dimensions"] += 1
            elif size_error:
                log_error(error_rows, file_id, file_name, "IMAGE_ERROR", size_error)
                if "file_not_found" in size_error:
                    stats["broken"] += 1
            
            # Get ML data
            ml = ml_by_id.get(file_id, {})
            has_animal = ml.get("has_animal", "")
            is_blank = ml.get("is_blank", "")
            
            # If has_animal exists but is_blank doesn't, compute it
            if str(has_animal).strip() != "" and str(is_blank).strip() == "":
                try:
                    is_blank = "0" if int(float(has_animal)) == 1 else "1"
                except (ValueError, TypeError):
                    is_blank = ""
            
            if has_animal != "":
                stats["with_ml"] += 1
                if str(has_animal) == "1":
                    stats["animals"] += 1
                if str(is_blank) == "1":
                    stats["blanks"] += 1
            
            out_row = {
                "file_id": file_id,
                "file_name": file_name,
                "local_file_name": local_file_name,
                "exif_datetime": exif_dt,
                "date": date,
                "time": time,
                "width": width,
                "height": height,
                "has_animal": has_animal,
                "is_blank": is_blank,
                "species": ml.get("species", ""),
                "count": ml.get("count", ""),
                "model_certainty": ml.get("model_certainty", ""),
            }
            
            # Validate row
            warnings = validate_row(out_row, ml)
            if warnings:
                log_error(error_rows, file_id, file_name, "VALIDATION", ", ".join(warnings))
            
            rows_out.append(out_row)
            
            if stats["total"] % 500 == 0:
                logger.info(f"Processed {stats['total']} files...")
    
    # Write output
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows_out)
    
    # Write error log
    write_error_log(error_rows)
    
    # Summary
    logger.info(f"Wrote {len(rows_out)} rows to {OUT_CSV}")
    logger.info(f"Statistics:")
    logger.info(f"  - Total files: {stats['total']}")
    logger.info(f"  - With EXIF datetime: {stats['with_exif']}")
    logger.info(f"  - With dimensions: {stats['with_dimensions']}")
    logger.info(f"  - With ML results: {stats['with_ml']}")
    logger.info(f"  - Animals: {stats['animals']}")
    logger.info(f"  - Blanks: {stats['blanks']}")
    logger.info(f"  - Broken/missing: {stats['broken']}")
    logger.info(f"  - Errors logged: {len(error_rows)}")
    
    print(f"\nMetadata extraction complete:")
    print(f"  Total: {stats['total']}")
    print(f"  With EXIF: {stats['with_exif']}")
    print(f"  With ML: {stats['with_ml']} (Animals: {stats['animals']}, Blanks: {stats['blanks']})")
    print(f"  Errors: {len(error_rows)}")
    print(f"Output: {OUT_CSV}")
    
    if not ML_OUT.exists():
        print("\nNote: ml_outputs.csv not found. ML columns are empty.")
        print("Run MegaDetector and run_inference.py to populate ML columns.")


if __name__ == "__main__":
    main()
