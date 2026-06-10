import os

extensions = ('.py', '.ts', '.tsx', '.js')
exclude_dirs = {'.venv', '.next', 'node_modules', '.git', '__pycache__'}

found = []
for root, dirs, files in os.walk('.'):
    # filter out excluded dirs
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for file in files:
        if file.endswith(extensions):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if 'stake' in line.lower():
                            found.append(f"{path}:{i+1}: {line.strip()}")
            except Exception as e:
                # ignore read errors
                pass

for line in found:
    print(line)
