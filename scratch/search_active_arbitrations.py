with open('frontend/src/app/graph/page.tsx', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'activearbitratedtensions' in line.lower():
            print(f"Line {i+1}: {line.strip()}")
