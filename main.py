# main.py
import os
import sys
import base64
import argparse
import subprocess
import winreg  # Используем встроенную библиотеку Windows для работы с реестром
from compiler import compile_launcher, compile_library, get_obfuscated_code_from_target


def find_local_python_runtimes():
    """
    Сканирует реестр Windows и системное окружение,
    чтобы найти все установленные интерпретаторы Python на машине разработчика.
    Возвращает словарь вида: {"311": "C:\\Python311\\python.exe"}
    """
    runtimes = {}

    # 1. Проверяем дефолтную команду 'python' в PATH
    try:
        version_out = subprocess.check_output(
            [
                "python",
                "-c",
                "import sys, os; print(f'{sys.version_info.major}{sys.version_info.minor}|{sys.executable}')",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if "|" in version_out:
            ver_str, exe_path = version_out.split("|")
            runtimes[ver_str] = exe_path
    except Exception:
        pass

    # 2. Сканируем ветки реестра (CurrentUser и LocalMachine)
    reg_paths = [
        r"Software\Python\PythonCore",
        r"Software\WOW6432Node\Python\PythonCore",
    ]
    hives = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]

    for reg_path in reg_paths:
        for hive in hives:
            try:
                with winreg.OpenKey(hive, reg_path) as key:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                    for i in range(num_subkeys):
                        ver_name = winreg.EnumKey(key, i)
                        # Отрезаем суффиксы вроде "-arm64" или "-32", убираем точки
                        clean_ver = ver_name.split("-")[0].replace(".", "")
                        if clean_ver in runtimes:
                            continue

                        try:
                            install_path_str = rf"{reg_path}\{ver_name}\InstallPath"
                            with winreg.OpenKey(hive, install_path_str) as install_key:
                                exe_dir = winreg.QueryValueEx(install_key, "")[0]
                                full_exe_path = os.path.join(exe_dir, "python.exe")
                                if os.path.exists(fullExePath := full_exe_path):
                                    runtimes[clean_ver] = fullExePath
                        except Exception:
                            pass
            except Exception:
                pass

    return runtimes


def get_python_version_info(target_python):
    """Безопасно вытягивает мажорную и минорную версию рантайма"""
    try:
        cmd = target_python.split() if " " in target_python else [target_python]
        version_out = subprocess.check_output(
            cmd
            + [
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            text=True,
        ).strip()
        major, minor = map(int, version_out.split("."))
        return major, minor
    except Exception:
        return sys.version_info.major, sys.version_info.minor


def build_pipeline(
    main_script,
    additional_files,
    output_exe_path,
    mode,
    target_python,
    reqs,
    windowed,
    build_exe=True,
):
    """
    Основной пайплайн сборки.
    Флаг build_exe позволяет пропустить сборку .exe, если мы просто генерируем дополнительные .dll
    """
    base_name, _ = os.path.splitext(os.path.basename(output_exe_path))
    output_dir = os.path.dirname(output_exe_path)

    py_ver_major, py_ver_minor = get_python_version_info(target_python)
    min_version_str = f"{py_ver_major}.{py_ver_minor}"
    postfix_str = f"-cpython{py_ver_major}{py_ver_minor}"

    final_exe_path = (
        os.path.join(output_dir, f"{base_name}.exe")
        if output_dir
        else f"{base_name}.exe"
    )
    final_dll_path = (
        os.path.join(output_dir, f"{base_name}{postfix_str}.dll")
        if output_dir
        else f"{base_name}{postfix_str}.dll"
    )

    print(
        f"\033[96m:: PCP: Compiling blueprint for Python {min_version_str} -> {os.path.basename(final_dll_path)}...\033[0m"
    )

    # 1. Собираем стабы всех нужных файлов в один мешок
    files_map = {}

    # Кодируем главный скрипт
    try:
        main_stub_b64 = get_obfuscated_code_from_target(target_python, main_script)
        files_map[os.path.basename(main_script)] = main_stub_b64
    except Exception as e:
        print(
            f"\033[91m:: Obfuscation failed for {main_script} under Python {min_version_str}: {e}\033[0m"
        )
        return False

    # Если режим multi, пакуем в этот же мешок все остальные зависимые модули
    if mode == "multi":
        for add_file in additional_files:
            if not os.path.exists(add_file):
                print(
                    f"\033[33m>> Warning: Dependent module '{add_file}' not found, skipping.\033[0m"
                )
                continue
            try:
                sub_stub_b64 = get_obfuscated_code_from_target(target_python, add_file)
                files_map[os.path.basename(add_file)] = sub_stub_b64
            except Exception as e:
                print(
                    f"\033[91m:: Obfuscation failed for submodule {add_file} under Python {min_version_str}: {e}\033[0m"
                )
                return False

    # 2. Вызываем компиляцию C# компонентов
    success = True
    if build_exe:
        if not compile_launcher(final_exe_path, base_name, min_version_str, windowed):
            success = False

    if not compile_library(
        final_dll_path, files_map, os.path.basename(main_script), reqs, min_version_str
    ):
        success = False

    return success


def main():
    parser = argparse.ArgumentParser(
        description="PCP: Python Code Packer (C# Multi-Engine Pipeline)"
    )
    parser.add_argument("scripts", nargs="+", help="Python scripts path configuration")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output target baseline path (or base directory)",
    )
    parser.add_argument(
        "-r", "--reqs", nargs="*", default=[], help="Modules to check/install via pip"
    )
    parser.add_argument(
        "-w", "--windowed", action="store_true", help="Hide console window (GUI mode)"
    )
    parser.add_argument(
        "--mode",
        choices=["batch", "multi"],
        default="batch",
        help="batch: each file compiled to standalone app pair; multi: bundle all files inside single package",
    )
    parser.add_argument(
        "--all-py",
        action="store_true",
        help="Automatically scan system and generate DLLs for ALL installed Python versions",
    )
    parser.add_argument(
        "--py",
        default="python",
        help="Specify single target Python path/version engine (ignored if --all-py is set)",
    )

    args = parser.parse_args()

    if not args.scripts:
        print("\033[91m:: Error: No input scripts specified.\033[0m")
        sys.exit(1)

    # Обработка дефолтных путей вывода
    output_baseline = args.output
    if not output_baseline:
        output_baseline = "./dist/app.exe" if args.mode == "multi" else "./dist/"

    # Определяем пул движков для сборки
    target_engines = {}
    if args.all_py:
        print(
            "\033[94m[*] Scanning system registry for installed Python engines...\033[0m"
        )
        target_engines = find_local_python_runtimes()
        if not target_engines:
            print(
                "\033[33m>> Warning: No Python installations found in registry. Falling back to default 'python'.\033[0m"
            )
            target_engines["default"] = "python"
        else:
            print(
                f"\033[92m[+] Found {len(target_engines)} Python runtimes: {', '.join(target_engines.keys())}\033[0m"
            )
    else:
        # Если передан конкретный алиас или путь
        engine_path = args.py
        if args.py and not os.path.exists(args.py) and not args.py.startswith("python"):
            clean_ver = args.py.replace(".", "")
            if len(clean_ver) >= 2:
                engine_path = f"py -{clean_ver[0]}.{clean_ver[1:]}"
        target_engines["custom"] = engine_path

    print(
        f"\033[95m[*] PCP Compiler Active [Mode: {args.mode}] [Total target engines: {len(target_engines)}]\033[0m"
    )

    # Исполнение режимов
    if args.mode == "batch":
        global_success = True
        for script in args.scripts:
            if not os.path.exists(script):
                print(f"\033[91m:: Error: Script '{script}' not found!\033[0m")
                continue

            if (
                output_baseline.endswith("/")
                or output_baseline.endswith("\\\\")
                or os.path.isdir(output_baseline)
            ):
                base_name, _ = os.path.splitext(os.path.basename(script))
                current_output = os.path.join(output_baseline, f"{base_name}.exe")
            else:
                current_output = output_baseline

            out_dir = os.path.dirname(current_output)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            # Для каждого файла генерируем ОДИН .exe лаунчер, но МНОГО .dll (если активен --all-py)
            is_first_engine = True
            for eng_name, eng_exe in target_engines.items():
                if not build_pipeline(
                    script,
                    [],
                    current_output,
                    "batch",
                    eng_exe,
                    args.reqs,
                    args.windowed,
                    build_exe=is_first_engine,
                ):
                    global_success = False
                is_first_engine = False  # exe создается только один раз

        if global_success:
            print("\033[92m:: All batch components built successfully!\033[0m")
        else:
            sys.exit(1)

    elif args.mode == "multi":
        main_script = args.scripts[0]
        additional_modules = args.scripts[1:]

        if not os.path.exists(main_script):
            print(f"\033[91m:: Error: Main script '{main_script}' not found!\033[0m")
            sys.exit(1)

        if (
            output_baseline.endswith("/")
            or output_baseline.endswith("\\\\")
            or os.path.isdir(output_baseline)
        ):
            base_name, _ = os.path.splitext(os.path.basename(main_script))
            output_baseline = os.path.join(output_baseline, f"{base_name}.exe")

        out_dir = os.path.dirname(output_baseline)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        global_success = True
        is_first_engine = True
        for eng_name, eng_exe in target_engines.items():
            if not build_pipeline(
                main_script,
                additional_modules,
                output_baseline,
                "multi",
                eng_exe,
                args.reqs,
                args.windowed,
                build_exe=is_first_engine,
            ):
                global_success = False
                is_first_engine = False  # exe создается только один раз
        if global_success:
            print(
                "\033[92m:: Monolithic multi-module application built successfully for all targets!\033[0m"
            )
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
