import json
from pathlib import Path

cfg_dir = Path.home() / '.lmstudio' / '.internal' / 'user-concrete-model-default-config'
for p in cfg_dir.rglob('*.json'):
    if '.bak' in str(p):
        continue
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        load_fields = data.get('load', {}).get('fields', [])
        for f in load_fields:
            if f.get('key') == 'llm.load.numParallelSessions' and f.get('value') == 4:
                keys = [(f['key'].split('.')[-1], f['value']) for f in load_fields]
                print(f'Example: {p.name}')
                print(f'  load.fields: {keys}')
                raise StopIteration
    except StopIteration:
        break
    except Exception:
        pass
