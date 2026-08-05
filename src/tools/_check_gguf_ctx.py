"""Check native context length from GGUF headers."""
import struct
from pathlib import Path

def read_gguf_metadata(path, keys=None):
    """Read specific metadata keys from a GGUF file."""
    with open(path, 'rb') as f:
        magic = f.read(4)
        if magic != b'GGUF':
            return {}
        _version = struct.unpack('<I', f.read(4))[0]
        _n_tensors = struct.unpack('<Q', f.read(8))[0]
        n_kv = struct.unpack('<Q', f.read(8))[0]
        
        result = {}
        for _ in range(n_kv):
            k_len = struct.unpack('<Q', f.read(8))[0]
            k = f.read(k_len).decode('utf-8').rstrip('\0')
            v_type = struct.unpack('<I', f.read(4))[0]
            
            if v_type == 0:  # UINT8
                v = struct.unpack('<B', f.read(1))[0]
            elif v_type == 1:  # INT8
                v = struct.unpack('<b', f.read(1))[0]
            elif v_type == 2:  # UINT16
                v = struct.unpack('<H', f.read(2))[0]
            elif v_type == 3:  # INT16
                v = struct.unpack('<h', f.read(2))[0]
            elif v_type == 4:  # UINT32
                v = struct.unpack('<I', f.read(4))[0]
            elif v_type == 5:  # INT32
                v = struct.unpack('<i', f.read(4))[0]
            elif v_type == 6:  # FLOAT32
                v = struct.unpack('<f', f.read(4))[0]
            elif v_type == 7:  # BOOL
                v = struct.unpack('<B', f.read(1))[0] != 0
            elif v_type == 8:  # STRING
                s_len = struct.unpack('<Q', f.read(8))[0]
                v = f.read(s_len).decode('utf-8').rstrip('\0')
            elif v_type == 10:  # ARRAY
                arr_len = struct.unpack('<Q', f.read(8))[0]
                v_type_inner = struct.unpack('<I', f.read(4))[0]
                v = f'read {arr_len} items of type {v_type_inner}'
            else:
                v = f'unknown type {v_type}'
            
            if keys is None or k in keys:
                result[k] = v
        
        return result

# Check specific GGUF files
files = [
    r'C:\Users\pskra\.lmstudio\models\noctrex\LFM2-24B-A2B-MXFP4_MOE-GGUF\LFM2-24B-A2B-MXFP4_MOE.gguf',
    r'C:\Users\pskra\.lmstudio\models\unsloth\gemma-4-26B-A4B-it-GGUF\gemma-4-26B-A4B-it-IQ3_S.gguf',
]

for f in files:
    try:
        meta = read_gguf_metadata(f, ['llm.context_length', 'llm.block_count', 'llm.embedding_length'])
        print(f'File: {f.split(chr(92))[-1]}')
        for k, v in meta.items():
            print(f'  {k}: {v}')
        print()
    except Exception as e:
        print(f'Error reading {f}: {e}')
        print()
