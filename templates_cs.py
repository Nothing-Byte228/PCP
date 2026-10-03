# Универсальный базовый лаунчер (appname.exe), который сканирует свою папку,
# находит подходящую под версию Python DLL-ку и запускает её через Reflection
LAUNCHER_TEMPLATE = """using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using System.Collections.Generic;
using Microsoft.Win32;

class Launcher {
    private static readonly string AppName = "PCP Universal Launcher";
    private static readonly string BaseName = "[BASE_NAME]";

    static int Main(string[] args) {
        string exePath = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        Directory.SetCurrentDirectory(exePath);

        // 1. Ищем все установленные версии Python в системе
        Dictionary<string, string> installedPythonRuntimes = FindAllPythonRuntimes();

        // 2. Ищем все доступные модули кода (.dll) в текущей папке приложения
        Dictionary<string, string> availableLibraries = FindAvailableLibraries(exePath);

        // 3. Выбираем лучшую пару
        string bestVersion = null;
        int maxVerValue = -1;

        foreach (var libVer in availableLibraries.Keys) {
            if (installedPythonRuntimes.ContainsKey(libVer)) {
                try {
                    int currentVerValue = int.Parse(libVer);
                    if (currentVerValue > maxVerValue) {
                        maxVerValue = currentVerValue;
                        bestVersion = libVer;
                    }
                } catch {}
            }
        }

        if (string.IsNullOrEmpty(bestVersion)) {
            string errorMessage = "Critical Error: Could not match any installed Python engine with available application modules.\\n\\n";
            if (availableLibraries.Count == 0) errorMessage += "-> No application libraries (*.dll) found.\\n";
            else errorMessage += "-> Found modules for Python: " + string.Join(", ", availableLibraries.Keys) + "\\n";
            if (installedPythonRuntimes.Count == 0) errorMessage += "-> No Python installation detected.\\n";
            else errorMessage += "-> Installed Python runtimes found: " + string.Join(", ", installedPythonRuntimes.Keys);
            MessageBox.Show(errorMessage, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        string targetDllPath = availableLibraries[bestVersion];
        string pythonInterpreterExe = installedPythonRuntimes[bestVersion];

        // ПЕРЕДАЕМ ПАРАМЕТРЫ ЧЕРЕЗ ОКРУЖЕНИЕ (Железобетонный способ без багов сигнатуры)
        Environment.SetEnvironmentVariable("PCP_MIN_VERSION", "[MIN_VERSION]");
        Environment.SetEnvironmentVariable("PCP_WINDOWED", "[WINDOWED_FLAG]");
        Environment.SetEnvironmentVariable("PCP_PYTHON_EXE", pythonInterpreterExe);

        try {
            Assembly assembly = Assembly.LoadFrom(targetDllPath);
            Type type = assembly.GetType("PythonLibrary.RuntimeContainer");
            if (type == null) return 1;

            MethodInfo method = type.GetMethod("InvokeRuntime", BindingFlags.Static | BindingFlags.Public);
            if (method == null) return 1;

            // Передаем ровно ОДИН параметр (массив строк args) внутри массива объектов!
            // Для рефлексии это идеальная структура из одного элемента
            return (int)method.Invoke(null, new object[] { args });
        }
        catch (Exception ex) {
            MessageBox.Show("Dynamic link pipeline runtime crash:\\n" + ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static Dictionary<string, string> FindAvailableLibraries(string path) {
        var libs = new Dictionary<string, string>();
        string prefix = BaseName + "-cpython";
        foreach (string file in Directory.GetFiles(path, prefix + "*.dll")) {
            string fileName = Path.GetFileNameWithoutExtension(file);
            string verStr = fileName.Substring(prefix.Length);
            if (!libs.ContainsKey(verStr)) libs.Add(verStr, file);
        }
        return libs;
    }

    static Dictionary<string, string> FindAllPythonRuntimes() {
        var runtimes = new Dictionary<string, string>();
        string pathPythonVer = GetPythonVersionPath("python");
        if (!string.IsNullOrEmpty(pathPythonVer)) runtimes.Add(pathPythonVer, "python.exe");

        string[] regPaths = { @"Software\Python\PythonCore", @"Software\WOW6432Node\Python\PythonCore" };
        RegistryKey[] hives = { Registry.CurrentUser, Registry.LocalMachine };

        foreach (var regPath in regPaths) {
            foreach (var hive in hives) {
                using (RegistryKey key = hive.OpenSubKey(regPath)) {
                    if (key == null) continue;
                    foreach (string verKey in key.GetSubKeyNames()) {
                        string cleanVer = verKey.Split('-')[0].Replace(".", "");
                        if (runtimes.ContainsKey(cleanVer)) continue;

                        using (RegistryKey installKey = key.OpenSubKey(verKey + @"\InstallPath")) {
                            if (installKey == null) continue;
                            object exeDir = installKey.GetValue("");
                            if (exeDir != null) {
                                string fullExePath = Path.Combine(exeDir.ToString(), "python.exe");
                                if (File.Exists(fullExePath)) runtimes.Add(cleanVer, fullExePath);
                            }
                        }
                    }
                }
            }
        }
        return runtimes;
    }

    static string GetPythonVersionPath(string command) {
        try {
            ProcessStartInfo psi = new ProcessStartInfo(command, "-c \\"import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')\\"") {
                RedirectStandardOutput = true, UseShellExecute = false, CreateNoWindow = true
            };
            using (Process p = Process.Start(psi)) {
                string output = p.StandardOutput.ReadToEnd().Trim();
                p.WaitForExit();
                return p.ExitCode == 0 ? output : null;
            }
        } catch { return null; }
    }
}
"""

# Шаблон для динамических библиотек (appname-cpython313.dll)
LIBRARY_TEMPLATE = """using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace PythonLibrary {
    public class RuntimeContainer {
        private static readonly string[] Requirements = new string[] { [REQUIREMENTS_PLACEHOLDER] };
        private static readonly string Base64RuntimeCode = "[BASE64_RUNTIME_CODE]";
        private static readonly string AppName = "PCP Runtime Engine";

        // Сигнатура принимает ровно один параметр! Рефлексия C# 5 никогда тут не споткнется
        public static int InvokeRuntime(string[] args) {
            Console.OutputEncoding = Encoding.UTF8;
            string exePath = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);

            // Читаем параметры из окружения, переданные лаунчером
            string minVersion = Environment.GetEnvironmentVariable("PCP_MIN_VERSION") ?? "3.10";
            bool windowed = Convert.ToBoolean(Environment.GetEnvironmentVariable("PCP_WINDOWED") ?? "false");
            string pythonInterpreterExe = Environment.GetEnvironmentVariable("PCP_PYTHON_EXE") ?? "python.exe";

            if (!CheckVersion(minVersion)) {
                MessageBox.Show(
                    "Your Python version is too old.\\nRequired version is >= " + minVersion,
                    AppName, MessageBoxButtons.OK, MessageBoxIcon.Error
                );
                return 1;
            }

            if (Requirements.Length > 0 && !ManageDependencies(Requirements)) {
                MessageBox.Show(
                    "Critical dependencies are missing and failed to install via pip.\\nPlease check your internet connection.",
                    AppName, MessageBoxButtons.OK, MessageBoxIcon.Error
                );
                return 1;
            }

            byte[] data = Convert.FromBase64String(Base64RuntimeCode);
            string pythonScript = Encoding.UTF8.GetString(data);
            string tempScriptPath = Path.Combine(Path.GetTempPath(), "pcp_runtime_main.py");

            try {
                File.WriteAllText(tempScriptPath, pythonScript, Encoding.UTF8);
            } catch (Exception ex) {
                MessageBox.Show("Error creating runtime memory stub:\\n" + ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            string scriptArgs = "\\"" + tempScriptPath + "\\"";
            if (args.Length > 0) {
                scriptArgs += " " + string.Join(" ", args);
            }

            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = pythonInterpreterExe;
            if (windowed && pythonInterpreterExe.EndsWith("python.exe")) {
                startInfo.FileName = pythonInterpreterExe.Replace("python.exe", "pythonw.exe");
            }
            
            startInfo.Arguments = scriptArgs;
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = windowed;
            startInfo.WorkingDirectory = exePath;
            startInfo.RedirectStandardError = true;

            int exitCode = 0;
            try {
                using (Process process = Process.Start(startInfo)) {
                    if (process != null) {
                        string errors = process.StandardError.ReadToEnd();
                        process.WaitForExit();
                        exitCode = process.ExitCode;

                        if (exitCode != 0 && !string.IsNullOrEmpty(errors)) {
                            MessageBox.Show("An unhandled exception occurred during runtime:\\n\\n" + errors, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                        }
                    }
                }
            }
            catch (Exception ex) {
                MessageBox.Show("Error launching Python subsystem:\\n" + ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                exitCode = 1;
            }
            finally {
                if (File.Exists(tempScriptPath)) {
                    try { File.Delete(tempScriptPath); } catch {}
                }
            }
            return exitCode;
        }

        static bool CheckVersion(string minVersion) {
            try {
                Version current = Version.Parse(GetPythonVersionStr());
                Version required = Version.Parse(minVersion);
                return current >= required;
            } catch { return false; }
        }

        static string GetPythonVersionStr() {
            ProcessStartInfo psi = new ProcessStartInfo("python", "-c \\"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')\\"") {
                RedirectStandardOutput = true, UseShellExecute = false, CreateNoWindow = true
            };
            using (Process p = Process.Start(psi)) {
                string output = p.StandardOutput.ReadToEnd().Trim();
                p.WaitForExit();
                return output;
            }
        }

        static bool ManageDependencies(string[] modules) {
            foreach (string module in modules) {
                ProcessStartInfo checkPsi = new ProcessStartInfo("python", "-c \\"import " + module + "\\"") {
                    UseShellExecute = false, CreateNoWindow = true
                };
                try {
                    using (Process p = Process.Start(checkPsi)) {
                        p.WaitForExit(); if (p.ExitCode == 0) continue;
                    }
                } catch { return false; }

                Console.WriteLine(">> Missing dependency detected. Installing '" + module + "'...");
                ProcessStartInfo pipPsi = new ProcessStartInfo("python", "-m pip install " + module + " --user --quiet") {
                    UseShellExecute = false, CreateNoWindow = false
                };
                try {
                    using (Process p = Process.Start(pipPsi)) {
                        p.WaitForExit(); if (p.ExitCode != 0) return false;
                    }
                } catch { return false; }
            }
            return true;
        }
    }
}
"""
