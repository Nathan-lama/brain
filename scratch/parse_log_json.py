import urllib.request
import json

def fetch_json(url):
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    solve = fetch_json("http://127.0.0.1:8000/solve")
    alts = fetch_json("http://127.0.0.1:8000/solve/alternatives?n=3")

    if solve:
        print("=== BASELINE SOLUTION ===")
        print(f"Incoherence Score: {solve.get('incoherence_score')}")
        print(f"Total Score: {solve.get('score')}")
        print("Violated Tensions:")
        for t in solve.get("violated", []):
            print(f"  - ID: {t.get('id')}, Type: {t.get('type')}, Score: {t.get('score')}, Poids: {t.get('poids')}, Scheme: {t.get('scheme_id')}")
            for c in t.get("claims", []):
                print(f"    * Claim: {c.get('id')} -> {c.get('text')}")
            for p in t.get("ponts", []):
                print(f"    * Pont: {p.get('id')} -> {p.get('text')}")

    if alts:
        print("\n=== ALTERNATIVE SOLUTIONS ===")
        for alt in alts:
            print(f"\nAlternative #{alt.get('solution_index')}:")
            print(f"  Incoherence Score: {alt.get('incoherence_score')}")
            print(f"  Arbitrated Tensions:")
            for t in alt.get("arbitrated_tensions", []):
                print(f"    - ID: {t.get('id')}, Type: {t.get('type')}, Score: {t.get('score')}, Poids: {t.get('poids')}, Scheme: {t.get('scheme_id')}")
                for c in t.get("claims", []):
                    print(f"      * Claim: {c.get('id')} -> {c.get('text')}")
                for p in t.get("ponts", []):
                    print(f"      * Pont: {p.get('id')} -> {p.get('text')}")

if __name__ == "__main__":
    main()
