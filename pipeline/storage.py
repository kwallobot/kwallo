"""Keeps the pipeline's data folder in sync with a Cloudflare R2 bucket (S3-compatible).
If the R2 settings aren't present (e.g. a local test), it does nothing and the local folder is used as is."""
import os, hashlib, json

def _client():
    need = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    if not all(os.environ.get(k) for k in need):
        return None, None
    import boto3
    c = boto3.client("s3", endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                     aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    return c, os.environ["R2_BUCKET"]

def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def sync_down(local, prefix="data/"):
    """Download every file under data/ that's missing or different locally. Returns the fingerprints seen."""
    c, bucket = _client()
    seen = {}
    if c is None:
        print("Storage: no R2 settings, using the local folder only.")
        return seen
    n = 0
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            rel = o["Key"][len(prefix):]
            if not rel:
                continue
            path = os.path.join(local, rel)
            etag = o["ETag"].strip('"')
            seen[rel] = etag
            if os.path.exists(path) and ("-" in etag or _md5(path) == etag) and os.path.getsize(path) == o["Size"]:
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            c.download_file(bucket, o["Key"], path)
            n += 1
    print(f"Storage: {len(seen)} files in R2, {n} downloaded.")
    return seen

def sync_up(local, seen, prefix="data/"):
    """Upload files that are new or changed since the download."""
    c, bucket = _client()
    if c is None:
        return
    n = 0
    for root, _, files in os.walk(local):
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.relpath(path, local).replace(os.sep, "/")
            if rel in seen and "-" not in seen[rel] and _md5(path) == seen[rel]:
                continue
            c.upload_file(path, bucket, prefix + rel)
            n += 1
    print(f"Storage: {n} files uploaded to R2.")

def put_public(key, body, content_type="application/json"):
    """Write one file to the site/ area of the bucket (what the web app and the Telegram bot read)."""
    c, bucket = _client()
    if c is None:
        return False
    c.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type, CacheControl="public, max-age=120")
    return True
