import urllib.request
import urllib.parse
import json

payload = {
  "nodes": [],
  "scheme_nodes": [
    {
      "id": "a5555555-5555-5555-5555-555555555555",
      "scheme": "inference",
      "premises": [
        "d1111111-1111-1111-1111-111111111111",
        "d2222222-2222-2222-2222-222222222222"
      ],
      "conclusion": "c1111111-1111-1111-1111-111111111111",
      "strength": "defaisable_faible"
    }
  ]
}

def request(url, data=None, method="GET"):
    req_data = None
    if data is not None:
        req_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

print("=== 1. Blocked Import Check (allow_hume_violations=false) ===")
status, res = request("http://localhost:8000/import", payload, method="POST")
print("Status:", status)
print("Response:", json.dumps(res, indent=2))

print("\n=== 2. Allowed Import Check (allow_hume_violations=true) ===")
status, res = request("http://localhost:8000/import?allow_hume_violations=true", payload, method="POST")
print("Status:", status)
print("Response:", json.dumps(res, indent=2))

print("\n=== 3. Validate Hume (Expect count=1) ===")
status, res = request("http://localhost:8000/validate/hume")
print("Status:", status)
print("Response:", json.dumps(res, indent=2))

print("\n=== 4. Delete Violating Inference (scheme_id: a5555555-5555-5555-5555-555555555555) ===")
status, res = request("http://localhost:8000/edges/a5555555-5555-5555-5555-555555555555", method="DELETE")
print("Status:", status)
print("Response:", json.dumps(res, indent=2))

print("\n=== 5. Re-validate Hume (Expect count=0) ===")
status, res = request("http://localhost:8000/validate/hume")
print("Status:", status)
print("Response:", json.dumps(res, indent=2))
