with open('backend/tests/test_prompt10.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if any(term in line for term in ['ca1', 'ca2', 'c4', 'b3', 'c1', 'conflict', 'conflit']):
            print(f"Line {i+1}: {line.strip()}")
