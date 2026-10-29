import os, json
root = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dataset')
counts = {}
for name in sorted(os.listdir(root)):
    p = os.path.join(root, name)
    if os.path.isdir(p):
        files = [f for f in os.listdir(p) if os.path.isfile(os.path.join(p, f))]
        counts[name] = len(files)
print(json.dumps(counts, indent=2))
