from pathlib import Path
s=Path('app/templates/admin_settings.html').read_text(encoding='utf-8', errors='replace')
lines=s.splitlines()
ln=973-1
line=lines[ln]
print('Line len',len(line))
print(line)
for i,ch in enumerate(line):
    print(i, ch, ord(ch))
