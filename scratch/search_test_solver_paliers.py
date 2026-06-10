with open('backend/tests/test_solver.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'Node(' in line or 'SchemeNode(' in line:
            # Print next 10 lines
            print(f"Line {i+1}:")
            f.seek(0)
            lines = f.readlines()
            for j in range(i, min(i+10, len(lines))):
                print(f"  {lines[j].strip()}")
