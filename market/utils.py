import hashlib


def generate_signature(data, signature_key):
    sorted_data = ''.join([f'{k}={v}' for k, v in sorted(data.items())])
    return hashlib.sha512((sorted_data + signature_key).encode('utf-8')).hexdigest()
