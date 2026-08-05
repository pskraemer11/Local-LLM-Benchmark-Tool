"""Check context_length values for specific models."""
import yaml

with open('doc-git/model_registry.yaml', encoding='utf-8') as f:
    reg = yaml.safe_load(f)

for key in ['noctrex/lfm2-24b-a2b_moe', 'unsloth/gemma-4-26b-a4b-it@iq3_s']:
    entry = reg.get(key, {})
    print(key + ':')
    print('  context_length:', entry.get('context_length'))
    print('  max_context_length:', entry.get('max_context_length'))
    print()
