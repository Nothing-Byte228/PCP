import base64
import marshal
import secrets

def obfuscate_code(optimized_code: str) -> tuple[str, str, str]:
    """
    Шифрует исходный текст Python-кода.
    Возвращает кортеж: (base64_payload, base64_key, runtime_stub)
    """
    # 1. Компилируем оптимизированный текст в бинарный байт-код Python
    # compile() создает объект кода, marshal.dumps() переводит его в байты (.pyc формат)
    bytecode = marshal.dumps(compile(optimized_code, "<pcp_runtime>", "exec"))

    # 2. Генерируем случайный 16-байтовый криптографический ключ
    xor_key = secrets.token_bytes(16)
    
    # 3. Шифруем байт-код методом XOR
    encrypted_bytecode = bytearray()
    for i in range(len(bytecode)):
        encrypted_bytecode.append(bytecode[i] ^ xor_key[i % len(xor_key)])
    
    # 4. Переводим зашифрованные байты и ключ в Base64 для безопасного хранения в строках
    base64_payload = base64.b64encode(encrypted_bytecode).decode("utf-8")
    base64_key = base64.b64encode(xor_key).decode("utf-8")
    
    # 5. Генерируем микро-загрузчик, который выполнит этот пирог прямо в памяти
    runtime_stub = f"""import base64, marshal
k = base64.b64decode(b'{base64_key}')
d = base64.b64decode(b'{base64_payload}')
b = bytearray()
for i in range(len(d)):
    b.append(d[i] ^ k[i % len(k)])
exec(marshal.loads(bytes(b)))
"""
    
    return base64_payload, base64_key, runtime_stub


# === ТЕСТ БЛОК ===
if __name__ == "__main__":
    my_secret_code = "print('Hello, secure world!')"
    
    # Обфусцируем
    payload, key, stub = obfuscate_code(my_secret_code)
    
    print("--- ЗАШИФРОВАННЫЙ PAYLOAD (Base64) ---")
    print(payload)
    print("\n--- СЛУЧАЙНЫЙ КЛЮЧ (Base64) ---")
    print(key)
    print("\n--- ЧТО БУДЕТ ЗАПИСАНО ВО ВРЕМЕННЫЙ ФАЙЛ LAUNCHER-ОМ ---")
    print(stub)
