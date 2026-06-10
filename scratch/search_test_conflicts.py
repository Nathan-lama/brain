import os

for root, dirs, files in os.walk('backend/tests'):
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'ca1' in content or 'ca2' in content or 'c4' in content or 'b3' in content:
                    print(f"Match found in: {path}")
                    # Print lines containing these
                    f.seek(0)
                    for i, line in enumerate(f):
                        if any(term in line for term in ['ca1', 'ca2', 'c4', 'b3', 'c1']):
                            print(f"  Line {i+1}: {line.strip()}")
