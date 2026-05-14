"""Окно авторизации."""
from __future__ import annotations

from PyQt5 import QtCore, QtGui, QtWidgets

from db import DB


class LoginDialog(QtWidgets.QDialog):
    def __init__(self, db: DB, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.user: dict | None = None
        self.setWindowTitle("Вход в систему")
        self.setFixedSize(360, 220)

        title = QtWidgets.QLabel("АС планирования рациона питания")
        title.setAlignment(QtCore.Qt.AlignCenter)
        f = title.font(); f.setPointSize(12); f.setBold(True); title.setFont(f)

        self.role = QtWidgets.QComboBox()
        self.role.addItems(["Пользователь", "Администратор"])

        self.login_edit = QtWidgets.QLineEdit()
        self.login_edit.setPlaceholderText("Логин")
        self.pw_edit = QtWidgets.QLineEdit()
        self.pw_edit.setPlaceholderText("Пароль")
        self.pw_edit.setEchoMode(QtWidgets.QLineEdit.Password)

        ok = QtWidgets.QPushButton("Войти")
        cancel = QtWidgets.QPushButton("Отмена")
        ok.clicked.connect(self._try_login)
        cancel.clicked.connect(self.reject)

        form = QtWidgets.QFormLayout()
        form.addRow("Группа:", self.role)
        form.addRow("Логин:", self.login_edit)
        form.addRow("Пароль:", self.pw_edit)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cancel)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(title)
        lay.addLayout(form)
        lay.addLayout(btns)

    def _try_login(self) -> None:
        login = self.login_edit.text().strip()
        pw = self.pw_edit.text()
        role_ui = "admin" if self.role.currentText() == "Администратор" else "user"
        rows = self.db.query(
            "SELECT id, login, role, full_name FROM app_user "
            "WHERE login=%s AND password_hash=%s",
            (login, pw),
        )
        if not rows:
            QtWidgets.QMessageBox.warning(self, "Ошибка входа", "Неверный логин или пароль.")
            return
        u = rows[0]
        if u["role"] != role_ui:
            QtWidgets.QMessageBox.warning(
                self, "Ошибка входа",
                f"Пользователь {u['login']} имеет роль «{u['role']}», "
                f"а выбрана роль «{role_ui}».",
            )
            return
        self.user = u
        self.accept()
