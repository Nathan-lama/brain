import urllib.request
import json

def fetch_json(url):
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def main():
    print("Fetching /solve response...")
    solve_data = fetch_json("http://127.0.0.1:8000/solve")
    if solve_data:
        print("\n=== /solve raw JSON ===")
        print(json.dumps(solve_data, indent=2, ensure_ascii=False))
        
    print("\nFetching /solve/alternatives response...")
    alts_data = fetch_json("http://127.0.0.1:8000/solve/alternatives?n=3")
    if alts_data:
        print("\n=== /solve/alternatives raw JSON ===")
        print(json.dumps(alts_data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
