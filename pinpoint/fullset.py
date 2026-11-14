"""On-demand access to single files of the FULL Junction dataset (10 GB zip) without downloading it.

The zip's central directory is indexed once (data/full/zipindex.pkl, ~14k entries); a file is then
fetched with one HTTP range request and cached under data/full/files/<path inside the dataset>.
Used for drawings the preview lacks (e.g. the source .ifc of a rendered ifc_models plan) and for
the full-dataset robustness sample.  Nothing is uploaded anywhere; this only reads the public zip.
"""
import os, pickle, struct, zlib, threading
import requests

URL = 'https://fwjydgxpttajiqpfmqtj.supabase.co/storage/v1/object/public/stoa-junction-2026/junction-dataset.zip'
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FULL = os.path.join(ROOT, 'data/full')
FILES = os.path.join(FULL, 'files')
IDX = os.path.join(FULL, 'zipindex.pkl')
PREFIX = 'junction-dataset/'
_lock = threading.Lock()
_idx = None


def index():
    global _idx
    if _idx is None:
        if os.path.exists(IDX):
            _idx = pickle.load(open(IDX, 'rb'))
        else:
            from remotezip import RemoteZip
            with RemoteZip(URL) as z:
                _idx = {i.filename: (i.header_offset, i.compress_size, i.file_size, i.compress_type)
                        for i in z.infolist()}
            os.makedirs(FULL, exist_ok=True)
            pickle.dump(_idx, open(IDX, 'wb'))
    return _idx


def local(rel):
    """Cached local path for a dataset-relative path like 'data/ifc_models/x.ifc' (may not exist yet)."""
    return os.path.join(FILES, rel)


def available(rel):
    try:
        return PREFIX + rel in index()
    except Exception:
        return False


def fetch(rel, max_bytes=300e6):
    """Return a local path for dataset-relative `rel`, downloading it from the full zip if needed.
    Returns None if the file is not in the full dataset or the download fails."""
    out = local(rel)
    if os.path.exists(out):
        return out
    try:
        info = index().get(PREFIX + rel)
    except Exception:
        return None
    if info is None or info[1] > max_bytes:
        return None
    off, csize, size, ctype = info
    with _lock:
        if os.path.exists(out):
            return out
        try:
            r = requests.get(URL, headers={'Range': f'bytes={off}-{off + 30 + 1024 + csize}'}, timeout=300)
            if r.status_code != 206:
                return None
            blob = r.content
            n, m = struct.unpack('<HH', blob[26:30])
            data = blob[30 + n + m: 30 + n + m + csize]
            if ctype == 8:
                data = zlib.decompress(data, -15)
            if len(data) != size:
                return None
        except Exception:
            return None
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = out + '.part'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, out)
    return out


def read_text(rel):
    p = fetch(rel)
    return open(p, encoding='utf-8', errors='replace').read() if p else None
