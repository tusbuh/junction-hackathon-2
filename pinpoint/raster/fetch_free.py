"""Fetch the CubiCasa5K plans that are NOT in the Stoa dataset (cubicasa_free_ids.json).

    python -m pinpoint.raster.fetch_free
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pinpoint.raster.download_cubicasa import fetch, index, ROOT

FREE = ROOT / "data/full/cubicasa_free_ids.json"
STOA = ROOT / "data/full/cubicasa_stoa_ids.json"


def main():
    free = json.loads(FREE.read_text())
    stoa = set(json.loads(STOA.read_text()))
    assert not set(free) & stoa
    idx = index()
    todo = [tuple(x.rsplit("-", 1)) for x in free]
    def job(a):
        try:
            return fetch(idx, *a)
        except Exception as e:
            return f"fail {a} {e}"
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(job, todo))
    print({r: res.count(r) for r in set(res) if not r.startswith("fail")},
          [r for r in res if r.startswith("fail")])


if __name__ == "__main__":
    main()
