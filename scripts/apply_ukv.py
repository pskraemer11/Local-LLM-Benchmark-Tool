import sys; sys.path.insert(0, 'src')
from registry_tool import load_registry, save_registry
from benchmark_config import should_use_unified_kv_cache

reg = load_registry()
updated = 0
for rn, re_ in reg.items():
    if not isinstance(re_, dict) or re_.get('blueprint') == 'none':
        continue
    file_size = re_.get('file_size_bytes', 0)
    size_gb = file_size / (1024**3) if file_size else 0
    target = should_use_unified_kv_cache(rn, size_gb)
    if re_.get('useUnifiedKvCache') != target:
        re_['useUnifiedKvCache'] = target
        updated += 1
        print(f'{rn}: {size_gb:.1f} GB -> UKV={target}')

save_registry(reg)
print(f'\nRegistry UKV updated: {updated} entries')
