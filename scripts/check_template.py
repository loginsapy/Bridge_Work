from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError
p='c:/Users/david/Proyectos/BridgeWork-Recuperar/app/templates'
env=Environment(loader=FileSystemLoader(p))
try:
    env.get_template('admin_settings.html')
    print('Parsed OK')
except TemplateSyntaxError as e:
    print('TemplateSyntaxError:', e, 'line', e.lineno)
except Exception as e:
    print('Error:', e)