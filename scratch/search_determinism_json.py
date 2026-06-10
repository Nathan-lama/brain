import json

with open('determinism.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    
    print("Nodes in json:")
    for n in nodes:
        meta = n.get('metadata', {})
        imported_id = meta.get('imported_id')
        node_type = meta.get('type')
        tier = meta.get('tier')
        print(f"  ID: {n['id']} | Text: {n.get('text', '')[:40]} | Type: {node_type} | Tier: {tier} | Metadata: {meta}")
        
    print("\nEdges in json:")
    for e in edges:
        print(e)
