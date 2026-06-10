import os

search_terms = ['ca2', 'c4', 'b3']
found = []
for root, dirs, files in os.walk('backend/migrations'):
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        for term in search_terms:
                            if term in line.lower():
                                found.append(f"{path}:{i+1}: ({term}) {line.strip()}")
            except Exception:
                pass

for item in found:
    print(item)
