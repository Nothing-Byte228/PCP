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

def compile_library(output_dll, files_map, main_script_name, requirements, current_py_version):
    csc_executable = get_csc_path()
    reqs_formatted = ", ".join([f'"{req}"' for req in requirements])

    dict_elements = []
    for fname, base64_stub in files_map.items():
        dict_elements.append(f'{{ "{fname}", "{base64_stub}" }}')
    dict_placeholder = ",\n            ".join(dict_elements)

    # Форматируем шаблон библиотеки
    csharp_code = LIBRARY_TEMPLATE.replace("[FILES_DICTIONARY_PLACEHOLDER]", dict_placeholder)
    csharp_code = csharp_code.replace("[MAIN_SCRIPT_NAME]", main_script_name)
    csharp_code = csharp_code.replace("[REQUIREMENTS_PLACEHOLDER]", reqs_formatted)
    
    # Зашиваем СТРОГУЮ целевую версию для этой конкретной DLL (например, "3.13")
    csharp_code = csharp_code.replace("[TARGET_VERSION]", current_py_version) 

    with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", encoding="utf-8", delete=False) as temp_file:
        temp_file.write(csharp_code)
        temp_source_path = temp_file.name

    cmd = [csc_executable, "/target:library", "/optimize", "/r:System.Windows.Forms.dll", f"/out:{output_dll}", temp_source_path]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(temp_source_path):
        os.remove(temp_source_path)

    return result.returncode == 0 and os.path.exists(output_dll)

def get_obfuscated_code_from_target(target_python, script_path):
    """Запускает целевой интерпретатор Python для генерации обфусцированного стаба"""
    macro = f"""
import sys, base64
sys.path.append(r'{os.path.dirname(os.path.abspath(__file__))}')
from obfuscate import obfuscate_code
with open(r'{os.path.abspath(script_path)}', 'r', encoding='utf-8') as f:
    code = f.read()
_, _, stub = obfuscate_code(code)
print(base64.b64encode(stub.encode('utf-8')).decode('utf-8'))
"""
    cmd = target_python.split() if " " in target_python else [target_python]
    cmd.extend(["-c", macro])
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return result.stdout.strip()