import json
from pathlib import Path

notebook_path = Path(r'd:\DATATHON\notebooks\namnn.ipynb')

with open(notebook_path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

cell_1 = nb['cells'][1]
print(f"Cell 1 ID: {cell_1.get('id')}")
print("Cell 1 Source:")
print("".join(cell_1['source']))
