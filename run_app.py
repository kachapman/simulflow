"""Standalone entry point for PyInstaller."""

import sys
import subprocess

from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

from simulflow.app import MainWindow


def verify_sudo(password: str) -> bool:
    """Verify sudo password works."""
    try:
        result = subprocess.run(
            ["sudo", "-S", "true"],
            input=password.encode(),
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Prompt for sudo password
    sudo_password, ok = QInputDialog.getText(
        None,
        "Simulflow",
        "Enter your sudo password\n(needed to disable system Remote Login):",
        QLineEdit.EchoMode.Password,
    )

    if not ok or not sudo_password:
        sys.exit(0)

    if not verify_sudo(sudo_password):
        QMessageBox.critical(
            None,
            "Simulflow",
            "Invalid sudo password. Please try again.",
        )
        sys.exit(1)

    window = MainWindow(sudo_password)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
