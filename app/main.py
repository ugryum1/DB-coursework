"""АС планирования рациона питания — точка входа."""
from __future__ import annotations

import sys

from PyQt5 import QtCore, QtGui, QtWidgets

from db import DB, load_config
from ui_login import LoginDialog
from ui_main import MainWindow


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("АС планирования рациона питания")
    app.setStyle("Fusion")

    cfg = load_config()
    try:
        db = DB(cfg)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(
            None, "Ошибка подключения к БД",
            f"Не удалось подключиться к PostgreSQL: {exc}\n\n"
            "Проверьте параметры в app/config.json и что СУБД запущена.",
        )
        return 1

    # Цикл «логин → главное окно → logout → снова логин».
    while True:
        login = LoginDialog(db)
        if login.exec_() != QtWidgets.QDialog.Accepted:
            return 0
        user = login.user

        win = MainWindow(db, user)
        logged_out = {"flag": False}

        def _on_logout():
            logged_out["flag"] = True

        win.logoutRequested.connect(_on_logout)
        win.show()
        app.exec_()

        if not logged_out["flag"]:
            return 0  # пользователь закрыл крестиком — выходим окончательно


if __name__ == "__main__":
    sys.exit(main())
