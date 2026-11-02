"""Run against a real HTTP server and save auditable responses. Stdlib only."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8080")
parser.add_argument("--output", default="evidence/http-smoke.json")
args = parser.parse_args()
records = []
for method, path, payload, expected in [
    ("GET", "/health/live", None, 200),
    ("GET", "/health/ready", None, 200),
    ("GET", "/v1/model", None, 200),
    ("GET", "/openapi.json", None, 200),
    ("POST", "/v1/predict", json.loads((ROOT / "examples/predict.json").read_text()), 200),
    ("POST", "/v1/predict", {"instances": []}, 422),
]:
    req = Request(args.url + path, data=None if payload is None else json.dumps(payload).encode(),
                  method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as response:
            status, body = response.status, json.load(response)
    except HTTPError as error:
        status, body = error.code, json.load(error)
    records.append({"method": method, "path": path, "status": status, "expected": expected,
                    "passed": status == expected, "response": body})
out = ROOT / args.output
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "base_url": args.url,
                           "passed": all(r["passed"] for r in records), "requests": records}, indent=2), encoding="utf-8")
print(f"HTTP smoke: {sum(r['passed'] for r in records)}/{len(records)}; evidence={out}")
if not all(r["passed"] for r in records): raise SystemExit(1)
