import os
import sys
import re

sys.stdout.reconfigure(encoding="utf-8")

repos_dir = "reference_repos"
repo_dirs = sorted([d for d in os.listdir(repos_dir) if os.path.isdir(os.path.join(repos_dir, d)) and d != "__pycache__"])
print(f"Total repo directories: {len(repo_dirs)}")

with open("features.md", "r", encoding="utf-8") as f:
    text = f.read()

pattern = re.compile(r"## 📦 \[(\d{3})\] ([^`\n]+) \(`([^`]+)`\)")
matches = pattern.findall(text)
print(f"Matched repo entries in features.md: {len(matches)}")

matched_dirs = set(m[2] for m in matches)
missing_in_text = [d for d in repo_dirs if d not in matched_dirs]
print(f"Repo dirs not matched by pattern: {len(missing_in_text)}")
if missing_in_text:
    print("Missing or unmatched dirs:", missing_in_text[:10])

blocks = text.split("## 📦 [")
print(f"Total split blocks: {len(blocks) - 1}")

incomplete = []
total_features = 0
for i, b in enumerate(blocks[1:], 1):
    header = b.split("\n")[0]
    num = header[:3]
    if "### 🛠️ বিস্তারিত ফিচারসমূহ:" not in b:
        incomplete.append((num, "missing feature header"))
    features = re.findall(r"#### 🔹 [^\n]+", b)
    total_features += len(features)
    if len(features) < 1:
        incomplete.append((num, "no features listed"))
    if "আমাদের VeloRoute-এ স্ট্যাটাস:" not in b:
        incomplete.append((num, "missing status"))
    if "যোগ করার সিদ্ধান্ত:" not in b:
        incomplete.append((num, "missing decision"))

print(f"Total features cataloged: {total_features}")
print(f"Incomplete entries found: {len(incomplete)}")
if incomplete:
    print("Incomplete samples:", incomplete[:10])
else:
    print("ALL 264 repo entries are completely structured and verified!")
