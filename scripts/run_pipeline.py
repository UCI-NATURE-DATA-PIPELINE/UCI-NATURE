# runs the pipeline in the correct order (index > download > csv outputs)

import subprocess
import sys

steps = [
    ["python", "scripts/build_index.py"],
    ["python", "scripts/download_drive.py"],
    ["python", "scripts/make_manifest.py"],
    ["python", "scripts/run_inference.py"],
    ["python", "scripts/extract_metadata.py"],
    ["python", "scripts/make_output.py"],
]

def main():
    for cmd in steps:
        print("\n>>>", " ".join(cmd))
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print("Stopped due to an error on:", " ".join(cmd))
            sys.exit(result.returncode)

    print("\n Done. File: data/outputs/output.csv")

if __name__ == "__main__":
    main()