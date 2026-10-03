import os
import sys
import base64
import argparse
import subprocess
from obfuscate import obfuscate_code
from compiler import compile_launcher, compile_library, get_obfuscated_code_from_target

def main():
    parser = argparse.ArgumentParser(description="PCP: Python Code Packer (Modular Enterprise Architecture)")
    parser.add_argument("script", help="Path to the main Python script")
    parser.add_argument("-o", "--output", default="./dist/app.exe", help="Output execution file baseline path")
    parser.add_argument("-r", "--reqs", nargs="*", default=[], help="Modules to check/install via pip")
    parser.add_argument("-w", "--windowed", action="store_true", help="Hide console window (GUI mode, uses pythonw)")
    parser.add_argument("--mode", choices=["all", "exe-only", "dll-only"], default="all", 
                        help="Build configuration mode (default: all - generates both runner and version library)")
    parser.add_argument("--py", default=None, 
                        help="Specify target Python version (e.g., 311, 3.11) or full path to python.exe for cross-compilation")

    args = parser.parse_args()

    if not os.path.exists(args.script):
        print(f"\033[91m:: Error: Source script '{args.script}' not found!\033[0m")
        sys.exit(1)

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    base_name, _ = os.path.splitext(os.path.basename(args.output))

    # === АВТООПРЕДЕЛЕНИЕ И ОРАБОТКА ЦЕЛЕВОГО ИНТЕРПРЕТАТOРА ===
    target_python_exe = "python"
    py_ver_major = sys.version_info.major
    py_ver_minor = sys.version_info.minor

    if args.py:
        if os.path.exists(args.py) and args.py.endswith(".exe"):
            # Если передан прямой путь к python.exe
            target_python_exe = args.py
            try:
                version_out = subprocess.check_output(
                    [target_python_exe, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], 
                    text=True
                ).strip()
                py_ver_major, py_ver_minor = map(int, version_out.split("."))
            except Exception:
                print(f"\033[33m>> Warning: Could not verify version of '{args.py}'. Using current host runtime.\033[0m")
        else:
            # Если передана строка вида "311" или "3.11"
            clean_ver = args.py.replace(".", "")
            if len(clean_ver) >= 2:
                py_ver_major = int(clean_ver[0])
                py_ver_minor = int(clean_ver[1:])
                # Формируем стандартную команду для Windows-лаунчера 'py'
                target_python_exe = f"py -{py_ver_major}.{py_ver_minor}"

    min_version_str = f"{py_ver_major}.{py_ver_minor}"
    postfix_str = f"-cpython{py_ver_major}{py_ver_minor}"

    # Формируем финальные пути сборки
    final_exe_path = os.path.join(output_dir, f"{base_name}.exe") if output_dir else f"{base_name}.exe"
    final_dll_path = os.path.join(output_dir, f"{base_name}{postfix_str}.dll") if output_dir else f"{base_name}{postfix_str}.dll"

    print(f"\033[96m:: PCP [Modular Edition]: Starting build pipes for {os.path.basename(args.script)}...\033[0m")

    # Слой 1. Сборка DLL и запуск обфускации через нужный интерпретатор
    base64_runtime_code = ""
    if args.mode in ["all", "dll-only"]:
        print(f"\033[94m>> Compiling bytecode using target engine: '{target_python_exe}'...\033[0m")
        try:
            # Вызываем функцию кросс-компиляции из compiler.py
            base64_runtime_code = get_obfuscated_code_from_target(target_python_exe, args.script)
        except Exception as e:
            print(f"\033[91m:: Obfuscation pipeline crash: {e}\033[0m")
            sys.exit(1)

    # Слой 2. Сборка модулей C#
    success = True

    if args.mode in ["all", "exe-only"]:
        if not compile_launcher(final_exe_path, base_name, min_version_str, args.windowed):
            success = False

    if args.mode in ["all", "dll-only"]:
        if not compile_library(final_dll_path, base64_runtime_code, args.reqs, min_version_str):
            success = False

    if success:
        print("\033[92m:: Multi-component pipeline build task accomplished successfully!\033[0m")
    else:
        print("\033[91m:: Component build pipeline failed.\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
