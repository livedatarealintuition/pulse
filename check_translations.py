#!/usr/bin/env python3
"""Translation completeness check for Pulse (free version).
Run from the project root. Returns 0 if all OK, 1 if missing keys."""
import re, sys

with open('pulse_free.py') as f:
    code = f.read()

# Extract TRANSLATIONS dict
start = code.find('TRANSLATIONS = {')
depth = 0
for i in range(start, len(code)):
    if code[i] == '{': depth += 1
    elif code[i] == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break
exec('trans = ' + code[start+len('TRANSLATIONS = '):end])

# Extract all {{ t.xxx }} from template
template_keys = set(re.findall(r'\{\{\s*t\.(\w+)\s*\}\}', code))
# Extract t["xxx"] patterns
py_keys = set(re.findall(r't\["(\w+)"\]', code))
py_keys |= set(re.findall(r"t\['(\w+)'\]", code))
all_keys = template_keys | py_keys

errors = 0
for key in sorted(all_keys):
    missing = []
    for lang in ['zh_tw', 'zh_cn', 'en']:
        if key not in trans.get(lang, {}):
            missing.append(lang)
    if missing:
        print(f"MISSING: '{key}' in {missing}")
        errors += 1

for key in sorted(all_keys):
    count = sum(1 for lang in ['zh_tw', 'zh_cn', 'en'] if key in trans.get(lang, {}))
    if count != 3:
        print(f"INCOMPLETE: '{key}' — {count}/3 languages")
        errors += 1

if errors:
    print(f"\n{errors} issue(s) found. {len(all_keys)} keys checked.")
    sys.exit(1)
else:
    print(f"All OK — {len(all_keys)} keys, 3 languages each")
