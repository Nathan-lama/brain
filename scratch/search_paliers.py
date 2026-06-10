import os

search_terms = ['c1', 'c4', 'b1', 'b3', 'ca1', 'ca2']
found = []
for root, dirs, files in os.walk('.'):
    if any(p in root for p in ['.venv', '.next', 'node_modules', '.git', '__pycache__']):
        continue
    for file in files:
        if file.endswith(('.py', '.json')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if any(term in content for term in search_terms):
                        found.append(path)
            except Exception:
                pass

print("Files containing seed/test nodes:", found)
