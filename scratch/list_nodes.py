import urllib.request
import json

try:
    url = "http://localhost:8000/graph"
    response = urllib.request.urlopen(url)
    data = json.loads(response.read())
    nodes = data.get("nodes", [])
    
    descriptives = []
    normatives = []
    for n in nodes:
        if n['type'] in ['descriptif', 'empirique', 'definitionnel']:
            descriptives.append(n)
        elif n['type'] in ['normatif_conclusion', 'normatif_position']:
            normatives.append(n)
            
    print("Descriptive/empirical/definitional nodes:")
    for n in descriptives[:5]:
        print(f"  ID: {n['id']} | Type: {n['type']} | Text: {n['text'][:40]}...")
        
    print("\nNormative position/conclusion nodes:")
    for n in normatives[:5]:
        print(f"  ID: {n['id']} | Type: {n['type']} | Text: {n['text'][:40]}...")
except Exception as e:
    print("Error:", e)
