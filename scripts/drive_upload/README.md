# Drive Upload Pipeline

Uploads processed CSV results back to Julie's Wildlife Database on Google Drive.

## WARNING

DO NOT TEST THESE SCRIPTS WITHOUT PERMISSION. Running them will upload files directly to Julie's Drive and cannot be easily undone.

## How It Works

1. find_camera_folders.py - Finds Drive folder IDs for each camera location
2. make_output_by_location.py - Splits output.csv by camera location locally
3. upload_to_drive.py - Uploads CSVs to Julie's Drive with append logic

## For Developers

Step 1: Find folder IDs
```bash
python scripts/drive_upload/find_camera_folders.py
```

Copy the folder IDs and paste them into upload_to_drive.py in the CAMERA_FOLDERS dictionary.

Step 2: Split results by location
```bash
python scripts/drive_upload/make_output_by_location.py
```

Creates separate CSVs in data/outputs/by_location/ for each camera.

Step 3: Test locally first (IMPORTANT)
Before running on Julie's Drive, test on your personal Google Drive:
- Create a test folder structure in your Drive
- Share it with the service account
- Modify CAMERA_FOLDERS in upload_to_drive.py to use your test folder IDs
- Run upload_to_drive.py to verify it works

Step 4: Upload to Julie's Drive (with permission)
Once testing is confirmed working:
- Update CAMERA_FOLDERS with real Julie's folder IDs
- Run upload_to_drive.py

## For Julie

Once this is integrated into the full pipeline, the workflow will be:
1. Run the main pipeline script
2. Results automatically upload to your Drive in the correct camera folders
3. Existing CSVs are updated with new data instead of overwritten
4. No manual work needed

## Technical Details

Uses Google Drive API with service account authentication (inf191a-uci-nature-sa.json).
Creates one CSV per camera location with append and deduplication logic.