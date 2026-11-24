"""Exercise the install.sh shipped inside the Linux self-extracting package."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux installer")
class LinuxInstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.payload = self.root / "package" / "CommTool"
        self.prefix = self.root / "user install"
        self.payload.mkdir(parents=True)
        script = Path(__file__).resolve().parents[1] / "scripts" / "package_linux.sh"
        installer = script.read_text(encoding="utf-8").split("<<'INSTALL'\n", 1)[1].split("\nINSTALL\n", 1)[0]
        self.script = self.payload.parent / "install.sh"
        self.script.write_text(installer, encoding="utf-8")
        self.env = dict(os.environ, HOME=str(self.root), COMMTOOL_PREFIX=str(self.prefix),
                        COMMTOOL_BIN_DIR=str(self.root / "bin"), XDG_DATA_HOME=str(self.root / "data"),
                        DISPLAY="", WAYLAND_DISPLAY="")
        (self.payload / "_internal").mkdir()
        (self.payload / "CommTool").write_text(
            '#!/bin/sh\ncd "$(dirname "$0")"\ncat _internal/version\nexec ./CommTool.bin "$@"\n')
        (self.payload / "_internal" / "version").write_text("old\n")
        # Bash stays executable when renamed, including on runners whose
        # coreutils are a multicall binary that checks the invoked name.
        binary = self.payload / "CommTool.bin"
        shutil.copy2(shutil.which("bash"), str(binary))
        self.old_binary = binary.read_bytes()
        self.install()
        (self.prefix / "profile.ini").write_text("user settings")
        (self.payload / "_internal" / "version").write_text("new\n")
        with binary.open("ab") as stream:
            stream.write(b"new release")

    def install(self, success=True):
        result = subprocess.run(["bash", str(self.script)], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.stdout.decode("utf-8", errors="replace")
        self.assertEqual(result.returncode == 0, success, output)
        return output

    def assert_version(self, version):
        self.assertEqual(subprocess.check_output([str(self.prefix / "CommTool"), "-c", ":"]),
                         (version + "\n").encode())
        self.assertEqual((self.prefix / "profile.ini").read_text(), "user settings")
        self.assertFalse(list(self.prefix.glob(".commtool-install.*")))

    def test_upgrade_replaces_running_binary(self):
        running = subprocess.Popen([str(self.prefix / "CommTool.bin"), "-c", "read -t 60 line"],
                                   stdin=subprocess.PIPE)
        try:
            self.install()
            self.assertIsNone(running.poll())
            self.assert_version("new")
            self.assertEqual((self.prefix / "CommTool.bin").read_bytes(),
                             self.old_binary + b"new release")
        finally:
            running.terminate()
            running.wait()
            running.stdin.close()

    def test_incomplete_payload_keeps_old_version(self):
        (self.payload / "CommTool.bin").unlink()
        (self.payload / "CommTool").unlink()
        self.install(success=False)
        self.assert_version("old")

    def test_launcher_without_binary_is_rejected_before_switch(self):
        (self.payload / "CommTool.bin").unlink()
        self.install(success=False)
        self.assert_version("old")
        fresh = self.root / "fresh"
        self.env["COMMTOOL_PREFIX"] = str(fresh)
        self.install(success=False)
        self.assertFalse((fresh / "CommTool").exists())
        self.assertNotEqual(subprocess.call(["bash", str(self.script), "--check-payload"],
                                            stderr=subprocess.DEVNULL), 0)

    def test_plain_elf_launcher_can_be_installed_without_wrapper(self):
        (self.payload / "CommTool.bin").unlink()
        shutil.copy2(shutil.which("bash"), str(self.payload / "CommTool"))
        self.install()
        subprocess.check_call([str(self.prefix / "CommTool"), "-c", ":"])

    def test_failed_install_in_other_prefix_restores_shared_shortcuts(self):
        from scripts.bundle_linux_syslibs import write_launcher

        # Use the shipping wrapper, including invocation through the PATH symlink.
        write_launcher(str(self.prefix))
        cli = self.root / "bin" / "CommTool"
        menu = self.root / "data" / "applications" / "commtool.desktop"
        original_target = os.readlink(str(cli))
        original_menu = menu.read_bytes()
        (self.root / "Desktop" / "commtool.desktop").mkdir(parents=True)
        alternate = self.root / "alternate"
        self.env["COMMTOOL_PREFIX"] = str(alternate)
        self.install(success=False)
        self.assertEqual(os.readlink(str(cli)), original_target)
        self.assertEqual(cli.resolve(), self.prefix / "CommTool")
        self.assertEqual(menu.read_bytes(), original_menu)
        self.assertFalse((alternate / "CommTool").exists())
        subprocess.check_call([str(cli), "-c", ":"])
        self.assertEqual((self.prefix / "_internal" / "version").read_text(), "old\n")
        self.assertEqual((self.prefix / "profile.ini").read_text(), "user settings")

    def test_other_prefix_cannot_publish_into_locked_shortcut_directory(self):
        import fcntl

        other = self.root / "alternate"
        self.env["COMMTOOL_PREFIX"] = str(other)
        fd = os.open(str(self.root / "bin"), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIn("Another installation", self.install(success=False))
            self.assertFalse((other / "CommTool").exists())
            self.assert_version("old")
        finally:
            os.close(fd)

    def test_failure_during_runtime_switch_rolls_back_and_can_retry(self):
        # Fail just the rename that publishes the new binary, after _internal switched.
        commands = self.root / "commands"
        commands.mkdir()
        mv = commands / "mv"
        mv.write_text('#!/bin/bash\n'
                      'if [[ "${@: -2:1}" == */new/CommTool.bin ]]; then exit 1; fi\n'
                      'exec /bin/mv "$@"\n')
        mv.chmod(0o755)
        self.env["PATH"] = str(commands) + os.pathsep + self.env["PATH"]
        self.install(success=False)
        self.assert_version("old")
        self.assertEqual((self.prefix / "CommTool.bin").read_bytes(), self.old_binary)
        mv.unlink()
        self.install()
        self.assert_version("new")

    def test_desktop_install_failure_restores_runtime(self):
        desktop = self.root / "data" / "applications" / "commtool.desktop"
        desktop.unlink()
        desktop.mkdir()
        self.install(success=False)
        self.assert_version("old")

    def test_failed_rollback_preserves_backup_and_restores_remaining_entries(self):
        # Fail the last desktop rename, then fail restoration of one runtime file.
        commands = self.root / "commands"
        commands.mkdir()
        desktop = self.root / "Desktop"
        desktop.mkdir()
        mv = commands / "mv"
        mv.write_text('#!/bin/bash\n'
                      'if [[ "${@: -1}" == "$HOME/Desktop/commtool.desktop" || '
                      '"${@: -2:1}" == */old/CommTool.bin ]]; then exit 1; fi\n'
                      'exec /bin/mv "$@"\n')
        mv.chmod(0o755)
        self.env["PATH"] = str(commands) + os.pathsep + self.env["PATH"]
        output = self.install(success=False)
        work, = self.prefix.glob(".commtool-install.*")
        self.assertIn("backup retained at " + str(work), output)
        self.assertEqual((work / "old" / "CommTool.bin").read_bytes(), self.old_binary)
        self.assertEqual((self.prefix / "_internal" / "version").read_text(), "old\n")
        self.assertTrue((self.prefix / "CommTool").exists())
        self.assertFalse(list(desktop.glob(".commtool-entry.*")))

    def test_readonly_old_runtime_survives_failed_upgrade(self):
        if os.geteuid() == 0:
            self.skipTest("requires an unprivileged installer")
        runtime = self.prefix / "_internal"
        runtime.chmod(0o555)
        try:
            # Linux requires write access to update the directory's '..' entry
            # when moving it to the backup directory.
            self.install(success=False)
            self.assert_version("old")
        finally:
            runtime.chmod(0o755)
