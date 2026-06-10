import json
import os

for fname in ['scratch/solve_response.json', 'scratch/alts_response.json']:
    if os.path.exists(fname):
        print("=== File:", fname)
        with open(fname, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # if it's a list or dict
            if isinstance(data, dict):
                violated = data.get('violated_constraints', [])
                arbitrated = data.get('arbitrated_tensions', [])
                print("  Violated constraints count:", len(violated))
                print("  Arbitrated tensions count:", len(arbitrated))
                for t in arbitrated:
                    print(f"    Tension ID: {t.get('id')} | Scheme: {t.get('scheme_id')} | Kept: {t.get('kept_node', {}).get('label_court')} | Discarded: {t.get('discarded_node', {}).get('label_court')} | Score: {t.get('stake_score')}")
            elif isinstance(data, list):
                print("  List length:", len(data))
                for idx, item in enumerate(data):
                    arbitrated = item.get('arbitrated_tensions', [])
                    print(f"    Item {idx} arbitrated tensions count:", len(arbitrated))
                    for t in arbitrated:
                        print(f"      Tension ID: {t.get('id')} | Scheme: {t.get('scheme_id')} | Kept: {t.get('kept_node', {}).get('label_court')} | Discarded: {t.get('discarded_node', {}).get('label_court')} | Score: {t.get('stake_score')}")
