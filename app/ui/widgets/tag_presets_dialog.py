from __future__ import annotations
import re

from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QInputDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QMenu,
)

from app.ui.styles import Components, Palette, Typography, Spacing


# -----------------------------
# Tree node helpers
# -----------------------------
def _is_tag_node(n: Any) -> bool:
    return isinstance(n, dict) and n.get("type") == "tag"


def _is_folder_node(n: Any) -> bool:
    return isinstance(n, dict) and n.get("type") == "folder"


def _make_folder(name: str, children: Optional[List[dict]] = None) -> dict:
    name = (name or "").strip().upper()
    return {"type": "folder", "name": name, "children": list(children or [])}

def _canon_tag(value: str) -> str:
    s = (value or "").strip().casefold()
    s = re.sub(r"\s+", "", s)
    return s

def _make_tag(value: str) -> dict:
    return {"type": "tag", "value": value}


def _normalize_preset_value_to_root_folder(v: Any) -> dict:
    """
    Backward compatibility:
    - old: List[str]
    - new: {"type":"folder","name":..., "children":[...]}
    """
    if isinstance(v, list):
        children = []
        for t in v:
            t = str(t).strip()
            if t:
                children.append(_make_tag(t))
        return _make_folder("КОРЕНЬ НАБОРА", children)

    if _is_folder_node(v):
        name = str(v.get("name") or "КОРЕНЬ НАБОРА")
        children = v.get("children") if isinstance(v.get("children"), list) else []
        norm_children: List[dict] = []
        for c in children:
            if _is_tag_node(c):
                value = str(c.get("value") or "").strip()
                if value:
                    norm_children.append(_make_tag(value))
            elif _is_folder_node(c):
                norm_children.append(_normalize_preset_value_to_root_folder(c))
        return _make_folder(name if name else "КОРЕНЬ НАБОРА", norm_children)

    return _make_folder("КОРЕНЬ НАБОРА", [])


class TagPresetsDialog(QDialog):
    """
    Presets format:
        Dict[str, FolderNode]
    where FolderNode = {"type":"folder","name": str, "children":[TagNode|FolderNode...]}
    """

    ROLE_PATH = int(Qt.ItemDataRole.UserRole)          # tuple[int, ...] path from root children
    ROLE_NODE_TYPE = int(Qt.ItemDataRole.UserRole) + 1 # "root"|"folder"|"tag"

    def __init__(
        self,
        presets: Dict[str, Any],
        parent=None,
        *,
        window_title="Наборы",
        tag_color=Palette.PRIMARY,
    ):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.resize(800, 520)
        self.setStyleSheet(Components.dialog())

        # Normalize
        self.presets: Dict[str, dict] = {}
        for k, v in (presets or {}).items():
            name = str(k).strip()
            if not name:
                continue
            self.presets[name] = _normalize_preset_value_to_root_folder(v)

        self._btn_style = f"""
        QPushButton {{
            background-color: {Palette.BG_DARK_3};
            border: 1px solid {Palette.BORDER_PRIMARY};
            border-radius: {Spacing.RADIUS_NORMAL}px;
            color: {Palette.TEXT};
            font-size: 12px;
            font-weight: {Typography.WEIGHT_BOLD};
            padding: 0;
        }}
        QPushButton:hover {{
            background-color: {Palette.BG_LIGHT};
            border-color: {Palette.PRIMARY};
            color: {Palette.PRIMARY};
        }}
        QPushButton:pressed {{ background-color: {Palette.BG_DARK_2}; }}
        QPushButton:disabled {{
            background-color: {Palette.BG_DARK};
            border-color: {Palette.DIVIDER};
            color: {Palette.TEXT_MUTED};
        }}
        """

        layout = QHBoxLayout(self)
        layout.setSpacing(Spacing.LG)

        # LEFT
        left = QVBoxLayout()
        lbl_left = QLabel("СПИСОК НАБОРОВ")
        lbl_left.setStyleSheet(Components.section_title())
        left.addWidget(lbl_left)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {Palette.BG_DARK_3};
                border: 1px solid {Palette.BORDER_SOFT};
                color: {Palette.TEXT};
            }}
            QListWidget::item:selected {{
                background: {Palette.with_alpha(tag_color, 0.2)};
                color: {tag_color};
            }}
        """)
        for name in sorted(self.presets.keys()):
            self._add_list_item(name)
        left.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        for txt, func in [("✚", self._add_preset), ("━", self._delete_preset), ("Переименовать", self._rename_preset)]:
            b = QPushButton(txt)
            b.setMinimumSize(30, 25)
            b.setStyleSheet(self._btn_style)
            b.clicked.connect(func)
            b.setAutoDefault(False)
            b.setDefault(False)
            btn_row.addWidget(b)
        btn_row.addStretch(0)
        left.addLayout(btn_row)

        # RIGHT
        right = QVBoxLayout()
        lbl_right = QLabel("СТРУКТУРА НАБОРА")
        lbl_right.setStyleSheet(Components.section_title())
        right.addWidget(lbl_right)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {Palette.BG_LIGHT};
                border: 1px solid {Palette.BORDER_SOFT};
                color: {Palette.TEXT};
                border-radius: {Spacing.RADIUS_NORMAL}px;
            }}
            QTreeWidget::item:selected {{
                background: {Palette.with_alpha(tag_color, 0.16)};
                color: {Palette.TEXT};
            }}
        """)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        right.addWidget(self.tree, stretch=1)

        tools = QHBoxLayout()
        self.btn_add_folder = self._mk_btn("📁 Папка", self._add_folder)
        self.btn_add_tag = self._mk_btn("🏷 Тег", self._add_tag)
        self.btn_rename_node = self._mk_btn("Переименовать", self._rename_node)
        self.btn_delete_node = self._mk_btn("Удалить", self._delete_node)
        for b in [self.btn_add_folder, self.btn_add_tag, self.btn_rename_node, self.btn_delete_node]:
            tools.addWidget(b)
        tools.addStretch(1)
        right.addLayout(tools)

        hint = QLabel("Набор в меню ★ вставляет только теги корня; папка — теги рекурсивно.")
        hint.setStyleSheet(Components.muted_label() if hasattr(Components, "muted_label") else Components.panel())
        right.addWidget(hint)

        btn_box = QHBoxLayout()
        b_close = QPushButton("Закрыть")
        b_close.setMinimumSize(30, 25)
        b_close.setStyleSheet(self._btn_style)
        b_close.clicked.connect(self.accept)
        b_close.setAutoDefault(False)
        b_close.setDefault(False)
        btn_box.addStretch()
        btn_box.addWidget(b_close)
        right.addLayout(btn_box)

        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

        self.list_widget.currentItemChanged.connect(self._on_preset_changed)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    # -----------------------------
    # UI utils
    # -----------------------------
    def _mk_btn(self, text: str, handler):
        b = QPushButton(text)
        b.setMinimumSize(30, 25)
        b.setStyleSheet(self._btn_style)
        b.clicked.connect(handler)
        b.setAutoDefault(False)
        b.setDefault(False)
        return b

    def _add_list_item(self, name: str):
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, name)
        self.list_widget.addItem(item)

    def _current_preset_name(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _get_current_root_folder(self) -> Optional[dict]:
        name = self._current_preset_name()
        if not name:
            return None
        return self.presets.get(name)

    def _ensure_preset_selected(self) -> Optional[dict]:
        root = self._get_current_root_folder()
        if root:
            return root

        name, ok = QInputDialog.getText(self, "Новый набор", "Имя:")
        if not (ok and name.strip()):
            return None

        name = name.strip()

        if name in self.presets:
            # select existing
            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                if it and it.data(Qt.ItemDataRole.UserRole) == name:
                    self.list_widget.setCurrentRow(i)
                    break
            return self._get_current_root_folder()

        # create new
        self.presets[name] = _make_folder("КОРЕНЬ НАБОРА", [])
        self._add_list_item(name)
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)
        self.tree.setFocus()
        return self._get_current_root_folder()

    # -----------------------------
    # Preset operations (left)
    # -----------------------------
    def _add_preset(self):
        name, ok = QInputDialog.getText(self, "Новый набор", "Имя:")
        if not (ok and name.strip()):
            return
        name = name.strip()
        if name in self.presets:
            QMessageBox.warning(self, "Ошибка", "Набор с таким именем уже существует.")
            return
        self.presets[name] = _make_folder("КОРЕНЬ НАБОРА", [])
        self._add_list_item(name)
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)

    def _rename_preset(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        old = item.data(Qt.ItemDataRole.UserRole)
        name, ok = QInputDialog.getText(self, "Переименовать", "Имя:", text=old)
        if not (ok and name.strip()):
            return
        name = name.strip()
        if name == old:
            return
        if name in self.presets:
            QMessageBox.warning(self, "Ошибка", "Набор с таким именем уже существует.")
            return
        self.presets[name] = self.presets.pop(old)
        item.setText(name)
        item.setData(Qt.ItemDataRole.UserRole, name)

    def _delete_preset(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if name in self.presets:
            del self.presets[name]
        self.list_widget.takeItem(self.list_widget.row(item))
        self.tree.clear()

    def _on_preset_changed(self, curr, prev):
        self.tree.clear()
        if not curr:
            return
        name = curr.data(Qt.ItemDataRole.UserRole)
        root = self.presets.get(name)
        if not root:
            return
        self._populate_tree(root)
        self.tree.expandAll()

    # -----------------------------
    # Path <-> Node
    # -----------------------------
    def _node_by_path(self, root: dict, path: Tuple[int, ...]) -> dict:
        node: dict = root
        for idx in path:
            node = (node.get("children") or [])[idx]
        return node

    def _folder_by_path(self, root: dict, path: Tuple[int, ...]) -> dict:
        node = self._node_by_path(root, path) if path else root
        if not _is_folder_node(node):
            raise ValueError("Path does not point to a folder")
        return node

    def _selected_path_and_type(self) -> Tuple[Tuple[int, ...], str]:
        """
        Returns (path, node_type), where:
        - root: path=()
        - folder/tag: path=(...)
        """
        it = self.tree.currentItem()
        if not it:
            return (), "корень набора"
        p = it.data(0, self.ROLE_PATH)
        t = it.data(0, self.ROLE_NODE_TYPE)
        if p is None:
            p = ()
        if not t:
            t = "корень набора"
        return tuple(p), str(t)
    
    def _collect_tag_keys_in_folder(self, folder: dict, *, skip_index: Optional[int] = None) -> set[str]:
        keys: set[str] = set()
        children = folder.get("children") or []
        for i, ch in enumerate(children):
            if skip_index is not None and i == skip_index:
                continue
            if _is_tag_node(ch):
                k = _canon_tag(str(ch.get("value") or ""))
                if k:
                    keys.add(k)
        return keys

    # -----------------------------
    # Tree render
    # -----------------------------
    def _populate_tree(self, root_folder: dict):
        root_item = QTreeWidgetItem([f"📂 {root_folder.get('name', 'КОРЕНЬ НАБОРА')}"])
        root_item.setData(0, self.ROLE_PATH, ())
        root_item.setData(0, self.ROLE_NODE_TYPE, "КОРЕНЬ НАБОРА")
        self.tree.addTopLevelItem(root_item)

        def add_children(parent_item: QTreeWidgetItem, folder_node: dict, parent_path: Tuple[int, ...]):
            children = folder_node.get("children") or []
            for i, ch in enumerate(children):
                path = parent_path + (i,)
                if _is_folder_node(ch):
                    it = QTreeWidgetItem([f"📁 {ch.get('name', '')}"])
                    it.setData(0, self.ROLE_PATH, path)
                    it.setData(0, self.ROLE_NODE_TYPE, "folder")
                    parent_item.addChild(it)
                    add_children(it, ch, path)
                elif _is_tag_node(ch):
                    it = QTreeWidgetItem([f"🏷 {ch.get('value', '')}"])
                    it.setData(0, self.ROLE_PATH, path)
                    it.setData(0, self.ROLE_NODE_TYPE, "tag")
                    parent_item.addChild(it)

        add_children(root_item, root_folder, ())

    def _refresh_current_tree(self):
        cur = self.list_widget.currentItem()
        self._on_preset_changed(cur, None)

    # -----------------------------
    # Actions
    # -----------------------------
    def _add_folder(self):
        root = self._ensure_preset_selected()
        if not root:
            return

        sel_path, sel_type = self._selected_path_and_type()

        # target folder:
        if sel_type == "folder":
            target_folder = self._folder_by_path(root, sel_path)
        elif sel_type == "tag" and sel_path:
            target_folder = self._folder_by_path(root, sel_path[:-1])
        else:
            target_folder = root

        name, ok = QInputDialog.getText(self, "Новая папка", "Имя папки:")
        if not (ok and name.strip()):
            return

        target_folder.setdefault("children", []).append(_make_folder(name.strip(), []))
        self._refresh_current_tree()

    def _add_tag(self):
        root = self._ensure_preset_selected()
        if not root:
            return

        sel_path, sel_type = self._selected_path_and_type()

        # target folder:
        if sel_type == "folder":
            target_folder = self._folder_by_path(root, sel_path)
        elif sel_type == "tag" and sel_path:
            target_folder = self._folder_by_path(root, sel_path[:-1])
        else:
            target_folder = root

        value, ok = QInputDialog.getText(self, "Новый тег", "Тег:")
        if not (ok and value.strip()):
            return

        value = value.strip()
        key = _canon_tag(value)
        if not key:
            return

        existing = self._collect_tag_keys_in_folder(target_folder)
        if key in existing:
            QMessageBox.warning(self, "Дубликат тега", f"Тег '{value}' уже существует в этой папке.")
            return

        target_folder.setdefault("children", []).append(_make_tag(value))
        self._refresh_current_tree()

    def _rename_node(self):
        root = self._get_current_root_folder()
        if not root:
            return

        sel_path, sel_type = self._selected_path_and_type()
        if sel_type == "КОРЕНЬ НАБОРА":
            QMessageBox.information(self, "Информация", "Корневую папку набора переименовывать не нужно.")
            return

        node = self._node_by_path(root, sel_path)

        if sel_type == "folder":
            old = str(node.get("name") or "")
            name, ok = QInputDialog.getText(self, "Переименовать папку", "Имя:", text=old)
            if ok and name.strip():
                node["name"] = name.strip().upper()

        elif sel_type == "tag":
            old = str(node.get("value") or "")
            name, ok = QInputDialog.getText(self, "Переименовать тег", "Тег:", text=old)
            if ok and name.strip():
                new_value = name.strip()
                new_key = _canon_tag(new_value)
                if not new_key:
                    return

                parent_path = sel_path[:-1]
                idx = sel_path[-1]

                parent_folder = self._folder_by_path(root, parent_path) if parent_path else root
                existing = self._collect_tag_keys_in_folder(parent_folder, skip_index=idx)

                if new_key in existing:
                    QMessageBox.warning(self, "Дубликат тега", f"Тег '{new_value}' уже существует в этой папке.")
                    return

                node["value"] = new_value

        self._refresh_current_tree()

    def _delete_node(self):
        root = self._get_current_root_folder()
        if not root:
            return

        sel_path, sel_type = self._selected_path_and_type()
        if sel_type == "КОРЕНЬ НАБОРА":
            QMessageBox.information(self, "Информация", "Корень удалять нельзя.")
            return
        if not sel_path:
            return

        parent_path = sel_path[:-1]
        idx = sel_path[-1]
        parent = self._folder_by_path(root, parent_path) if parent_path else root

        children = parent.get("children") or []
        if 0 <= idx < len(children):
            del children[idx]
            parent["children"] = children

        self._refresh_current_tree()

    def _on_tree_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {Palette.BG_DARK_2}; color: {Palette.TEXT}; border: 1px solid {Palette.BORDER_SOFT}; }}"
        )

        act_add_folder = menu.addAction("📁 Добавить папку")
        act_add_tag = menu.addAction("🏷 Добавить тег")
        act_rename = menu.addAction("✏ Переименовать")
        act_delete = menu.addAction("🗑 Удалить")

        act = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if not act:
            return
        if act == act_add_folder:
            self._add_folder()
        elif act == act_add_tag:
            self._add_tag()
        elif act == act_rename:
            self._rename_node()
        elif act == act_delete:
            self._delete_node()

    # -----------------------------
    # Public API
    # -----------------------------
    def get_presets(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for k, v in self.presets.items():
            out[k] = _normalize_preset_value_to_root_folder(v)
        return out