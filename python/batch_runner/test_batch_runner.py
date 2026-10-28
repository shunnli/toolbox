"""Focused tests; set BATCH_RUNNER_TEST_MATLAB to enable real MATLAB checks."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import batch_runner as batch


RUNNER = Path(batch.__file__).resolve()


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="batch runner ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def config(self, entries, name="tasks.toml"):
        return self.write(
            name,
            "\n".join(
                f"[[tasks]]\n{kind} = {json.dumps(value, ensure_ascii=False)}\n"
                for kind, value in entries
            ),
        )

    def run_cli(self, *args, env=None, timeout=30):
        child_env = dict(os.environ)
        child_env.update(BATCH_PYTHON_CMD=sys.executable, PYTHONIOENCODING="utf-8")
        if env:
            child_env.update(env)
        return subprocess.run(
            [
                sys.executable, str(RUNNER), *map(str, args),
                "-y", "--port", "0", "--cpu-limit", "0", "--mem-limit", "0",
            ],
            cwd=self.root,
            env=child_env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout,
        )


class TaskParsingTests(WorkspaceTest):
    def test_legacy_comments_paths_and_deduplication(self):
        script = self.write("folder with spaces/main.py", "print('ok')")
        percent = self.write("100%ready.m", "disp('ok');")
        taskfile = self.write(
            "configs/tasks.txt",
            "# comment\n; comment\n% comment\n\n"
            "folder with spaces/main.py # first\n"
            "folder with spaces/main.py ; duplicate\n"
            "100%ready.m % inline comment\n",
        )
        with contextlib.chdir(self.root):
            self.assertEqual(
                batch.parse_taskfiles([str(taskfile)]), [str(script), str(percent)]
            )
            with patch("sys.stdin", io.StringIO("100%ready.m\n100%ready.m\n")):
                self.assertEqual(batch.parse_taskfiles(["-"]), [str(percent)])

    def test_toml_preserves_code_and_comments(self):
        taskfile = self.write(
            "tasks.toml",
            "\ufeff# configuration comment\n"
            "[[tasks]]\n"
            '''matlab = "solve([1 2; 3 4], struct('label', '50% # ;'));" # comment\n'''
            "[[tasks]]\npython = '''\n"
            "# Python comment\nprint('50% # ;')\n'''\n",
        )
        tasks = batch.parse_toml_taskfile(str(taskfile))
        self.assertEqual(tasks[0].value, "solve([1 2; 3 4], struct('label', '50% # ;'));")
        self.assertEqual(tasks[1].value, "# Python comment\nprint('50% # ;')\n")
        self.assertEqual([task.extension for task in tasks], [".m", ".py"])

    def test_launch_directory_rules(self):
        script = self.write("scripts/main.py", "")
        taskfile = self.config(
            [("script", "scripts/main.py"), ("python", "print('ok')")],
            "elsewhere/tasks.toml",
        )
        with contextlib.chdir(self.root):
            tasks = batch.parse_toml_taskfile(str(taskfile))
        self.assertEqual(tasks[0].value, str(script))
        self.assertEqual(tasks[0].cwd, str(script.parent))
        self.assertEqual(tasks[1].cwd, str(self.root))

    def test_structured_duplicates_survive_mixed_inputs(self):
        self.write("main.py", "")
        self.write("tasks.txt", "main.py\nmain.py\n")
        self.config([
            ("script", "main.py"), ("script", "main.py"),
            ("python", "print(1)"), ("python", "print(1)"),
        ])
        with contextlib.chdir(self.root):
            tasks = batch.collect_tasks(["tasks.txt", "tasks.toml", "tasks.txt"], ["main.py"])
        self.assertEqual(len(tasks), 5)
        self.assertEqual([task.kind for task in tasks], ["script"] * 3 + ["python"] * 2)

    def test_invalid_configuration_has_source_context(self):
        cases = [
            "", "tasks = 1", "tasks = [1]", "[[tasks]]",
            "[defaults]\ntimeout = '2h'\n[[tasks]]\npython = 'print(1)'",
            "[[tasks]]\npython = 'print(1)'\nmatlab = 'disp(1)'",
            "[[tasks]]\npython = 'print(1)'\ntimeout = '2h'",
            "[[tasks]]\ncall = 'solve(1)'", "[[tasks]]\npython = 12",
            "[[tasks]]\npython = '   '", '[[tasks]]\npython = "\\u0000"',
            "[[tasks]\npython = 'print(1)'",
        ]
        for content in cases:
            with self.subTest(content=content):
                path = self.write("invalid.toml", content)
                with self.assertRaisesRegex(ValueError, "invalid.toml"):
                    batch.parse_toml_taskfile(str(path))

    def test_missing_or_unsupported_script_has_source_context(self):
        self.write("notes.md", "")
        with contextlib.chdir(self.root):
            for filename, error in [("missing.m", FileNotFoundError), ("notes.md", ValueError)]:
                with self.subTest(filename=filename):
                    config = self.config([("script", filename)])
                    with self.assertRaisesRegex(error, r"tasks\[1\]"):
                        batch.parse_toml_taskfile(str(config))


class TaskExecutionTests(WorkspaceTest):
    def test_repeated_tasks_have_independent_status_and_logs(self):
        code = "print(r'<tag> C:\\data')"
        task = batch.Task("python", code, str(self.root), "tasks.toml:tasks[1]")
        with patch.object(batch, "Manager"):
            runner = batch.BatchRunner(SimpleNamespace(port=0), [task, task, task], [])
        runner._output_dir = str(self.root)
        runner._total = 3
        runner._start_time = 1.0
        futures = [Future(), Future()]
        runner._futures = dict(zip(futures, runner.scripts[:2]))
        runner._pending = runner.scripts[2:]
        runner._running_start_times = {1: 10.0, 2: 20.0}
        state = runner._snapshot()
        self.assertEqual([r["task_id"] for r in state["running"]], [1, 2])
        self.assertEqual([r["start"] for r in state["running"]], [10.0, 20.0])
        self.assertEqual(state["queued"][0]["task_id"], 3)
        html = batch._build_status_html(runner)
        self.assertIn("&lt;tag&gt;", html)
        self.assertIn("C:\\data", html)
        for index, future in enumerate(futures, 1):
            future.set_result({
                "script_path": code, "stdout": f"result {index}", "stderr": "",
                "returncode": 0, "success": True, "duration": 0.1,
            })
        with contextlib.redirect_stdout(io.StringIO()):
            runner._wait()
        self.assertEqual(runner.success, 2)
        self.assertEqual({r["task_id"] for r in runner._snapshot()["results"]}, {1, 2})
        self.assertEqual((self.root / "task_0001_python.log").read_text(), "result 1")
        self.assertEqual((self.root / "task_0002_python.log").read_text(), "result 2")
        self.assertIn("&lt;tag&gt;", batch._build_status_html(runner))

    def test_python_function_arguments_environment_and_duplicates(self):
        self.write(
            "experiment.py",
            "import json, os\nfrom pathlib import Path\n"
            "def solve(values, options, label):\n"
            "    print(json.dumps(dict(values=values, options=options, label=label, "
            "cwd=str(Path.cwd()), inherited=os.environ['BATCH_TEST_PARENT'], "
            "local=os.environ.get('BATCH_TEST_LOCAL', 'unset'))))\n",
        )
        label = "O'Brien; # 50% C:\\data 中文"
        code = (
            "import os\nfrom experiment import solve\n"
            "os.environ['BATCH_TEST_LOCAL'] = 'task-only'\n"
            f"solve([1, 2], {{'tol': 1e-6}}, {label!r})\n"
        )
        self.write("scripts/main.py", "from pathlib import Path\nprint(Path.cwd().name)")
        config = self.config([
            ("python", code), ("python", code),
            ("python", "import os; assert os.environ['BATCH_TEST_LOCAL'] == 'parent'; print('isolated')"),
            ("script", "scripts/main.py"), ("script", "scripts/main.py"),
        ])
        result = self.run_cli(
            "-f", config, "-j", "2",
            env={"BATCH_TEST_PARENT": "inherited", "BATCH_TEST_LOCAL": "parent"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("5 succeeded, 0 failed", result.stdout)
        outputs = sorted(self.root.glob(".batch_runner/*/task_*.log"))
        self.assertEqual(len(outputs), 5)
        for path in outputs[:2]:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data, dict(
                values=[1, 2], options={"tol": 1e-6}, label=label,
                cwd=str(self.root), inherited="inherited", local="task-only",
            ))
        self.assertEqual(outputs[2].read_text().strip(), "isolated")
        self.assertEqual(outputs[3].read_text().strip(), "scripts")
        self.assertEqual(outputs[4].read_text().strip(), "scripts")

    def test_legacy_cli_still_deduplicates_and_runs_in_script_directory(self):
        self.write("scripts/main.py", "from pathlib import Path\nprint(Path.cwd().name)")
        taskfile = self.write("tasks.txt", "scripts/main.py # comment\nscripts/main.py\n")
        result = self.run_cli("-f", taskfile, "scripts/main.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 succeeded, 0 failed", result.stdout)
        outputs = [p for p in self.root.glob(".batch_runner/*/*.log") if p.name != "runner.log"]
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].read_text().strip(), "scripts")
        self.assertEqual(outputs[0].name, "task_0001_script.log")
        self.assertIn("[1] ", result.stdout)
        runner_log = outputs[0].with_name("runner.log").read_text(encoding="utf-8")
        self.assertIn("Submit  [1] ", runner_log)

    def test_failure_and_global_timeout_are_reported(self):
        config = self.config([
            ("python", "raise RuntimeError('expected failure')"),
            ("python", "import time; time.sleep(30)"),
        ])
        result = self.run_cli("-f", config, "-j", "2", "--timeout", "2s")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("0 succeeded, 2 failed", result.stdout)
        self.assertIn("Timeout", result.stdout)
        output = next(self.root.glob(".batch_runner/*/task_0001_python.log"))
        self.assertIn("expected failure", output.read_text())

    def test_invalid_config_starts_no_tasks(self):
        self.write("tasks.toml", "[[tasks]]\npython = 'print(1)'\ntimeout = '2h'")
        result = self.run_cli("-f", "tasks.toml")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tasks[1]", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / ".batch_runner").exists())


@unittest.skipUnless(os.getenv("BATCH_RUNNER_TEST_MATLAB"), "MATLAB integration is opt-in")
class MatlabIntegrationTests(WorkspaceTest):
    def test_real_matlab_calls_scripts_and_errors(self):
        self.write(
            "check_case.m",
            "function check_case(matrix, options, label)\n"
            "assert(isequal(matrix, [1 2; 3 4]));\n"
            "assert(options.tol == 1e-6);\n"
            "assert(strcmp(label, 'O''Brien; # 50%'));\n"
            "assert(strcmp(getenv('BATCH_TEST_PARENT'), 'inherited'));\n"
            "assert(strcmp(getenv('BATCH_TEST_LOCAL'), 'task-only'));\n"
            "assert(strcmp(pwd, getenv('BATCH_TEST_CWD')));\n"
            "disp('MATLAB function passed');\nend\n",
        )
        self.write(
            "user's scripts/main.m",
            "assert(isfile('main.m')); disp('MATLAB script passed');",
        )
        config = self.config([
            ("matlab", "% MATLAB comment\nsetenv('BATCH_TEST_LOCAL', 'task-only');\n"
             "check_case([1 2; 3 4], struct('tol', 1e-6), 'O''Brien; # 50%');"),
            ("matlab", "assert(strcmp(getenv('BATCH_TEST_LOCAL'), 'parent')); disp('isolated');"),
            ("script", "user's scripts/main.m"),
            ("matlab", "error('batch_runner:expected', 'expected failure');"),
        ])
        result = self.run_cli(
            "-f", config, "-j", "2", "--timeout", "2m", timeout=240,
            env={
                "BATCH_MATLAB_CMD": os.environ["BATCH_RUNNER_TEST_MATLAB"],
                "BATCH_TEST_PARENT": "inherited", "BATCH_TEST_LOCAL": "parent",
                "BATCH_TEST_CWD": str(self.root),
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("3 succeeded, 1 failed", result.stdout)
        outputs = sorted(self.root.glob(".batch_runner/*/task_*.log"))
        self.assertEqual(len(outputs), 4)
        for path, expected in zip(outputs, [
            "MATLAB function passed", "isolated", "MATLAB script passed", "expected failure",
        ]):
            self.assertIn(expected, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
