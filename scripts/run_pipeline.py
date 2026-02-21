#!/usr/bin/env python3
# Runs the complete pipeline in the correct order
# Fixed: Unicode encoding issue on Windows

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Pipeline steps in order
STEPS = [
    {
        "name": "Index Drive",
        "cmd": ["python", "scripts/pipeline/build_index.py"],
        "output": "data/outputs/drive_index.csv",
        "required": True,
    },
    {
        "name": "Download Images",
        "cmd": ["python", "scripts/pipeline/download_drive.py"],
        "output": "data/outputs/download_log.csv",
        "required": True,
    },
    {
        "name": "Create Manifest",
        "cmd": ["python", "scripts/pipeline/make_manifest.py"],
        "output": "data/outputs/manifest.csv",
        "required": True,
    },
    {
        "name": "Run Inference",
        "cmd": ["python", "scripts/ml/run_inference.py"],
        "output": "data/outputs/ml_outputs.csv",
        "required": False,
    },
    {
        "name": "Extract Metadata",
        "cmd": ["python", "scripts/pipeline/extract_metadata.py"],
        "output": "data/outputs/metadata.csv",
        "required": True,
    },
    {
        "name": "Generate Output",
        "cmd": ["python", "scripts/pipeline/make_output.py"],
        "output": "data/outputs/output.csv",
        "required": True,
    },
    {
        "name": "Validate Output",
        "cmd": ["python", "scripts/pipeline/validate_output.py"],
        "output": None,
        "required": False,
    },
]

LOG_FILE = Path("data/outputs/pipeline_log.txt")


def log(msg: str):
    """Log to both console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(step: dict) -> tuple:
    """Run a single pipeline step."""
    name = step["name"]
    cmd = step["cmd"]
    
    log(f"Starting: {name}")
    log(f"  Command: {' '.join(cmd)}")
    
    start = time.time()
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        duration = time.time() - start
        
        if result.returncode != 0:
            log(f"  [FAILED] (exit code {result.returncode})")
            return False, duration
        
        if step["output"]:
            output_path = Path(step["output"])
            if output_path.exists():
                size = output_path.stat().st_size
                log(f"  [OK] Complete ({duration:.1f}s) -> {step['output']} ({size:,} bytes)")
            else:
                log(f"  [WARN] Complete but output file not found: {step['output']}")
        else:
            log(f"  [OK] Complete ({duration:.1f}s)")
        
        return True, duration
        
    except KeyboardInterrupt:
        duration = time.time() - start
        log(f"  [STOPPED] Interrupted by user (Ctrl+C)")
        return False, duration
    except FileNotFoundError:
        duration = time.time() - start
        log(f"  [FAILED] Script not found: {cmd[1]}")
        return False, duration
    except Exception as e:
        duration = time.time() - start
        log(f"  [FAILED] Error: {repr(e)}")
        return False, duration


def main():
    log("=" * 60)
    log("WILDLIFE CAMERA IMAGE PROCESSING PIPELINE")
    log("=" * 60)
    
    total_start = time.time()
    results = []

    python_exe = sys.executable
    
    for i, step in enumerate(STEPS, 1):
        step = dict(step)
        step["cmd"] = [python_exe] + step["cmd"][1:]

        log(f"\n[Step {i}/{len(STEPS)}] {step['name']}")
        log("-" * 40)
        
        success, duration = run_step(step)
        results.append({
            "name": step["name"],
            "success": success,
            "duration": duration,
            "required": step["required"],
        })
        
        if not success and step["required"]:
            log(f"\n[STOPPED] Pipeline stopped: Required step '{step['name']}' failed")
            break
    
    total_duration = time.time() - total_start
    
    log("\n" + "=" * 60)
    log("PIPELINE SUMMARY")
    log("=" * 60)
    
    for r in results:
        status = "[OK]" if r["success"] else "[FAILED]"
        req = " (required)" if r["required"] else ""
        log(f"  {status} {r['name']}: {r['duration']:.1f}s{req}")
    
    log(f"\nTotal time: {total_duration:.1f}s ({total_duration/60:.1f} min)")
    
    final_output = Path("data/outputs/output.csv")
    if final_output.exists():
        import csv
        with open(final_output, "r", encoding="utf-8") as f:
            row_count = sum(1 for _ in csv.reader(f)) - 1
        log(f"\n[OK] Final output: {final_output}")
        log(f"  Rows: {row_count}")
    else:
        log(f"\n[FAILED] Final output not found: {final_output}")
    
    all_required_ok = all(r["success"] for r in results if r["required"])
    
    if all_required_ok:
        log("\n[OK] Pipeline completed successfully!")
        return 0
    else:
        log("\n[FAILED] Pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())