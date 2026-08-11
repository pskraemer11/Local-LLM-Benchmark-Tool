import sys; sys.path.insert(0, 'src')
import registry_tool as rt
from model_identity import normalize_model_name

reg = rt.load_registry()

# Find base entries (without @) that have @quant variants
to_remove = []
for rn, re_ in list(reg.items()):
    if "@" not in rn:
        base = normalize_model_name(rn)
        # Check if any @quant variant exists
        has_variant = any(
            "@" in other and normalize_model_name(other).split("@")[0] == base
            for other in reg if other != rn
        )
        if has_variant:
            to_remove.append(rn)

print(f"Zu entfernende Base-Eintraege ({len(to_remove)}):")
for rn in to_remove:
    print(f"  {rn} ({reg[rn].get('file_size_bytes', 0)/1e6:.1f} MB)")
    del reg[rn]

if to_remove:
    rt.save_registry(reg)
    print(f"\nRegistry bereinigt: {len(reg)} Eintraege verbleiben")
else:
    print("\nKeine Base-Eintraege zum Entfernen gefunden.")
