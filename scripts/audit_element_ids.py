import re
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

# 1. Collect all element IDs defined in templates
all_ids = set()
for root, _, files in os.walk("veloroute/ui/templates"):
    for fname in files:
        if fname.endswith(".html"):
            with open(os.path.join(root, fname), "r", encoding="utf-8") as f:
                content = f.read()
            # find id="..."
            matches = re.findall(r'id=[\'\"]([a-zA-Z0-9_\-]+)[\'\"]', content)
            for m in matches:
                all_ids.add(m)

print(f"Total HTML element IDs defined in templates: {len(all_ids)}")

# 2. Collect all document.getElementById('...') calls in scripts.html
with open("veloroute/ui/templates/pages/scripts.html", "r", encoding="utf-8") as f:
    scripts = f.read()

get_elem_ids = set(re.findall(r'document\.getElementById\([\'\"]([a-zA-Z0-9_\-]+)[\'\"]\)', scripts))
print(f"Total document.getElementById calls in scripts.html: {len(get_elem_ids)}")

missing_ids = [eid for eid in sorted(get_elem_ids) if eid not in all_ids]
print(f"IDs queried in JS but missing in HTML: {len(missing_ids)}")
for eid in missing_ids:
    print(f"  ⚠️ {eid}")

