from pathlib import Path
s=Path('app/templates/admin_settings.html').read_text(encoding='utf-8', errors='replace')
print('ifs', s.count('{% if'), 'endifs', s.count('{% endif'), 'fors', s.count('{% for'), 'endfors', s.count('{% endfor'))
lines=s.splitlines()
for i in range(960,980):
    print(i+1, lines[i])