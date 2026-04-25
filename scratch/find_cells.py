import json
from pathlib import Path

notebook_path = Path(r'd:\DATATHON\notebooks\namnn.ipynb')

with open(notebook_path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        source = cell['source']
        if source:
            first_line = source[0].strip()
            print(f"Cell {i} (ID: {cell.get('id')}): {first_line[:50]}")
            if 'PHÂN TÍCH NHÂN KHẨU HỌC' in "".join(source):
                print(f"  --> FOUND DEMOGRAPHIC CELL AT INDEX {i}")
