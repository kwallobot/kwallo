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
    n, stale = 0, []
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            rel = o["Key"][len(prefix):]
            if not rel:
                continue
            if rel.startswith("site/") and rel.count("/") >= 2:
                stale.append({"Key": o["Key"]})                   # v33: website copies inside data/ (left by an interrupted run): not needed
                continue
            path = os.path.join(local, rel)
            etag = o["ETag"].strip('"')
            seen[rel] = etag
            if os.path.exists(path) and ("-" in etag or _md5(path) == etag) and os.path.getsize(path) == o["Size"]:
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            c.download_file(bucket, o["Key"], path)
            n += 1
    for i in range(0, len(stale), 1000):                            # tidy them away, 1,000 at a time
        try:
            c.delete_objects(Bucket=bucket, Delete={"Objects": stale[i:i + 1000], "Quiet": True})
        except Exception as ex:
            print(f"Storage: could not tidy old website copies ({str(ex)[:60]}); they're skipped anyway.")
            break
    if stale:
        print(f"Storage: {len(stale)} leftover website copies in data/ removed (the live site files in site/ are untouched).")
    print(f"Storage: {len(seen)} files in R2, {n} downloaded.")
    return seen

def sync_up(local, seen, prefix="data/"):
    """Upload files that are new or changed since the download."""
    c, bucket = _client()
    if c is None:
        return seen
    n = 0
    for root, _, files in os.walk(local):
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.relpath(path, local).replace(os.sep, "/")
            if rel.startswith("site/") and rel.count("/") >= 2:
                continue                                        # v33: website pages are published to site/ already
            if rel in seen and "-" not in seen[rel] and _md5(path) == seen[rel]:
                continue
            c.upload_file(path, bucket, prefix + rel)
            seen[rel] = _md5(path)                                  # v30: remember it, so later checkpoints skip it
            n += 1
    print(f"Storage: {n} files uploaded to R2.")
    return seen

import threading
from concurrent.futures import ThreadPoolExecutor
_POOL, _FUTURES, _LOCK = None, [], threading.Lock()

def put_public_async(key, body, content_type="application/json"):
    """v33: queue an upload; up to 24 run at once. Call flush() to wait for them all."""
    global _POOL
    c, bucket = _client()
    if c is None:
        return False
    with _LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(max_workers=24)
        _FUTURES.append((key, _POOL.submit(c.put_object, Bucket=bucket, Key=key, Body=body, ContentType=content_type, CacheControl="public, max-age=120")))
    return True

def flush():
    """Wait for queued uploads; returns (number done, list of keys that failed)."""
    global _FUTURES
    with _LOCK:
        fs, _FUTURES = _FUTURES, []
    done, failed = 0, []
    for key, f in fs:
        try:
            f.result(); done += 1
        except Exception:
            failed.append(key)
    return done, failed

def put_public(key, body, content_type="application/json"):
    """Write one file to the site/ area of the bucket (what the web app and the Telegram bot read)."""
    c, bucket = _client()
    if c is None:
        return False
    c.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type, CacheControl="public, max-age=120")
    return True

def backup(prefix="data/", keep_weekly=4, keep_monthly=6):
    """v29: copy data/ into backups/YYYY-MM-DD/ inside the bucket (a server-side copy: nothing is downloaded), then keep the
    last few weekly backups plus the first backup of each of the last few months, deleting older ones."""
    import datetime
    c, bucket = _client()
    if c is None:
        print("Backup: skipped (no R2 settings).")
        return
    today = datetime.date.today().isoformat()
    n = 0
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            if o["Key"].startswith(prefix + "site/") and o["Key"][len(prefix):].count("/") >= 2:
                continue                                        # v33: website pages aren't backed up (rebuilt every run)
            c.copy_object(Bucket=bucket, Key=f"backups/{today}/{o['Key'][len(prefix):]}", CopySource={"Bucket": bucket, "Key": o["Key"]})
            n += 1
    dates = set()
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="backups/", Delimiter="/"):
        for p in page.get("CommonPrefixes", []):
            dates.add(p["Prefix"].split("/")[1])
    dates = sorted(dates)
    keep = set(dates[-keep_weekly:])
    first_of_month = {}
    for d in dates:
        first_of_month.setdefault(d[:7], d)
    keep |= set(sorted(first_of_month.values())[-keep_monthly:])
    removed = 0
    for d in dates:
        if d in keep:
            continue
        for page in c.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"backups/{d}/"):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            for i in range(0, len(objs), 1000):
                c.delete_objects(Bucket=bucket, Delete={"Objects": objs[i:i + 1000]})
        removed += 1
    print(f"Backup: {n} files copied to backups/{today}/; keeping {len(keep)} backups ({', '.join(sorted(keep))}); {removed} older ones removed.")
