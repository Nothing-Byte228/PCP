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

        bool executed = false;
        int exitCode = 1;

        // Сортируем найденные версии библиотек по убыванию (например, сначала 314, затем 313)
        var sortedVersions = new List<string>(availableLibraries.Keys);
        sortedVersions.Sort((a, b) => b.CompareTo(a));

        // 3. Пытаемся запустить лучшую подходящую пару
        foreach (var libVer in sortedVersions) {
            if (installedPythonRuntimes.ContainsKey(libVer)) {
                string targetDllPath = availableLibraries[libVer];
                string pythonInterpreterExe = installedPythonRuntimes[libVer];

                // Передаем параметры через окружение целевой DLL
                Environment.SetEnvironmentVariable("PCP_PYTHON_EXE", pythonInterpreterExe);

                try {
                    Assembly assembly = Assembly.LoadFrom(targetDllPath);
                    Type type = assembly.GetType("PythonLibrary.RuntimeContainer");
                    if (type == null) continue;

                    MethodInfo method = type.GetMethod("InvokeRuntime", BindingFlags.Static | BindingFlags.Public);
                    if (method == null) continue;

                    // Вызываем InvokeRuntime из C#-библиотеки
                    exitCode = (int)method.Invoke(null, new object[] { args });

                    // Код 99 — это сигнал от DLL, что версия интерпретатора не совпала с её байт-кодом.
                    // В этом случае не падаем, а пробуем следующую доступную DLL в цикле.
                    if (exitCode == 99) continue;

                    executed = true;
                    break; // Успешный старт, выходим из цикла перебора
                }
                catch {
                    // Если DLL повреждена или заблокирована, пытаемся пойти дальше
                    continue; 
                }
            }
        }

        // Если ни одна из библиотек не смогла инициализироваться с локальным Python
        if (!executed) {
            string errorMessage = "Critical Error: Could not match any installed Python engine with available application modules.\\n\\n";
            if (availableLibraries.Count == 0) errorMessage += "-> No application libraries (*.dll) found.\\n";
            else errorMessage += "-> Found modules for Python: " + string.Join(", ", availableLibraries.Keys) + "\\n";
            if (installedPythonRuntimes.Count == 0) errorMessage += "-> No Python installation detected.\\n";
            else errorMessage += "-> Installed Python runtimes found: " + string.Join(", ", installedPythonRuntimes.Keys);
            
            MessageBox.Show(errorMessage, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        return exitCode;
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

        string[] regPaths = { @"Software\\Python\\PythonCore", @"Software\\WOW6432Node\\Python\\PythonCore" };
        RegistryKey[] hives = { Registry.CurrentUser, Registry.LocalMachine };

        foreach (var regPath in regPaths) {
            foreach (var hive in hives) {
                using (RegistryKey key = hive.OpenSubKey(regPath)) {
                    if (key == null) continue;
                    foreach (string verKey in key.GetSubKeyNames()) {
                        string cleanVer = verKey.Split('-')[0].Replace(".", "");
                        if (runtimes.ContainsKey(cleanVer)) continue;

                        using (RegistryKey installKey = key.OpenSubKey(verKey + @"\\InstallPath")) {
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
            ProcessStartInfo psi = new ProcessStartInfo(command, "-c \\\"import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')\\\"") {
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

# Изменен под поддержку словаря файлов и автоматического воссоздания структуры
LIBRARY_TEMPLATE = """using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;
using System.Collections.Generic;

namespace PythonLibrary {
    public class RuntimeContainer {
        private static readonly string[] Requirements = new string[] { [REQUIREMENTS_PLACEHOLDER] };
        private static readonly string MainScriptName = "[MAIN_SCRIPT_NAME]";
        private static readonly string AppName = "PCP Runtime Engine";

        // Словарь: ИмяФайла -> Base64 строка загрузочного стаба (заглушки)
        private static readonly Dictionary<string, string> FilePayloads = new Dictionary<string, string>() {
            [FILES_DICTIONARY_PLACEHOLDER]
        };

        public static int InvokeRuntime(string[] args) {
            Console.OutputEncoding = Encoding.UTF8;
            string exePath = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);

            // Читаем версию Python и настройки окна, которые подготовил лаунчер
            string pythonInterpreterExe = Environment.GetEnvironmentVariable("PCP_PYTHON_EXE") ?? "python.exe";
            bool windowed = Convert.ToBoolean(Environment.GetEnvironmentVariable("PCP_WINDOWED") ?? "false");

            string targetVersion = "[TARGET_VERSION]"; 
            if (!CheckExactVersion(targetVersion)) {
                // Если рантайм не совпал с версией байт-кода, возвращаем 99 для перебора
                return 99; 
            }

            if (Requirements.Length > 0 && !ManageDependencies(Requirements)) {
                MessageBox.Show("Critical dependencies are missing and failed to install via pip.", AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            // Создаем изолированную временную папку для текущего сеанса рантайма
            string sessionTempDir = Path.Combine(Path.GetTempPath(), "pcp_project_" + Guid.NewGuid().ToString("N"));
            try {
                Directory.CreateDirectory(sessionTempDir);
            } catch (Exception ex) {
                MessageBox.Show("Error creating isolation runtime directory:\\n" + ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            // Распаковываем все привязанные файлы проекта
            foreach (var item in FilePayloads) {
                string currentFilePath = Path.Combine(sessionTempDir, item.Key);
                try {
                    byte[] data = Convert.FromBase64String(item.Value);
                    string pythonScript = Encoding.UTF8.GetString(data);
                    File.WriteAllText(currentFilePath, pythonScript, Encoding.UTF8);
                } catch (Exception ex) {
                    MessageBox.Show("Error unpacking module " + item.Key + ":\\n" + ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    CleanDirectory(sessionTempDir);
                    return 1;
                }
            }

            string targetMainScript = Path.Combine(sessionTempDir, MainScriptName);
            string scriptArgs = "\\"" + targetMainScript + "\\"";
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
            startInfo.WorkingDirectory = exePath; // Рабочая папка остается оригинальной для логов/сохранений
            startInfo.RedirectStandardError = true;

            // Добавляем путь к временной папке в PYTHONPATH, чтобы локальные импорты работали без швов
            string currentPythonPath = Environment.GetEnvironmentVariable("PYTHONPATH") ?? "";
            startInfo.EnvironmentVariables["PYTHONPATH"] = string.IsNullOrEmpty(currentPythonPath) 
                ? sessionTempDir 
                : sessionTempDir + Path.PathSeparator + currentPythonPath;

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
                CleanDirectory(sessionTempDir);
            }
            return exitCode;
        }

        static bool CheckExactVersion(string targetVersion) {
            try {
                // Проверяем на строгое соответствие "Major.Minor"
                return GetPythonVersionStr() == targetVersion;
            } catch { return false; }
        }

        static void CleanDirectory(string path) {
            if (Directory.Exists(path)) {
                try { Directory.Delete(path, true); } catch {}
            }
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
