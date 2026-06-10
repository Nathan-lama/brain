import urllib.request
import json

def fetch_json_post(url):
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error POST {url}: {e}")
        return None

def fetch_json_get(url):
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error GET {url}: {e}")
        return None

def main():
    solve = fetch_json_post("http://127.0.0.1:8000/solve")
    alts = fetch_json_get("http://127.0.0.1:8000/solve/alternatives?n=3")

    if solve:
        print("=== BASELINE POST /solve ===")
        print(f"incoherence_score: {solve.get('incoherence_score')}")
        print("violated list:")
        for t in solve.get("violated", []):
            print(f"  - ID: {t.get('id')}, Type: {t.get('type')}, Score: {t.get('score')}, Poids: {t.get('poids')}, Scheme ID: {t.get('scheme_id')}")

    if alts:
        print("\n=== ALTERNATIVES GET /solve/alternatives ===")
        for alt in alts:
            print(f"Alternative #{alt.get('solution_index')}:")
            print(f"  incoherence_score: {alt.get('incoherence_score')}")
            print("  arbitrated_tensions list:")
            for t in alt.get("arbitrated_tensions", []):
                print(f"    - ID: {t.get('id')}, Type: {t.get('type')}, Score: {t.get('score')}, Poids: {t.get('poids')}, Scheme ID: {t.get('scheme_id')}")

if __name__ == "__main__":
    main()
