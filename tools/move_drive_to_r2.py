# ===== ONE-TIME: copy your Kwallo data from Google Drive to Cloudflare R2 =====
# Run this in a NEW Colab cell (any notebook). It reads your Drive 'football' folder and uploads it to R2 as data/...
# Your R2 keys go in Colab Secrets first: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
!pip -q install boto3
import os, boto3
from google.colab import drive, userdata
drive.mount("/content/drive")
SRC = "/content/drive/MyDrive/football"
s3 = boto3.client("s3", endpoint_url=f"https://{userdata.get('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                  aws_access_key_id=userdata.get("R2_ACCESS_KEY_ID"), aws_secret_access_key=userdata.get("R2_SECRET_ACCESS_KEY"), region_name="auto")
bucket, n, size = userdata.get("R2_BUCKET"), 0, 0
for root, _, files in os.walk(SRC):
    for f in files:
        p = os.path.join(root, f)
        key = "data/" + os.path.relpath(p, SRC).replace(os.sep, "/")
        s3.upload_file(p, bucket, key)
        n += 1; size += os.path.getsize(p)
        if n % 50 == 0:
            print(f"  {n} files, {size / 1e6:.0f} MB so far...")
print(f"Done: {n} files ({size / 1e6:.0f} MB) copied to R2. Keep the Drive copy as a backup.")
