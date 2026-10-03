import os
import sys
import base64
import subprocess
import tempfile
import argparse

def build_exe(script_path, output_file, requirements, min_version="3.10", windowed=False):
    print(f"\033[96m:: Generating stable EXE with embedded {os.path.basename(script_path)}...\033[0m")

    if not os.path.exists(script_path):
        print(f"\033[91m:: Error: {script_path} not found!\033[0m")
        sys.exit(1)

    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(output_file):
        try: os.remove(output_file)
        except Exception: pass

    # 1. Кодируем python-скрипт в Base64
    with open(script_path, "rb") as f:
        file_bytes = f.read()
    base64_code = base64.b64encode(file_bytes).decode("utf-8")

    reqs_formatted = ", ".join([f'"{req}"' for req in requirements])

    # 2. Исходный код C# лаунчера
    csharp_code = f"""using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

class Launcher {{
    private static readonly string[] Requirements = new string[] {{ {reqs_formatted} }};
    private static readonly string MinPythonVersion = "{min_version}";
    private static readonly string AppName = "PCP Runtime Error";

    static int Main(string[] args) {{
        Console.OutputEncoding = Encoding.UTF8;

        string exePath = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        Directory.SetCurrentDirectory(exePath);

        // 1. Проверяем наличие Python
        if (!IsPythonInstalled()) {{
            MessageBox.Show(
                "Python is not installed or not found in your system PATH.\\n\\n" +
                "Please download and install Python from: https://python.org",
                AppName, MessageBoxButtons.OK, MessageBoxIcon.Error
            );
            return 1;
        }}

        // 2. Проверяем версию
        if (!CheckVersion(MinPythonVersion)) {{
            MessageBox.Show(
                "Your Python version is too old.\\n" +
                "Required version: >= " + MinPythonVersion,
                AppName, MessageBoxButtons.OK, MessageBoxIcon.Error
            );
            return 1;
        }}

        // 3. Проверяем зависимости
        if (Requirements.Length > 0) {{
            if (!ManageDependencies(Requirements)) {{
                MessageBox.Show(
                    "Critical dependencies are missing and failed to install via pip.\\n" +
                    "Please check your internet connection and try again.",
                    AppName, MessageBoxButtons.OK, MessageBoxIcon.Error
                );
                return 1;
            }}
        }}

        // 4. Декодируем и запускаем код
        string base64Data = "{base64_code}";
        byte[] data = Convert.FromBase64String(base64Data);
        string pythonScript = Encoding.UTF8.GetString(data);

        string tempScriptPath = Path.Combine(Path.GetTempPath(), "pcp_runtime_main.py");
        
        try {{
            File.WriteAllText(tempScriptPath, pythonScript, Encoding.UTF8);
        }} catch (Exception ex) {{
            MessageBox.Show("Error creating runtime script:\\n" + ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }}

        string scriptArgs = "\\"" + tempScriptPath + "\\"";
        if (args.Length > 0) {{
            scriptArgs += " " + string.Join(" ", args);
        }}

        ProcessStartInfo startInfo = new ProcessStartInfo();
        startInfo.FileName = "python.exe"; 
        
        // Если оконный режим, используем pythonw.exe, чтобы сам Python не вызывал консоль
        if ({str(windowed).lower()}) {{
            startInfo.FileName = "pythonw.exe";
        }}

        startInfo.Arguments = scriptArgs; 
        startInfo.UseShellExecute = false;
        startInfo.CreateNoWindow = {str(windowed).lower()}; 
        startInfo.WorkingDirectory = exePath; 
        startInfo.RedirectStandardError = true;

        int exitCode = 0;
        try {{
            using (Process process = Process.Start(startInfo)) {{
                if (process != null) {{
                    string errors = process.StandardError.ReadToEnd();
                    process.WaitForExit(); 
                    exitCode = process.ExitCode;

                    if (exitCode != 0 && !string.IsNullOrEmpty(errors)) {{
                        MessageBox.Show(
                            "An unhandled exception occurred during runtime:\\n\\n" + errors,
                            AppName, MessageBoxButtons.OK, MessageBoxIcon.Error
                        );
                    }}
                }}
            }}
        }} catch (Exception ex) {{
            MessageBox.Show("Error launching Python:\\n" + ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            exitCode = 1;
        }} finally {{
            if (File.Exists(tempScriptPath)) {{
                try {{ File.Delete(tempScriptPath); }} catch {{}}
            }}
        }}

        return exitCode;
    }}

    static bool IsPythonInstalled() {{
        try {{
            ProcessStartInfo psi = new ProcessStartInfo("python", "--version") {{
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            }};
            using (Process p = Process.Start(psi)) {{
                p.WaitForExit();
                return p.ExitCode == 0;
            }}
        }} catch {{ return false; }}
    }}

    static bool CheckVersion(string minVersion) {{
        try {{
            ProcessStartInfo psi = new ProcessStartInfo("python", "-c \\"import sys; print(f'{{sys.version_info.major}}.{{sys.version_info.minor}}')\\"") {{
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true
            }};
            using (Process p = Process.Start(psi)) {{
                string output = p.StandardOutput.ReadToEnd().Trim();
                p.WaitForExit();
                Version current = Version.Parse(output);
                Version required = Version.Parse(minVersion);
                return current >= required;
            }}
        }} catch {{ return false; }}
    }}

    static bool ManageDependencies(string[] modules) {{
        foreach (string module in modules) {{
            ProcessStartInfo checkPsi = new ProcessStartInfo("python", "-c \\"import " + module + "\\"") {{
                UseShellExecute = false,
                CreateNoWindow = true
            }};
            try {{
                using (Process p = Process.Start(checkPsi)) {{
                    p.WaitForExit();
                    if (p.ExitCode == 0) continue;
                }}
            }} catch {{ return false; }}

            Console.WriteLine(">> Missing dependency detected. Installing '" + module + "'...");
            ProcessStartInfo pipPsi = new ProcessStartInfo("python", "-m pip install " + module + " --user --quiet") {{
                UseShellExecute = false,
                CreateNoWindow = false
            }};
            try {{
                using (Process p = Process.Start(pipPsi)) {{
                    p.WaitForExit();
                    if (p.ExitCode != 0) return false;
                }}
            }} catch {{ return false; }}
        }}
        return true;
    }}
}}
"""

    csc_executable = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if not os.path.exists(csc_executable):
        csc_executable = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"

    if not os.path.exists(csc_executable):
        print("\033[91m:: Error: .NET Framework compiler (csc.exe) not found.\033[0m")
        sys.exit(1)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".cs", encoding="utf-8", delete=False) as temp_file:
        temp_file.write(csharp_code)
        temp_source_path = temp_file.name

    try:
        # Выбираем тип приложения в зависимости от флага windowed
        target_type = "/target:winexe" if windowed else "/target:exe"

        cmd = [
            csc_executable, 
            target_type, 
            "/optimize", 
            "/r:System.Windows.Forms.dll", 
            f"/out:{output_file}", 
            temp_source_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(temp_source_path):
            os.remove(temp_source_path)

        if result.returncode == 0 and os.path.exists(output_file):
            size_kb = os.path.getsize(output_file) / 1024
            print(f"\033[92m:: Success! {os.path.basename(output_file)} created.\033[0m")
            print(f"\033[92m:: File size: ({size_kb:.1f} KB)\033[0m")
        else:
            print("\033[91m:: Error: Compilation failed.\033[0m")
    except Exception as e:
        print(f"\033[91m:: Error during compilation: {e}\033[0m")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PCP: Python Code Packer")
    parser.add_argument("script", help="Path to the main.py script")
    parser.add_argument("-o", "--output", default="./dist/app.exe", help="Output EXE path")
    parser.add_argument("-r", "--reqs", nargs="*", default=[], help="Modules to check/install")
    parser.add_argument("--min-version", default="3.10", help="Minimum Python version")
    parser.add_argument("-w", "--windowed", action="store_true", help="Hide console window (GUI mode, uses pythonw)")

    args = parser.parse_args()
    build_exe(args.script, args.output, args.reqs, args.min_version, args.windowed)
