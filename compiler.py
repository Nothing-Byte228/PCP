import os
import sys
import tempfile
import subprocess
from templates_cs import LAUNCHER_TEMPLATE, LIBRARY_TEMPLATE

def get_csc_path():
    csc_path = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if not os.path.exists(csc_path):
        csc_path = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
    if not os.path.exists(csc_path):
        print("\033[91m:: Error: .NET Framework compiler (csc.exe) not found.\033[0m")
        sys.exit(1)
    return csc_path

def compile_launcher(output_exe, base_name, min_version, windowed):
    """Компилирует универсальный исполняемый файл-оболочку .exe"""
    csc_executable = get_csc_path()
    
    # Форматируем шаблон лаунчера
    csharp_code = LAUNCHER_TEMPLATE.replace("[BASE_NAME]", base_name)
    csharp_code = csharp_code.replace("[MIN_VERSION]", min_version)
    csharp_code = csharp_code.replace("[WINDOWED_FLAG]", str(windowed).lower())

    with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", encoding="utf-8", delete=False) as temp_file:
        temp_file.write(csharp_code)
        temp_source_path = temp_file.name

    target_type = "/target:winexe" if windowed else "/target:exe"
    cmd = [csc_executable, target_type, "/optimize", "/r:System.Windows.Forms.dll", f"/out:{output_exe}", temp_source_path]

    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(temp_source_path):
        os.remove(temp_source_path)

    if result.returncode == 0 and os.path.exists(output_exe):
        print(f"\033[92m:: Launcher Executable created -> {os.path.basename(output_exe)} ({os.path.getsize(output_exe)/1024:.1f} KB)\033[0m")
        return True
    return False

def compile_library(output_dll, base64_runtime_code, requirements, min_version):
    """Компилирует защищенную динамическую библиотеку .dll (/target:library)"""
    csc_executable = get_csc_path()
    reqs_formatted = ", ".join([f'"{req}"' for req in requirements])

    # Форматируем шаблон библиотеки
    csharp_code = LIBRARY_TEMPLATE.replace("[BASE64_RUNTIME_CODE]", base64_runtime_code)
    csharp_code = csharp_code.replace("[REQUIREMENTS_PLACEHOLDER]", reqs_formatted)
    csharp_code = csharp_code.replace("[MIN_VERSION]", min_version)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", encoding="utf-8", delete=False) as temp_file:
        temp_file.write(csharp_code)
        temp_source_path = temp_file.name

    # Ключевой флаг компиляции под динамическую библиотеку: /target:library
    cmd = [csc_executable, "/target:library", "/optimize", "/r:System.Windows.Forms.dll", f"/out:{output_dll}", temp_source_path]

    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(temp_source_path):
        os.remove(temp_source_path)

    if result.returncode == 0 and os.path.exists(output_dll):
        print(f"\033[92m:: Protected Code Library created -> {os.path.basename(output_dll)} ({os.path.getsize(output_dll)/1024:.1f} KB)\033[0m")
        return True
    return False

def get_obfuscated_code_from_target(target_python, script_path):
    """
    Запускает целевой интерпретатор Python, чтобы он сам скомпилировал 
    совместимый с ним байт-код и прогнал его через обфускатор.
    """
    import subprocess
    import os
    import sys
    
    # Скрипт-макрос, который выполнится внутри целевого Python
    macro = f"""
import sys, base64
sys.path.append(r'{os.path.dirname(os.path.abspath(__file__))}')
from obfuscate import obfuscate_code
with open(r'{os.path.abspath(script_path)}', 'r', encoding='utf-8') as f:
    code = f.read()
_, _, stub = obfuscate_code(code)
print(base64.b64encode(stub.encode('utf-8')).decode('utf-8'))
"""
    # Разносим команду в массив, если там есть пробелы (например, "py -3.11")
    cmd = target_python.split() if " " in target_python else [target_python]
    cmd.extend(["-c", macro])
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return result.stdout.strip()
