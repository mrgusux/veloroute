import re
import os
import sys
from veloroute.ui.app import app

sys.stdout.reconfigure(encoding="utf-8")

def extract_routes(obj):
    r_list = []
    routes = getattr(obj, "routes", [])
    for r in routes:
        if hasattr(r, "path"):
            m = getattr(r, "methods", None)
            m_tuple = tuple(sorted(m)) if m else ()
            r_list.append((r.path, m_tuple))
        if hasattr(r, "original_router"):
            r_list.extend(extract_routes(r.original_router))
    return r_list

routes = extract_routes(app)
route_paths = [r[0] for r in routes]
print(f"Total registered FastAPI route paths: {len(route_paths)}")

templates_dir = "veloroute/ui/templates"
fetches = set()

for root, _, files in os.walk(templates_dir):
    for fname in files:
        if fname.endswith(".html"):
            fpath = os.path.join(root, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # find fetch('/...') or fetch(`/...`) or $.ajax or axios
            matches = re.findall(r'fetch\(\s*[\'`"](/[^?`\'"]+)', content)
            for m in matches:
                fetches.add(m)

print(f"Total unique fetch endpoints found in templates: {len(fetches)}")

missing = []
for ep in sorted(fetches):
    matched = False
    for rp in route_paths:
        pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", rp) + "$"
        if re.match(pattern, ep):
            matched = True
            break
    if not matched:
        missing.append(ep)

print(f"Missing endpoints: {len(missing)}")
for m in missing:
    print(f"  ❌ {m}")
if not missing:
    print("✅ All template fetch endpoints are 100% matched to valid FastAPI routes!")
