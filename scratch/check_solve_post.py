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
    print("Fetching POST /solve response...")
    solve_data = fetch_json_post("http://127.0.0.1:8000/solve")
    if solve_data:
        with open("scratch/solve_response.json", "w", encoding="utf-8") as f:
            json.dump(solve_data, f, indent=2, ensure_ascii=False)
        print("Wrote solve response to scratch/solve_response.json")

    print("\nFetching GET /solve/alternatives response...")
    alts_data = fetch_json_get("http://127.0.0.1:8000/solve/alternatives?n=3")
    if alts_data:
        with open("scratch/alts_response.json", "w", encoding="utf-8") as f:
            json.dump(alts_data, f, indent=2, ensure_ascii=False)
        print("Wrote alternatives response to scratch/alts_response.json")

if __name__ == "__main__":
    main()

