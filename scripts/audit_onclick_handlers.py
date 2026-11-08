import re
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

onclicks = set()
for root, _, files in os.walk("veloroute/ui/templates/pages"):
    for fname in files:
        if fname.endswith(".html"):
            with open(os.path.join(root, fname), "r", encoding="utf-8") as f:
                content = f.read()
            matches = re.findall(r"onclick=[\'\"]([a-zA-Z0-9_]+)\(", content)
            for m in matches:
                if m not in {"if", "for", "while", "switch", "return"}:
                    onclicks.add(m)

print(f"Total onclick functions found in templates: {len(onclicks)}")

with open("veloroute/ui/templates/pages/scripts.html", "r", encoding="utf-8") as f:
    scripts = f.read()

# Match function declarations
funcs = re.findall(r"(?:function|async\s+function)\s+([a-zA-Z0-9_]+)\s*\(", scripts)
# Match window assignments
win_assigns = re.findall(r"window\.([a-zA-Z0-9_]+)\s*=", scripts)
# Match arrow functions / expressions
var_funcs = re.findall(r"(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\(", scripts)

all_defs = set(funcs) | set(win_assigns) | set(var_funcs)
print(f"Total script function definitions found: {len(all_defs)}")

missing_handlers = [fn for fn in sorted(onclicks) if fn not in all_defs]
print(f"Missing onclick handlers: {len(missing_handlers)}")
for fn in missing_handlers:
    print(f"  ❌ {fn}")
if not missing_handlers:
    print("✅ All onclick handlers in templates are implemented!")
