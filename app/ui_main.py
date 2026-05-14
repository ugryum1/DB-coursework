"""Главное окно АС планирования рациона питания."""
from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

from PyQt5 import QtChart, QtCore, QtGui, QtWidgets
from PyQt5.QtPrintSupport import QPrinter

from db import DB


# ---------- хелперы UI -------------------------------------------------------

def _top_window(w: QtWidgets.QWidget | None) -> QtWidgets.QWidget | None:
    if w is None:
        return None
    return w.window()


def _msg(parent, kind: str, title: str, text: str) -> int:
    """Модальный QMessageBox, центрированный по родительскому окну."""
    icons = {
        'info': QtWidgets.QMessageBox.Information,
        'warn': QtWidgets.QMessageBox.Warning,
        'crit': QtWidgets.QMessageBox.Critical,
        'ask':  QtWidgets.QMessageBox.Question,
    }
    top = _top_window(parent)
    box = QtWidgets.QMessageBox(top)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icons[kind])
    if kind == 'ask':
        box.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
    box.setWindowModality(QtCore.Qt.ApplicationModal)
    # центрируем относительно главного окна
    box.show()
    if top is not None:
        geo = top.frameGeometry()
        fr = box.frameGeometry()
        fr.moveCenter(geo.center())
        box.move(fr.topLeft())
    return box.exec_()


def info(parent, text: str, title: str = "Сообщение") -> None:
    _msg(parent, 'info', title, text)


def warn(parent, text: str, title: str = "Внимание") -> None:
    _msg(parent, 'warn', title, text)


def crit(parent, text: str, title: str = "Ошибка") -> None:
    _msg(parent, 'crit', title, text)


def ask(parent, text: str, title: str = "Подтверждение") -> bool:
    return _msg(parent, 'ask', title, text) == QtWidgets.QMessageBox.Yes


def center_dialog(dlg: QtWidgets.QDialog) -> None:
    """Центрировать диалог относительно главного окна (если есть)."""
    parent = dlg.parent()
    top = _top_window(parent) if isinstance(parent, QtWidgets.QWidget) else None
    if top is not None:
        geo = top.frameGeometry()
        fr = dlg.frameGeometry()
        fr.moveCenter(geo.center())
        dlg.move(fr.topLeft())


def _reports_dir() -> Path:
    """Каталог по умолчанию для PDF-отчётов.

    Внутри docker примонтирован /app/reports → kypca4/reports/ на хосте.
    Вне docker используем <project_root>/reports/.
    """
    candidates = [
        Path("/app/reports"),                                  # docker
        Path(__file__).resolve().parent.parent / "reports",    # запуск вне docker
    ]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            if d.is_dir():
                return d
        except OSError:
            continue
    return Path.cwd()


def export_pdf(parent: QtWidgets.QWidget, default_name: str, title: str,
               headers: list[str], rows: list[list]) -> None:
    """Сохранить таблицу в PDF через QTextDocument + QPrinter."""
    initial = str(_reports_dir() / default_name)
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        parent, "Сохранить PDF", initial, "PDF (*.pdf)")
    if not path:
        return
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    html = ["<html><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:'DejaVu Sans',Arial,sans-serif;font-size:11pt;}"
            "h2{margin:0 0 8pt 0;}"
            ".meta{color:#555;font-size:9pt;margin:0 0 14pt 0;}"
            "table{border-collapse:collapse;width:100%;}"
            "th,td{border:1px solid #888;padding:4pt 6pt;text-align:left;"
            "vertical-align:top;}"
            "th{background:#dde7ff;}"
            "tr:nth-child(even) td{background:#f6f8ff;}"
            "</style></head><body>"]
    html.append(f"<h2>{escape(title)}</h2>")
    html.append(f"<p class='meta'>Сформировано: {date.today().isoformat()} • "
                f"строк: {len(rows)}</p>")
    html.append("<table><thead><tr>")
    for h in headers:
        html.append(f"<th>{escape(str(h))}</th>")
    html.append("</tr></thead><tbody>")
    for r in rows:
        html.append("<tr>")
        for v in r:
            html.append(f"<td>{escape('' if v is None else str(v))}</td>")
        html.append("</tr>")
    html.append("</tbody></table></body></html>")

    doc = QtGui.QTextDocument()
    doc.setHtml("".join(html))
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPrinter.A4)
    printer.setPageMargins(15, 15, 15, 15, QPrinter.Millimeter)
    doc.print_(printer)
    info(parent, f"Файл сохранён:\n{path}", "Готово")


def fmt_num(v, digits: int = 0) -> str:
    """Аккуратный вывод числа без хвостовых нулей."""
    if v is None:
        return ""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{x:.{digits}f}"


# ---------- общая утилита редактирования таблицы ----------------------------

class TableEditor(QtWidgets.QWidget):
    """Универсальный редактор справочника на одной таблице.

    Параметры:
        title        — заголовок;
        select_sql   — SELECT для отображения (первый столбец = id);
        columns      — заголовки колонок таблицы;
        form_fields  — список (label, key, type) — поля формы для add/edit;
        insert_sql, update_sql, delete_sql — операторы;
        readonly     — режим без правок (для пользователя);
        round_cols   — индексы (1..n, без учёта id) колонок, которые надо округлять до int.
    """

    def __init__(self, db, *, title, select_sql, columns, form_fields,
                 insert_sql=None, update_sql=None, delete_sql=None,
                 readonly=False, round_cols=None):
        super().__init__()
        self.db = db
        self.title = title
        self.select_sql = select_sql
        self.columns = columns
        self.form_fields = form_fields
        self.insert_sql = insert_sql
        self.update_sql = update_sql
        self.delete_sql = delete_sql
        self.readonly = readonly
        self.round_cols = set(round_cols or [])

        v = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(f"<b>{title}</b>")
        head.addWidget(lbl); head.addStretch(1)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Поиск…")
        self.search.textChanged.connect(self._apply_filter)
        head.addWidget(self.search)
        v.addLayout(head)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(len(columns) + 1)
        self.table.setHorizontalHeaderLabels(["id"] + columns)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setColumnHidden(0, True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(self.table)

        btns = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Добавить")
        self.btn_edit = QtWidgets.QPushButton("Изменить")
        self.btn_del = QtWidgets.QPushButton("Удалить")
        self.btn_refresh = QtWidgets.QPushButton("Обновить")
        self.btn_pdf = QtWidgets.QPushButton("Отчёт PDF")
        for b in (self.btn_add, self.btn_edit, self.btn_del,
                  self.btn_refresh, self.btn_pdf):
            btns.addWidget(b)
        btns.addStretch(1)
        v.addLayout(btns)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_pdf.clicked.connect(self._export_pdf)

        if readonly:
            self.btn_add.setEnabled(False)
            self.btn_edit.setEnabled(False)
            self.btn_del.setEnabled(False)

        self.refresh()

    # --- данные ---

    def refresh(self) -> None:
        rows = self.db.query(self.select_sql)
        self._all_rows = rows
        self._render(rows)

    def _format_row(self, r) -> list[str]:
        vals = list(r.values())
        out: list[str] = []
        for i, v in enumerate(vals):
            if i == 0:
                out.append("" if v is None else str(v))
            elif i in self.round_cols and v is not None:
                try:
                    out.append(f"{float(v):.0f}")
                except (TypeError, ValueError):
                    out.append(str(v))
            else:
                out.append("" if v is None else str(v))
        return out

    def _render(self, rows) -> None:
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, s in enumerate(self._format_row(r)):
                it = QtWidgets.QTableWidgetItem(s)
                it.setFlags(it.flags() ^ QtCore.Qt.ItemIsEditable)
                self.table.setItem(i, j, it)

    def _apply_filter(self, text: str) -> None:
        text = text.lower().strip()
        if not text:
            self._render(self._all_rows); return
        filt = [r for r in self._all_rows
                if any(text in str(v).lower() for v in r.values())]
        self._render(filt)

    def _selected_row(self):
        idxs = self.table.selectionModel().selectedRows()
        if not idxs:
            return None
        i = idxs[0].row()
        return self._all_rows[i] if i < len(self._all_rows) else None

    # --- CRUD ---

    def _add(self) -> None:
        if not self.insert_sql:
            return
        dlg = FormDialog(self, "Добавление записи", self.form_fields)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            try:
                self.db.execute(self.insert_sql,
                                 [dlg.values[k] for _, k, _ in self.form_fields])
                self.refresh()
            except Exception as e:
                crit(self, str(e))

    def _edit(self) -> None:
        if not self.update_sql:
            return
        row = self._selected_row()
        if not row:
            info(self, "Выберите запись.", "Выбор"); return
        dlg = FormDialog(self, "Редактирование", self.form_fields, initial=row)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            try:
                params = [dlg.values[k] for _, k, _ in self.form_fields]
                params.append(list(row.values())[0])  # id
                self.db.execute(self.update_sql, params)
                self.refresh()
            except Exception as e:
                crit(self, str(e))

    def _delete(self) -> None:
        if not self.delete_sql:
            return
        row = self._selected_row()
        if not row:
            info(self, "Выберите запись.", "Выбор"); return
        if not ask(self, "Подтвердите удаление выбранной записи.", "Удалить?"):
            return
        try:
            self.db.execute(self.delete_sql, (list(row.values())[0],))
            self.refresh()
        except Exception as e:
            crit(self, str(e))

    def _export_pdf(self) -> None:
        rows = [self._format_row(r)[1:] for r in self._all_rows]
        default = f"report_{date.today().isoformat()}.pdf"
        export_pdf(self, default, self.title, self.columns, rows)


# ---------- универсальный диалог формы ---------------------------------------

class FormDialog(QtWidgets.QDialog):
    """form_fields: list of (label, key, type) where type ∈
       {'str','int','float','date','sql:<query returning id,name>','choice:...'}."""

    def __init__(self, parent, title, fields, initial=None):
        super().__init__(parent)
        # db ищем через родителей
        self.db = parent.db if hasattr(parent, "db") else None
        self.fields = fields
        self.values = {}
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        form = QtWidgets.QFormLayout(self)
        self.widgets: dict[str, QtWidgets.QWidget] = {}

        init_vals = list(initial.values())[1:] if initial else []

        for idx, (label, key, ftype) in enumerate(fields):
            w: QtWidgets.QWidget
            if ftype == "int":
                w = QtWidgets.QSpinBox(); w.setRange(-10**9, 10**9)
                if init_vals and idx < len(init_vals) and init_vals[idx] is not None:
                    try: w.setValue(int(init_vals[idx]))
                    except Exception: pass
            elif ftype == "float":
                w = QtWidgets.QDoubleSpinBox(); w.setRange(0, 10**6); w.setDecimals(2)
                if init_vals and idx < len(init_vals) and init_vals[idx] is not None:
                    try: w.setValue(float(init_vals[idx]))
                    except Exception: pass
            elif ftype == "date":
                w = QtWidgets.QDateEdit(); w.setCalendarPopup(True)
                w.setDate(QtCore.QDate.currentDate())
                if init_vals and idx < len(init_vals) and init_vals[idx]:
                    s = str(init_vals[idx])
                    d = QtCore.QDate.fromString(s, "yyyy-MM-dd")
                    if d.isValid(): w.setDate(d)
            elif ftype.startswith("sql:"):
                w = QtWidgets.QComboBox()
                opts = self.db.query(ftype[4:]) if self.db else []
                for o in opts:
                    vals = list(o.values())
                    w.addItem(str(vals[1]), vals[0])
                if init_vals and idx < len(init_vals):
                    cur = init_vals[idx]
                    for i in range(w.count()):
                        if str(w.itemText(i)) == str(cur) or w.itemData(i) == cur:
                            w.setCurrentIndex(i); break
            elif ftype.startswith("choice:"):
                w = QtWidgets.QComboBox()
                for o in ftype[7:].split("|"):
                    w.addItem(o)
                if init_vals and idx < len(init_vals) and init_vals[idx]:
                    i = w.findText(str(init_vals[idx]))
                    if i >= 0: w.setCurrentIndex(i)
            else:
                w = QtWidgets.QLineEdit()
                if init_vals and idx < len(init_vals) and init_vals[idx] is not None:
                    w.setText(str(init_vals[idx]))
            form.addRow(label, w)
            self.widgets[key] = w

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def showEvent(self, ev):  # noqa: N802
        super().showEvent(ev)
        center_dialog(self)

    def _ok(self) -> None:
        for label, key, ftype in self.fields:
            w = self.widgets[key]
            if isinstance(w, QtWidgets.QSpinBox):
                self.values[key] = w.value()
            elif isinstance(w, QtWidgets.QDoubleSpinBox):
                self.values[key] = w.value()
            elif isinstance(w, QtWidgets.QDateEdit):
                self.values[key] = w.date().toString("yyyy-MM-dd")
            elif isinstance(w, QtWidgets.QComboBox):
                self.values[key] = w.currentData() if ftype.startswith("sql:") else w.currentText()
            else:
                self.values[key] = w.text()
        self.accept()


# ---------- вкладка «Профиль и расчёт нормы» --------------------------------

class ProfileTab(QtWidgets.QWidget):
    """Карточка пользователя + расчёт суточной нормы (Миффлин-Сан Жеор)."""

    ACTIVITY = {"Низкий": 1.2, "Средний": 1.55, "Высокий": 1.725}
    GOAL_K = {"Похудение": 0.85, "Поддержание": 1.0, "Набор массы": 1.15}

    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user

        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel(f"<b>Профиль: {user['full_name']}</b>"))

        self.full = QtWidgets.QLineEdit()
        self.age = QtWidgets.QSpinBox(); self.age.setRange(1, 120)
        self.sex = QtWidgets.QComboBox(); self.sex.addItems(["М", "Ж"])
        self.weight = QtWidgets.QDoubleSpinBox(); self.weight.setRange(1, 400); self.weight.setSuffix(" кг")
        self.height = QtWidgets.QDoubleSpinBox(); self.height.setRange(1, 260); self.height.setSuffix(" см")
        self.activity = QtWidgets.QComboBox(); self.activity.addItems(list(self.ACTIVITY.keys()))
        self.goal = QtWidgets.QComboBox(); self.goal.addItems(list(self.GOAL_K.keys()))

        form = QtWidgets.QFormLayout()
        form.addRow("ФИО:", self.full)
        form.addRow("Возраст:", self.age)
        form.addRow("Пол:", self.sex)
        form.addRow("Вес:", self.weight)
        form.addRow("Рост:", self.height)
        form.addRow("Активность:", self.activity)
        form.addRow("Цель:", self.goal)
        v.addLayout(form)

        h = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Сохранить профиль")
        calc = QtWidgets.QPushButton("Рассчитать норму")
        pdf  = QtWidgets.QPushButton("Отчёт PDF")
        h.addWidget(save); h.addWidget(calc); h.addWidget(pdf); h.addStretch(1)
        v.addLayout(h)

        self.result = QtWidgets.QTextEdit(); self.result.setReadOnly(True)
        v.addWidget(self.result, 1)

        save.clicked.connect(self._save)
        calc.clicked.connect(self._calc)
        pdf.clicked.connect(self._pdf)

        self._load()

    def _load(self) -> None:
        rows = self.db.query(
            "SELECT full_name, age, sex, weight, height, activity_level, goal "
            "FROM app_user WHERE id=%s", (self.user["id"],))
        if not rows: return
        r = rows[0]
        self.full.setText(r["full_name"] or "")
        if r["age"]: self.age.setValue(r["age"])
        if r["sex"]: self.sex.setCurrentText(r["sex"])
        if r["weight"]: self.weight.setValue(float(r["weight"]))
        if r["height"]: self.height.setValue(float(r["height"]))
        if r["activity_level"]:
            i = self.activity.findText(r["activity_level"])
            if i >= 0: self.activity.setCurrentIndex(i)
        if r["goal"]:
            i = self.goal.findText(r["goal"])
            if i >= 0: self.goal.setCurrentIndex(i)

    def _save(self) -> None:
        self.db.execute(
            "UPDATE app_user SET full_name=%s, age=%s, sex=%s, weight=%s,"
            " height=%s, activity_level=%s, goal=%s WHERE id=%s",
            (self.full.text(), self.age.value(), self.sex.currentText(),
             self.weight.value(), self.height.value(),
             self.activity.currentText(), self.goal.currentText(),
             self.user["id"]),
        )
        info(self, "Профиль обновлён.", "Сохранено")

    def _calc(self) -> tuple[float, float, float, int, int, int]:
        w = self.weight.value(); h = self.height.value(); a = self.age.value()
        if self.sex.currentText() == "М":
            bmr = 10 * w + 6.25 * h - 5 * a + 5
        else:
            bmr = 10 * w + 6.25 * h - 5 * a - 161
        tdee = bmr * self.ACTIVITY[self.activity.currentText()]
        target = tdee * self.GOAL_K[self.goal.currentText()]
        prot = round(w * 1.8); fat = round(w * 1.0); carb = round((target - prot*4 - fat*9)/4)
        self.result.setHtml(
            f"<h3>Расчёт суточной нормы</h3>"
            f"<b>BMR</b> (формула Миффлин-Сан Жеор): {bmr:.0f} ккал<br>"
            f"<b>TDEE</b> с поправкой на активность: {tdee:.0f} ккал<br>"
            f"<b>Целевая калорийность</b> ({self.goal.currentText()}): "
            f"<span style='color:#205'>{target:.0f} ккал</span><br>"
            f"<b>Рекомендации по БЖУ:</b> Б={prot} г, Ж={fat} г, У={carb} г"
        )
        return bmr, tdee, target, prot, fat, carb

    def _pdf(self) -> None:
        bmr, tdee, target, prot, fat, carb = self._calc()
        headers = ["Параметр", "Значение"]
        rows = [
            ["ФИО", self.full.text()],
            ["Возраст", self.age.value()],
            ["Пол", self.sex.currentText()],
            ["Вес, кг", f"{self.weight.value():.1f}"],
            ["Рост, см", f"{self.height.value():.1f}"],
            ["Активность", self.activity.currentText()],
            ["Цель", self.goal.currentText()],
            ["BMR (ккал)", f"{bmr:.0f}"],
            ["TDEE (ккал)", f"{tdee:.0f}"],
            ["Целевая калорийность (ккал)", f"{target:.0f}"],
            ["Белки (г)", prot],
            ["Жиры (г)", fat],
            ["Углеводы (г)", carb],
        ]
        export_pdf(self, f"profile_{self.user['login']}.pdf",
                   f"Карточка профиля и суточная норма — {self.full.text()}",
                   headers, rows)


# ---------- вкладка «Рацион пользователя» ------------------------------------

class RationsTab(QtWidgets.QWidget):
    """Список рационов текущего пользователя + меню + сравнение с нормой."""

    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user

        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel("<b>Мои рационы</b>"))
        self.tbl_r = QtWidgets.QTableWidget(0, 5)
        self.tbl_r.setHorizontalHeaderLabels(["id", "Название", "Начало", "Конец", "Ккал/период"])
        self.tbl_r.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_r.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_r.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.tbl_r.setColumnHidden(0, True)
        self.tbl_r.itemSelectionChanged.connect(self._on_select)
        v.addWidget(self.tbl_r, 1)

        h = QtWidgets.QHBoxLayout()
        for name, slot in (("Добавить", self._add), ("Удалить", self._del),
                            ("Обновить", self.refresh)):
            b = QtWidgets.QPushButton(name); b.clicked.connect(slot); h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)

        v.addWidget(QtWidgets.QLabel("<b>Меню выбранного рациона</b>"))
        self.tbl_m = QtWidgets.QTableWidget(0, 5)
        self.tbl_m.setHorizontalHeaderLabels(["Меню", "Приём пищи", "Блюдо", "Порция, г", "Ккал"])
        self.tbl_m.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_m.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(self.tbl_m, 1)

        self.lbl_total = QtWidgets.QLabel(" ")
        v.addWidget(self.lbl_total)

        h2 = QtWidgets.QHBoxLayout()
        self.btn_add_menu = QtWidgets.QPushButton("Добавить приём пищи")
        self.btn_add_item = QtWidgets.QPushButton("Добавить блюдо в меню")
        self.btn_report = QtWidgets.QPushButton("Отчёт по рациону (PDF)")
        for b in (self.btn_add_menu, self.btn_add_item, self.btn_report):
            h2.addWidget(b)
        h2.addStretch(1)
        v.addLayout(h2)
        self.btn_add_menu.clicked.connect(self._add_menu)
        self.btn_add_item.clicked.connect(self._add_item)
        self.btn_report.clicked.connect(self._report)

        self.refresh()

    def refresh(self) -> None:
        rows = self.db.query(
            "SELECT r.id, r.name AS ration_name, r.date_start, r.date_end,"
            "       rn.total_calories "
            "FROM ration r LEFT JOIN ration_nutrition rn ON rn.ration_id=r.id "
            "WHERE r.user_id=%s ORDER BY r.date_start DESC", (self.user["id"],))
        self._rations = rows
        self.tbl_r.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.tbl_r.setItem(i, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
            self.tbl_r.setItem(i, 1, QtWidgets.QTableWidgetItem(r["ration_name"]))
            self.tbl_r.setItem(i, 2, QtWidgets.QTableWidgetItem(str(r["date_start"])))
            self.tbl_r.setItem(i, 3, QtWidgets.QTableWidgetItem(str(r["date_end"])))
            cal = r["total_calories"] or 0
            self.tbl_r.setItem(i, 4, QtWidgets.QTableWidgetItem(f"{float(cal):.0f}"))
        self.tbl_m.setRowCount(0); self.lbl_total.setText(" ")

    def _on_select(self) -> None:
        idxs = self.tbl_r.selectionModel().selectedRows()
        if not idxs:
            return
        rid = int(self.tbl_r.item(idxs[0].row(), 0).text())
        self._current_ration = rid
        # LEFT JOIN, чтобы пустые приёмы пищи (без блюд) тоже отображались
        rows = self.db.query(
            "SELECT m.name AS menu, m.meal_type, d.name AS dish, mi.portion_g, "
            "       (mi.portion_g * dn.total_calories / "
            "        CASE WHEN dn.total_grams=0 THEN NULL ELSE dn.total_grams END) AS kcal "
            "FROM   menu m "
            "LEFT JOIN menu_items mi ON mi.menu_id = m.id "
            "LEFT JOIN dish d ON d.id = mi.dish_id "
            "LEFT JOIN dish_nutrition dn ON dn.dish_id = d.id "
            "WHERE  m.ration_id=%s "
            "ORDER  BY m.meal_type, m.name, d.name", (rid,))
        self.tbl_m.setRowCount(len(rows))
        total = 0
        for i, r in enumerate(rows):
            self.tbl_m.setItem(i, 0, QtWidgets.QTableWidgetItem(r["menu"]))
            self.tbl_m.setItem(i, 1, QtWidgets.QTableWidgetItem(r["meal_type"]))
            self.tbl_m.setItem(i, 2, QtWidgets.QTableWidgetItem(r["dish"] or "—"))
            self.tbl_m.setItem(
                i, 3,
                QtWidgets.QTableWidgetItem(
                    "—" if r["portion_g"] is None else f"{float(r['portion_g']):.0f}"))
            if r["kcal"] is None:
                self.tbl_m.setItem(i, 4, QtWidgets.QTableWidgetItem("—"))
            else:
                k = float(r["kcal"]); total += k
                self.tbl_m.setItem(i, 4, QtWidgets.QTableWidgetItem(f"{k:.0f}"))
        self.lbl_total.setText(f"<b>Итого по рациону: {total:.0f} ккал</b>")

    def _add(self) -> None:
        dlg = FormDialog(self, "Новый рацион", [
            ("Название", "name", "str"),
            ("Дата начала", "ds", "date"),
            ("Дата окончания", "de", "date"),
        ])
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            try:
                self.db.execute(
                    "INSERT INTO ration (user_id, name, date_start, date_end) "
                    "VALUES (%s,%s,%s,%s)",
                    (self.user["id"], dlg.values["name"], dlg.values["ds"], dlg.values["de"]))
                self.refresh()
            except Exception as e:
                crit(self, str(e))

    def _del(self) -> None:
        idxs = self.tbl_r.selectionModel().selectedRows()
        if not idxs: return
        rid = int(self.tbl_r.item(idxs[0].row(), 0).text())
        if not ask(self, "Удалить рацион?", "Удалить?"):
            return
        self.db.execute("DELETE FROM ration WHERE id=%s", (rid,))
        self.refresh()

    def _add_menu(self) -> None:
        if not hasattr(self, "_current_ration"):
            info(self, "Выберите рацион.", "Выбор"); return
        dlg = FormDialog(self, "Добавить приём пищи", [
            ("Название", "name", "str"),
            ("Тип", "mt", "choice:Завтрак|Обед|Ужин|Перекус"),
        ])
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        name = (dlg.values["name"] or "").strip()
        if not name:
            warn(self, "Введите название приёма пищи."); return
        try:
            self.db.execute(
                "INSERT INTO menu (ration_id, name, meal_type) VALUES (%s,%s,%s)",
                (self._current_ration, name, dlg.values["mt"]))
        except Exception as e:
            crit(self, str(e)); return
        self._on_select()
        info(self, f"Приём пищи «{name}» добавлен. Теперь нажмите "
                   "«Добавить блюдо в меню», чтобы наполнить его.",
             "Готово")

    def _add_item(self) -> None:
        if not hasattr(self, "_current_ration"):
            info(self, "Выберите рацион.", "Выбор"); return
        menus = self.db.query(
            "SELECT id, name FROM menu WHERE ration_id=%s ORDER BY id",
            (self._current_ration,))
        if not menus:
            info(self, "Сначала добавьте приём пищи.", "Нет меню"); return
        excluded = [r["product_id"] for r in self.db.query(
            "SELECT product_id FROM user_excludes WHERE user_id=%s",
            (self.user["id"],))]
        if excluded:
            placeholders = ",".join(["%s"] * len(excluded))
            dishes = self.db.query(
                f"SELECT id, name FROM dish WHERE id NOT IN ("
                f"  SELECT DISTINCT dish_id FROM dish_products "
                f"  WHERE product_id IN ({placeholders})) ORDER BY name",
                tuple(excluded))
        else:
            dishes = self.db.query("SELECT id, name FROM dish ORDER BY name")
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Добавить блюдо в меню")
        dlg.setWindowModality(QtCore.Qt.ApplicationModal)
        f = QtWidgets.QFormLayout(dlg)
        cb_menu = QtWidgets.QComboBox()
        for m in menus: cb_menu.addItem(m["name"], m["id"])
        cb_dish = QtWidgets.QComboBox()
        for d in dishes: cb_dish.addItem(d["name"], d["id"])
        sp = QtWidgets.QDoubleSpinBox(); sp.setRange(1, 5000); sp.setValue(200); sp.setSuffix(" г")
        f.addRow("Меню:", cb_menu); f.addRow("Блюдо:", cb_dish); f.addRow("Порция:", sp)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        dlg.show(); center_dialog(dlg)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            try:
                self.db.execute(
                    "INSERT INTO menu_items (menu_id, dish_id, portion_g) VALUES (%s,%s,%s)",
                    (cb_menu.currentData(), cb_dish.currentData(), sp.value()))
                self._on_select()
            except Exception as e:
                crit(self, str(e))

    def _report(self) -> None:
        if not hasattr(self, "_current_ration"):
            info(self, "Выберите рацион.", "Выбор"); return
        rid = self._current_ration
        rows = self.db.query(
            "SELECT m.name AS menu, m.meal_type, d.name AS dish, mi.portion_g, "
            "       (mi.portion_g * dn.total_calories / NULLIF(dn.total_grams,0)) AS kcal "
            "FROM menu m JOIN menu_items mi ON mi.menu_id=m.id "
            "JOIN dish d ON d.id=mi.dish_id "
            "JOIN dish_nutrition dn ON dn.dish_id=d.id "
            "WHERE m.ration_id=%s ORDER BY m.meal_type, d.name", (rid,))
        hdr = self.db.query("SELECT name, date_start, date_end FROM ration WHERE id=%s", (rid,))[0]
        headers = ["Приём пищи", "Меню", "Блюдо", "Порция, г", "Ккал"]
        out = []
        total = 0.0
        for r in rows:
            k = float(r["kcal"] or 0); total += k
            out.append([r["meal_type"], r["menu"], r["dish"],
                        f"{float(r['portion_g']):.0f}", f"{k:.0f}"])
        out.append(["", "", "ИТОГО", "", f"{total:.0f}"])
        export_pdf(self, f"ration_{rid}.pdf",
                   f"Рацион «{hdr['name']}» — {hdr['date_start']} – {hdr['date_end']} "
                   f"({self.user['full_name']})",
                   headers, out)


# ---------- вкладка «Состав блюд» --------------------------------------------

class DishCompositionTab(QtWidgets.QWidget):
    def __init__(self, db, readonly: bool):
        super().__init__()
        self.db = db; self.readonly = readonly
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel("<b>Состав блюд</b>"))
        h = QtWidgets.QHBoxLayout()
        self.cb = QtWidgets.QComboBox()
        h.addWidget(QtWidgets.QLabel("Блюдо:")); h.addWidget(self.cb, 1)
        b = QtWidgets.QPushButton("Обновить"); h.addWidget(b)
        v.addLayout(h)
        self.tbl = QtWidgets.QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["Продукт", "Грамм", "Ккал", "Б/Ж/У", "Категория"])
        self.tbl.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(self.tbl, 1)
        self.lbl = QtWidgets.QLabel(); v.addWidget(self.lbl)

        h2 = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton("Добавить продукт")
        self.btn_del = QtWidgets.QPushButton("Удалить выбранное")
        self.btn_pdf = QtWidgets.QPushButton("Отчёт PDF")
        h2.addWidget(self.btn_add); h2.addWidget(self.btn_del); h2.addWidget(self.btn_pdf); h2.addStretch(1)
        v.addLayout(h2)
        if readonly:
            self.btn_add.setEnabled(False); self.btn_del.setEnabled(False)
        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._del)
        self.btn_pdf.clicked.connect(self._pdf)

        self.cb.currentIndexChanged.connect(self._reload)
        b.clicked.connect(self._reload_dishes)
        self._reload_dishes()

    def _reload_dishes(self) -> None:
        self.cb.blockSignals(True); self.cb.clear()
        for d in self.db.query("SELECT id, name FROM dish ORDER BY name"):
            self.cb.addItem(d["name"], d["id"])
        self.cb.blockSignals(False); self._reload()

    def _reload(self) -> None:
        did = self.cb.currentData()
        if did is None: return
        rows = self.db.query(
            "SELECT p.name AS pname, dp.grams, "
            " (dp.grams * p.calories/100.0) AS kcal, "
            " p.proteins, p.fats, p.carbs, c.name AS cname "
            "FROM dish_products dp JOIN product p ON p.id=dp.product_id "
            "JOIN category c ON c.id=p.category_id "
            "WHERE dp.dish_id=%s", (did,))
        self.tbl.setRowCount(len(rows))
        tk = tp = tf = tc = 0.0
        for i, r in enumerate(rows):
            self.tbl.setItem(i, 0, QtWidgets.QTableWidgetItem(r["pname"]))
            self.tbl.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{float(r['grams']):.0f}"))
            self.tbl.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{float(r['kcal']):.0f}"))
            self.tbl.setItem(i, 3, QtWidgets.QTableWidgetItem(
                f"{float(r['proteins']):.1f}/{float(r['fats']):.1f}/{float(r['carbs']):.1f}"))
            self.tbl.setItem(i, 4, QtWidgets.QTableWidgetItem(r["cname"]))
            g = float(r["grams"])
            tk += float(r['kcal']); tp += g*float(r['proteins'])/100
            tf += g*float(r['fats'])/100; tc += g*float(r['carbs'])/100
        self._totals = (tk, tp, tf, tc)
        self.lbl.setText(
            f"<b>Итого по блюду:</b> {tk:.0f} ккал; "
            f"Б={tp:.1f} г, Ж={tf:.1f} г, У={tc:.1f} г")

    def _add(self) -> None:
        did = self.cb.currentData()
        if did is None: return
        dlg = FormDialog(self, "Добавить продукт в блюдо", [
            ("Продукт", "p", "sql:SELECT id,name FROM product ORDER BY name"),
            ("Грамм", "g", "float"),
        ])
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            try:
                self.db.execute(
                    "INSERT INTO dish_products (dish_id, product_id, grams) VALUES (%s,%s,%s)",
                    (did, dlg.values["p"], dlg.values["g"]))
                self._reload()
            except Exception as e:
                crit(self, str(e))

    def _del(self) -> None:
        did = self.cb.currentData()
        idxs = self.tbl.selectionModel().selectedRows()
        if did is None or not idxs: return
        name = self.tbl.item(idxs[0].row(), 0).text()
        pid_rows = self.db.query("SELECT id FROM product WHERE name=%s", (name,))
        if not pid_rows: return
        self.db.execute("DELETE FROM dish_products WHERE dish_id=%s AND product_id=%s",
                        (did, pid_rows[0]["id"]))
        self._reload()

    def _pdf(self) -> None:
        did = self.cb.currentData()
        if did is None: return
        dname = self.cb.currentText()
        rows = []
        for i in range(self.tbl.rowCount()):
            rows.append([self.tbl.item(i, j).text() for j in range(5)])
        if hasattr(self, "_totals"):
            tk, tp, tf, tc = self._totals
            rows.append(["ИТОГО", "", f"{tk:.0f}",
                         f"{tp:.1f}/{tf:.1f}/{tc:.1f}", ""])
        export_pdf(self, f"dish_{did}.pdf", f"Состав блюда: {dname}",
                   ["Продукт", "Грамм", "Ккал", "Б/Ж/У", "Категория"], rows)


# ---------- вкладка «Аналитика» ---------------------------------------------

class AnalyticsTab(QtWidgets.QWidget):
    """Гистограмма калорийности продуктов и круговая диаграмма по пользователям."""

    def __init__(self, db):
        super().__init__(); self.db = db
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel("<b>Калорийность продуктов (на 100 г)</b>"))
        self.chart1 = QtChart.QChart(); self.view1 = QtChart.QChartView(self.chart1)
        self.view1.setRenderHint(QtGui.QPainter.Antialiasing)
        v.addWidget(self.view1, 1)
        v.addWidget(QtWidgets.QLabel("<b>Распределение калорий по рационам пользователей</b>"))
        self.chart2 = QtChart.QChart(); self.view2 = QtChart.QChartView(self.chart2)
        self.view2.setRenderHint(QtGui.QPainter.Antialiasing)
        v.addWidget(self.view2, 1)
        self.refresh()

    @staticmethod
    def _short_name(full: str) -> str:
        """«Иванов Иван Иванович» → «Иванов И.И.»"""
        parts = (full or "").split()
        if len(parts) >= 3:
            return f"{parts[0]} {parts[1][:1]}.{parts[2][:1]}."
        if len(parts) == 2:
            return f"{parts[0]} {parts[1][:1]}."
        return full or ""

    def refresh(self) -> None:
        rows = self.db.query("SELECT name, calories FROM product ORDER BY calories DESC LIMIT 12")
        series = QtChart.QBarSeries()
        bar = QtChart.QBarSet("ккал/100г")
        cats = []
        for r in rows:
            bar.append(float(r["calories"]))
            cats.append(r["name"])
        series.append(bar)
        self.chart1.removeAllSeries()
        for ax in list(self.chart1.axes()):
            self.chart1.removeAxis(ax)
        self.chart1.addSeries(series)
        ax_x = QtChart.QBarCategoryAxis(); ax_x.append(cats)
        ax_y = QtChart.QValueAxis(); ax_y.setRange(0, max([float(r["calories"]) for r in rows] + [1]) * 1.1)
        self.chart1.addAxis(ax_x, QtCore.Qt.AlignBottom)
        self.chart1.addAxis(ax_y, QtCore.Qt.AlignLeft)
        series.attachAxis(ax_x); series.attachAxis(ax_y)
        self.chart1.setTitle("Самые калорийные продукты")
        self.chart1.legend().setVisible(False)

        rows = self.db.query(
            "SELECT u.full_name, COALESCE(SUM(rn.total_calories),0) AS k "
            "FROM app_user u LEFT JOIN ration_nutrition rn ON rn.user_id=u.id "
            "GROUP BY u.full_name HAVING COALESCE(SUM(rn.total_calories),0)>0 "
            "ORDER BY k DESC")
        total = sum(float(r["k"]) for r in rows) or 1.0
        pie = QtChart.QPieSeries()
        pie.setHoleSize(0.40)
        pie.setPieSize(0.65)
        for r in rows:
            v = float(r["k"])
            pct = v / total * 100
            short = self._short_name(r["full_name"])
            # Единый формат подписи (используется и в легенде, и на срезе).
            label = f"{short} — {v:.0f} ккал ({pct:.0f}%)"
            sl = pie.append(label, v)
            # На срезе показываем только у крупных, чтобы подписи не
            # наезжали друг на друга — у мелких всё равно видно в легенде.
            if pct >= 5.0:
                sl.setLabelVisible(True)
                sl.setLabelPosition(QtChart.QPieSlice.LabelOutside)
                f = sl.labelFont(); f.setPointSize(9); sl.setLabelFont(f)
                sl.setLabelArmLengthFactor(0.10)
            else:
                sl.setLabelVisible(False)
        self.chart2.removeAllSeries()
        self.chart2.addSeries(pie)
        self.chart2.setTitle("")  # заголовок уже над диаграммой в виджете
        lg = self.chart2.legend()
        lg.setAlignment(QtCore.Qt.AlignRight)
        lg.setMarkerShape(QtChart.QLegend.MarkerShapeCircle)
        f = lg.font(); f.setPointSize(9); lg.setFont(f)
        self.chart2.setMargins(QtCore.QMargins(8, 8, 8, 8))


# ---------- главное окно -----------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    logoutRequested = QtCore.pyqtSignal()

    def __init__(self, db: DB, user: dict):
        super().__init__()
        self.db = db; self.user = user
        is_admin = user["role"] == "admin"
        self.setWindowTitle(
            f"АС планирования рациона питания — "
            f"{'Администратор' if is_admin else 'Пользователь'}: {user['full_name']}")
        self.resize(1100, 720)

        self._build_menu(is_admin)

        tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(tabs)

        if is_admin:
            tabs.addTab(self._tab_users(),     "Пользователи")
            tabs.addTab(self._tab_categories(), "Категории")
            tabs.addTab(self._tab_products(),  "Продукты")
            tabs.addTab(self._tab_dishes(),    "Блюда")
            tabs.addTab(DishCompositionTab(db, readonly=False), "Состав блюд")
            tabs.addTab(self._tab_rations_all(), "Все рационы")
            tabs.addTab(AnalyticsTab(db),     "Аналитика")
        else:
            tabs.addTab(ProfileTab(db, user),  "Профиль / норма")
            tabs.addTab(RationsTab(db, user),  "Мои рационы")
            tabs.addTab(self._tab_dishes_ro(), "Каталог блюд")
            tabs.addTab(self._tab_products_ro(), "Справочник продуктов")
            tabs.addTab(DishCompositionTab(db, readonly=True), "Состав блюд")
            tabs.addTab(self._tab_user_excludes(), "Мои исключения")
            tabs.addTab(self._tab_user_favorites(), "Любимые блюда")
            tabs.addTab(AnalyticsTab(db),      "Аналитика")

        self.statusBar().showMessage(
            f"Подключение: {db.backend}  •  Пользователь: {user['login']} ({user['role']})")

    def _build_menu(self, is_admin: bool) -> None:
        mb = self.menuBar()
        mfile = mb.addMenu("Файл")
        a_logout = mfile.addAction("Выйти из учётной записи")
        a_logout.triggered.connect(self._do_logout)
        a_quit = mfile.addAction("Выход из программы")
        a_quit.triggered.connect(QtWidgets.QApplication.quit)
        mhelp = mb.addMenu("Справка")
        a_about = mhelp.addAction("О программе")
        a_about.triggered.connect(self._show_about)

    def _do_logout(self) -> None:
        self.logoutRequested.emit()
        self.close()

    def _show_about(self) -> None:
        info(self,
             "АС планирования рациона питания\n\n"
             "Курсовая работа по дисциплине «Базы данных».\n"
             "МГТУ им. Н.Э. Баумана, ИУ5-42Б.\n"
             "PostgreSQL + PyQt5.",
             "О программе")

    # --- admin tabs ---

    def _tab_users(self):
        return TableEditor(
            self.db,
            title="Пользователи",
            select_sql="SELECT id, login, role, full_name, age, sex, weight, height,"
                       " activity_level, goal FROM app_user ORDER BY id",
            columns=["Логин", "Роль", "ФИО", "Возр.", "Пол", "Вес", "Рост", "Активность", "Цель"],
            form_fields=[
                ("Логин", "login", "str"),
                ("Пароль", "pw", "str"),
                ("Роль", "role", "choice:user|admin"),
                ("ФИО", "fn", "str"),
                ("Возраст", "age", "int"),
                ("Пол", "sex", "choice:М|Ж"),
                ("Вес", "w", "float"),
                ("Рост", "h", "float"),
                ("Активность", "act", "choice:Низкий|Средний|Высокий"),
                ("Цель", "goal", "choice:Похудение|Поддержание|Набор массы"),
            ],
            insert_sql="INSERT INTO app_user (login, password_hash, role, full_name, age, sex,"
                       " weight, height, activity_level, goal) "
                       "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            update_sql="UPDATE app_user SET login=%s, password_hash=%s, role=%s, full_name=%s,"
                       " age=%s, sex=%s, weight=%s, height=%s, activity_level=%s, goal=%s "
                       "WHERE id=%s",
            delete_sql="DELETE FROM app_user WHERE id=%s",
            round_cols={6, 7},  # вес, рост
        )

    def _tab_categories(self):
        return TableEditor(
            self.db,
            title="Категории продуктов",
            select_sql="SELECT id, name FROM category ORDER BY name",
            columns=["Название"],
            form_fields=[("Название", "n", "str")],
            insert_sql="INSERT INTO category (name) VALUES (%s)",
            update_sql="UPDATE category SET name=%s WHERE id=%s",
            delete_sql="DELETE FROM category WHERE id=%s",
        )

    def _tab_products(self):
        return TableEditor(
            self.db,
            title="Продукты",
            select_sql="SELECT p.id, p.name AS pname, p.calories, p.proteins, p.fats, p.carbs,"
                       " c.name AS cname "
                       "FROM product p JOIN category c ON c.id=p.category_id ORDER BY p.name",
            columns=["Название", "Ккал", "Б", "Ж", "У", "Категория"],
            form_fields=[
                ("Название", "n", "str"),
                ("Ккал/100г", "k", "float"),
                ("Белки", "p", "float"),
                ("Жиры", "f", "float"),
                ("Углеводы", "c", "float"),
                ("Категория", "cat", "sql:SELECT id, name FROM category ORDER BY name"),
            ],
            insert_sql="INSERT INTO product (name, calories, proteins, fats, carbs, category_id) "
                       "VALUES (%s,%s,%s,%s,%s,%s)",
            update_sql="UPDATE product SET name=%s, calories=%s, proteins=%s, fats=%s, carbs=%s, "
                       "category_id=%s WHERE id=%s",
            delete_sql="DELETE FROM product WHERE id=%s",
            round_cols={2},  # ккал
        )

    def _tab_dishes(self):
        return TableEditor(
            self.db,
            title="Блюда",
            select_sql="SELECT d.id, d.name AS dname, d.dish_type, d.description,"
                       " dn.total_calories "
                       "FROM dish d LEFT JOIN dish_nutrition dn ON dn.dish_id=d.id ORDER BY d.name",
            columns=["Название", "Тип", "Описание", "Ккал (всего)"],
            form_fields=[
                ("Название", "n", "str"),
                ("Тип", "t", "choice:Завтрак|Обед|Ужин|Перекус|Десерт|Напиток"),
                ("Описание", "d", "str"),
            ],
            insert_sql="INSERT INTO dish (name, dish_type, description) VALUES (%s,%s,%s)",
            update_sql="UPDATE dish SET name=%s, dish_type=%s, description=%s WHERE id=%s",
            delete_sql="DELETE FROM dish WHERE id=%s",
            round_cols={4},
        )

    def _tab_rations_all(self):
        return TableEditor(
            self.db,
            title="Рационы всех пользователей",
            select_sql="SELECT r.id, u.full_name AS uname, r.name AS rname,"
                       " r.date_start, r.date_end, rn.total_calories "
                       "FROM ration r JOIN app_user u ON u.id=r.user_id "
                       "LEFT JOIN ration_nutrition rn ON rn.ration_id=r.id "
                       "ORDER BY r.date_start DESC",
            columns=["Пользователь", "Название", "Начало", "Конец", "Ккал"],
            form_fields=[],
            readonly=True,
            round_cols={5},
        )

    # --- user tabs ---

    def _tab_dishes_ro(self):
        return TableEditor(
            self.db,
            title="Каталог блюд",
            select_sql="SELECT d.id, d.name AS dname, d.dish_type, d.description,"
                       " dn.total_calories "
                       "FROM dish d LEFT JOIN dish_nutrition dn ON dn.dish_id=d.id ORDER BY d.name",
            columns=["Название", "Тип", "Описание", "Ккал"],
            form_fields=[], readonly=True,
            round_cols={4},
        )

    def _tab_products_ro(self):
        return TableEditor(
            self.db,
            title="Справочник продуктов",
            select_sql="SELECT p.id, p.name AS pname, p.calories, p.proteins, p.fats, p.carbs,"
                       " c.name AS cname "
                       "FROM product p JOIN category c ON c.id=p.category_id ORDER BY p.name",
            columns=["Название", "Ккал", "Б", "Ж", "У", "Категория"],
            form_fields=[], readonly=True,
            round_cols={2},
        )

    def _tab_user_excludes(self):
        uid = self.user["id"]
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)
        v.addWidget(QtWidgets.QLabel("<b>Исключённые продукты (не попадут в рацион)</b>"))
        tbl = QtWidgets.QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["id", "Продукт", "Категория"])
        tbl.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        tbl.setColumnHidden(0, True)
        tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        v.addWidget(tbl, 1)
        h = QtWidgets.QHBoxLayout()
        b_add = QtWidgets.QPushButton("Добавить продукт")
        b_del = QtWidgets.QPushButton("Удалить выбранное")
        h.addWidget(b_add); h.addWidget(b_del); h.addStretch(1)
        v.addLayout(h)

        def reload():
            rows = self.db.query(
                "SELECT p.id, p.name AS pname, c.name AS cname FROM user_excludes ue "
                "JOIN product p ON p.id=ue.product_id "
                "JOIN category c ON c.id=p.category_id WHERE ue.user_id=%s ORDER BY p.name",
                (uid,))
            tbl.setRowCount(len(rows))
            for i, r in enumerate(rows):
                tbl.setItem(i, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
                tbl.setItem(i, 1, QtWidgets.QTableWidgetItem(r["pname"]))
                tbl.setItem(i, 2, QtWidgets.QTableWidgetItem(r["cname"]))

        def add():
            # передаём db и parent. Создадим псевдо-родителя
            class _P:
                def __init__(s): s.db = self.db
            dlg = FormDialog(w if hasattr(w, "db") else self._with_db(w), "Добавить исключение", [
                ("Продукт", "p", "sql:SELECT id, name FROM product ORDER BY name"),
            ])
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                try:
                    self.db.execute(
                        "INSERT INTO user_excludes (user_id, product_id) VALUES (%s,%s)",
                        (uid, dlg.values["p"]))
                    reload()
                except Exception as e:
                    crit(w, str(e))

        def remove():
            idxs = tbl.selectionModel().selectedRows()
            if not idxs: return
            pid = int(tbl.item(idxs[0].row(), 0).text())
            self.db.execute("DELETE FROM user_excludes WHERE user_id=%s AND product_id=%s",
                            (uid, pid))
            reload()

        b_add.clicked.connect(add); b_del.clicked.connect(remove)
        w.db = self.db
        reload()
        return w

    def _with_db(self, w):
        w.db = self.db
        return w

    def _tab_user_favorites(self):
        uid = self.user["id"]
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)
        w.db = self.db
        v.addWidget(QtWidgets.QLabel("<b>Любимые блюда</b>"))
        tbl = QtWidgets.QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["id", "Блюдо", "Тип"])
        tbl.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        tbl.setColumnHidden(0, True)
        v.addWidget(tbl, 1)
        h = QtWidgets.QHBoxLayout()
        b_add = QtWidgets.QPushButton("Добавить блюдо")
        b_del = QtWidgets.QPushButton("Удалить")
        h.addWidget(b_add); h.addWidget(b_del); h.addStretch(1)
        v.addLayout(h)

        def reload():
            rows = self.db.query(
                "SELECT d.id, d.name AS dname, d.dish_type FROM user_favorites uf "
                "JOIN dish d ON d.id=uf.dish_id WHERE uf.user_id=%s ORDER BY d.name",
                (uid,))
            tbl.setRowCount(len(rows))
            for i, r in enumerate(rows):
                tbl.setItem(i, 0, QtWidgets.QTableWidgetItem(str(r["id"])))
                tbl.setItem(i, 1, QtWidgets.QTableWidgetItem(r["dname"]))
                tbl.setItem(i, 2, QtWidgets.QTableWidgetItem(r["dish_type"] or ""))

        def add():
            dlg = FormDialog(w, "Добавить в избранное", [
                ("Блюдо", "d", "sql:SELECT id, name FROM dish ORDER BY name"),
            ])
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                try:
                    self.db.execute(
                        "INSERT INTO user_favorites (user_id, dish_id) VALUES (%s,%s)",
                        (uid, dlg.values["d"]))
                    reload()
                except Exception as e:
                    crit(w, str(e))

        def remove():
            idxs = tbl.selectionModel().selectedRows()
            if not idxs: return
            did = int(tbl.item(idxs[0].row(), 0).text())
            self.db.execute("DELETE FROM user_favorites WHERE user_id=%s AND dish_id=%s",
                            (uid, did))
            reload()

        b_add.clicked.connect(add); b_del.clicked.connect(remove)
        reload()
        return w
