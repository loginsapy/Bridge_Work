from pathlib import Path
s=Path('app/templates/admin_settings.html').read_text(encoding='utf-8', errors='replace')
lines=s.splitlines()
print('Total lines', len(lines))
for i in range(968,976):
    print(i+1, repr(lines[i]))