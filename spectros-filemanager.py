#!/usr/bin/env python3
# spectros-filemanager.py — SpectrOS File Manager v2.1
# ArCom Corporation — FreeBSD — GTK3
# Correccions: TreeModelSort, AppChooserDialog, icones, context menu

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GdkPixbuf, GLib, Pango, Gdk
import os
import subprocess
import mimetypes
import stat
import datetime
import threading
import shutil

# ── Icones per extensió ───────────────────────────────────────────────────────
EXT_ICON = {
    "pdf":  "application-pdf",
    "doc":  "x-office-document",  "docx": "x-office-document",
    "odt":  "x-office-document",
    "xls":  "x-office-spreadsheet", "xlsx": "x-office-spreadsheet",
    "ods":  "x-office-spreadsheet",
    "ppt":  "x-office-presentation", "pptx": "x-office-presentation",
    "txt":  "text-x-generic",     "md":   "text-x-generic",
    "png":  "image-x-generic",    "jpg":  "image-x-generic",
    "jpeg": "image-x-generic",    "gif":  "image-x-generic",
    "bmp":  "image-x-generic",    "svg":  "image-x-generic",
    "webp": "image-x-generic",
    "mp3":  "audio-x-generic",    "ogg":  "audio-x-generic",
    "flac": "audio-x-generic",    "wav":  "audio-x-generic",
    "mp4":  "video-x-generic",    "mkv":  "video-x-generic",
    "avi":  "video-x-generic",    "mov":  "video-x-generic",
    "zip":  "package-x-generic",  "tar":  "package-x-generic",
    "gz":   "package-x-generic",  "bz2":  "package-x-generic",
    "xz":   "package-x-generic",  "7z":   "package-x-generic",
    "py":   "text-x-script",      "sh":   "text-x-script",
    "js":   "text-x-script",      "c":    "text-x-script",
    "cpp":  "text-x-script",      "h":    "text-x-script",
    "rs":   "text-x-script",
}

IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
TEXT_EXTS  = {"txt", "md", "py", "sh", "c", "cpp", "h", "rs", "js",
              "json", "xml", "html", "css", "conf", "cfg", "ini", "log",
              "toml", "yaml", "yml"}

FALLBACK_ICONS        = ["text-x-generic", "gtk-file", "application-octet-stream"]
FALLBACK_FOLDER_ICONS = ["folder", "gtk-directory"]


def human_size(n):
    try:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if n < 1024:
                return f"{n:.0f} {unit}"
            n /= 1024
    except Exception:
        pass
    return "?"


def safe_load_icon(theme, icon_name, size, fallbacks):
    for name in [icon_name] + fallbacks:
        try:
            pb = theme.load_icon(name, size, Gtk.IconLookupFlags.FORCE_SIZE)
            if pb:
                return pb
        except Exception:
            continue
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, size, size)
    pb.fill(0x888888FF)
    return pb


def file_icon_name(path):
    if os.path.isdir(path):
        return "folder", FALLBACK_FOLDER_ICONS
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return EXT_ICON.get(ext, "text-x-generic"), FALLBACK_ICONS


class FileManagerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="🗂️  SpectrOS FileManager")
        self.set_default_size(1280, 800)
        self.history      = []
        self.future       = []
        self.current_path = os.path.expanduser("~")
        self._icon_theme  = Gtk.IconTheme.get_default()

        self._apply_css()
        self._build_ui()
        self._build_context_menu()
        self.navigate(self.current_path, push=False)
        self.show_all()

    def _apply_css(self):
        css = b"""
        window { background-color: #1e2127; }
        .header-bar {
            background: linear-gradient(135deg, #1a3a5c 0%, #0d2137 100%);
            border-bottom: 2px solid #2e6da4;
            padding: 0 8px; min-height: 44px;
        }
        .nav-btn {
            background: transparent; color: #90caf9;
            border: none; border-radius: 4px;
            padding: 4px 8px; font-size: 16px; min-width: 32px;
        }
        .nav-btn:hover    { background-color: #1e3a5f; }
        .nav-btn:disabled { color: #2e3a48; }
        .path-entry {
            background-color: #1a1e24; color: #e0e0e0;
            border: 1px solid #37474f; border-radius: 4px;
            padding: 4px 8px; font-family: monospace;
            font-size: 13px; min-width: 380px;
        }
        .sidebar { background-color: #1a1e24; border-right: 1px solid #2e3540; }
        .sidebar-section {
            font-size: 10px; font-weight: bold; color: #546e7a;
            text-transform: uppercase; letter-spacing: 1px;
            padding: 8px 12px 2px 12px;
        }
        row.sidebar-row { padding: 4px 8px; }
        row.sidebar-row:selected { background-color: #1e3a5f; }
        row.sidebar-row:hover    { background-color: #252932; }
        .sidebar-label { font-size: 13px; color: #b0bec5; }
        .file-list { background-color: #1e2127; color: #b0bec5; }
        .file-list row          { padding: 2px 0; }
        .file-list row:selected { background-color: #1e3a5f; }
        .file-list row:hover    { background-color: #252932; }
        .preview-panel  { background-color: #1a1e24; border-left: 1px solid #2e3540; }
        .preview-title  { font-size: 13px; font-weight: bold; color: #90caf9; padding: 10px 12px 4px 12px; }
        .preview-meta   { font-size: 11px; color: #78909c; padding: 0 12px 4px 12px; }
        .preview-text   { font-family: monospace; font-size: 11px; color: #78909c;
                          background-color: #141720; padding: 8px; }
        .status-bar   { background-color: #141720; border-top: 1px solid #2e3540; padding: 4px 12px; }
        .status-label { font-size: 11px; color: #546e7a; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.get_style_context().add_class("header-bar")

        self.back_btn   = Gtk.Button(label="◀")
        self.fwd_btn    = Gtk.Button(label="▶")
        self.up_btn     = Gtk.Button(label="▲")
        self.home_btn   = Gtk.Button(label="🏠")
        self.reload_btn = Gtk.Button(label="↻")

        for btn in [self.back_btn, self.fwd_btn, self.up_btn,
                    self.home_btn, self.reload_btn]:
            btn.get_style_context().add_class("nav-btn")

        self.back_btn.connect("clicked", self._go_back)
        self.fwd_btn.connect("clicked", self._go_forward)
        self.up_btn.connect("clicked", self._go_up)
        self.home_btn.connect("clicked",
            lambda b: self.navigate(os.path.expanduser("~")))
        self.reload_btn.connect("clicked",
            lambda b: self.navigate(self.current_path, push=False))

        self.path_entry = Gtk.Entry()
        self.path_entry.get_style_context().add_class("path-entry")
        self.path_entry.connect("activate", self._path_entered)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Cercar...")
        self.search_entry.set_size_request(180, -1)
        self.search_entry.connect("search-changed", self._on_search)

        for w in [self.back_btn, self.fwd_btn, self.up_btn,
                  self.home_btn, self.reload_btn, self.path_entry]:
            toolbar.pack_start(w, False, False, 0)
        toolbar.pack_end(self.search_entry, False, False, 0)
        root.pack_start(toolbar, False, False, 0)

        # Panells
        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_paned.set_position(200)
        root.pack_start(main_paned, True, True, 0)

        # Sidebar
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar_box.get_style_context().add_class("sidebar")
        sidebar_box.set_size_request(200, -1)
        self.sidebar_list = Gtk.ListBox()
        self.sidebar_list.get_style_context().add_class("sidebar")
        self.sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar_list.connect("row-activated", self._sidebar_activated)
        self._build_sidebar()
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.add(self.sidebar_list)
        sidebar_box.pack_start(sidebar_scroll, True, True, 0)

        center_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        center_paned.set_position(720)

        # TreeView
        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.store = Gtk.ListStore(
            GdkPixbuf.Pixbuf, str, str, str, str, str, int, int
        )
        self.filter_store = self.store.filter_new()
        self.filter_store.set_visible_func(self._filter_func)

        self.tree = Gtk.TreeView(model=self.filter_store)
        self.tree.get_style_context().add_class("file-list")
        self.tree.set_headers_visible(True)
        self.tree.set_activate_on_single_click(False)
        self.tree.connect("row-activated", self._row_activated)
        self.tree.connect("cursor-changed", self._row_selected)
        self.tree.connect("button-press-event", self._on_button_press)

        icon_r = Gtk.CellRendererPixbuf()
        name_r = Gtk.CellRendererText()
        name_r.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        size_r = Gtk.CellRendererText()
        size_r.set_property("xalign", 1.0)
        date_r = Gtk.CellRendererText()
        type_r = Gtk.CellRendererText()

        col_name = Gtk.TreeViewColumn("Nom")
        col_name.pack_start(icon_r, False)
        col_name.pack_start(name_r, True)
        col_name.add_attribute(icon_r, "pixbuf", 0)
        col_name.add_attribute(name_r, "text", 1)
        col_name.set_sort_column_id(1)
        col_name.set_min_width(260)
        col_name.set_expand(True)
        col_name.set_resizable(True)

        col_size = Gtk.TreeViewColumn("Mida", size_r, text=2)
        col_size.set_sort_column_id(6)
        col_size.set_min_width(80)
        col_size.set_resizable(True)

        col_date = Gtk.TreeViewColumn("Modificat", date_r, text=3)
        col_date.set_sort_column_id(3)
        col_date.set_min_width(130)
        col_date.set_resizable(True)

        col_type = Gtk.TreeViewColumn("Tipus", type_r, text=4)
        col_type.set_min_width(90)
        col_type.set_resizable(True)

        for col in [col_name, col_size, col_date, col_type]:
            self.tree.append_column(col)

        self.store.set_sort_column_id(7, Gtk.SortType.DESCENDING)

        list_scroll.add(self.tree)
        center_paned.pack1(list_scroll, True, True)

        # Preview
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        preview_box.get_style_context().add_class("preview-panel")
        preview_box.set_size_request(260, -1)

        self.preview_name = Gtk.Label(label="")
        self.preview_name.get_style_context().add_class("preview-title")
        self.preview_name.set_halign(Gtk.Align.START)
        self.preview_name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        preview_box.pack_start(self.preview_name, False, False, 0)

        self.preview_meta = Gtk.Label(label="")
        self.preview_meta.get_style_context().add_class("preview-meta")
        self.preview_meta.set_halign(Gtk.Align.START)
        self.preview_meta.set_line_wrap(True)
        preview_box.pack_start(self.preview_meta, False, False, 0)

        self.preview_img = Gtk.Image()
        self.preview_img.set_margin_top(8)
        self.preview_img.set_margin_start(8)
        self.preview_img.set_margin_end(8)
        preview_box.pack_start(self.preview_img, False, False, 0)

        preview_text_scroll = Gtk.ScrolledWindow()
        preview_text_scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.preview_buf = Gtk.TextBuffer()
        self.preview_tv  = Gtk.TextView(buffer=self.preview_buf)
        self.preview_tv.set_editable(False)
        self.preview_tv.set_cursor_visible(False)
        self.preview_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.preview_tv.get_style_context().add_class("preview-text")
        preview_text_scroll.add(self.preview_tv)
        preview_box.pack_start(preview_text_scroll, True, True, 0)

        center_paned.pack2(preview_box, False, False)
        main_paned.pack1(sidebar_box, False, False)
        main_paned.pack2(center_paned, True, True)

        # Status bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        status_box.get_style_context().add_class("status-bar")
        self.status_lbl = Gtk.Label(label="")
        self.status_lbl.get_style_context().add_class("status-label")
        self.status_lbl.set_halign(Gtk.Align.START)
        status_box.pack_start(self.status_lbl, True, True, 0)
        root.pack_start(status_box, False, False, 0)

    def _build_sidebar(self):
        locations = [
            ("LLOCS", None),
            ("🏠  Inici",        os.path.expanduser("~")),
            ("🖥️  Escriptori",   os.path.expanduser("~/Desktop")),
            ("📄  Documents",    os.path.expanduser("~/Documents")),
            ("📥  Descàrregues", os.path.expanduser("~/Downloads")),
            ("🖼️  Imatges",     os.path.expanduser("~/Pictures")),
            ("🎵  Música",       os.path.expanduser("~/Music")),
            ("🎥  Vídeos",       os.path.expanduser("~/Videos")),
            ("SISTEMA", None),
            ("💻  Arrel (/)",    "/"),
            ("🔧  /usr/local",   "/usr/local"),
            ("📦  /var",         "/var"),
            ("⚙️  /etc",         "/etc"),
            ("⚙️  SpectrOS",     "/usr/local/bin/spectros"),
        ]
        for name, path in locations:
            if path is None:
                lbl = Gtk.Label(label=name)
                lbl.get_style_context().add_class("sidebar-section")
                lbl.set_halign(Gtk.Align.START)
                row = Gtk.ListBoxRow()
                row.set_selectable(False)
                row.set_activatable(False)
                row.add(lbl)
            else:
                lbl = Gtk.Label(label=name)
                lbl.get_style_context().add_class("sidebar-label")
                lbl.set_halign(Gtk.Align.START)
                lbl.set_margin_start(8)
                row = Gtk.ListBoxRow()
                row.get_style_context().add_class("sidebar-row")
                row.nav_path = path
                row.add(lbl)
            self.sidebar_list.add(row)

    def _build_context_menu(self):
        self.ctx_menu = Gtk.Menu()
        items = [
            ("📂  Obrir",       self._ctx_open),
            ("📋  Copiar ruta", self._ctx_copy_path),
            ("✏️  Canviar nom", self._ctx_rename),
            (None, None),
            ("ℹ️  Propietats",  self._ctx_properties),
            (None, None),
            ("🗑️  Suprimir",   self._ctx_delete),
        ]
        for label, cb in items:
            if label is None:
                self.ctx_menu.append(Gtk.SeparatorMenuItem())
            else:
                mi = Gtk.MenuItem(label=label)
                if cb:
                    mi.connect("activate", cb)
                self.ctx_menu.append(mi)
        self.ctx_menu.show_all()

    # ── Navegació ─────────────────────────────────────────────────────────────

    def navigate(self, path, push=True):
        path = os.path.realpath(os.path.expanduser(str(path)))
        if not os.path.isdir(path):
            self.status_lbl.set_text(f"⚠  No és un directori: {path}")
            return
        if push and self.current_path and self.current_path != path:
            self.history.append(self.current_path)
            self.future.clear()
        self.current_path = path
        self.path_entry.set_text(path)
        self._update_nav_buttons()
        self._load_directory(path)

    def _update_nav_buttons(self):
        self.back_btn.set_sensitive(bool(self.history))
        self.fwd_btn.set_sensitive(bool(self.future))
        self.up_btn.set_sensitive(self.current_path != "/")

    def _go_back(self, btn):
        if self.history:
            self.future.append(self.current_path)
            self.navigate(self.history.pop(), push=False)

    def _go_forward(self, btn):
        if self.future:
            self.history.append(self.current_path)
            self.navigate(self.future.pop(), push=False)

    def _go_up(self, btn):
        parent = os.path.dirname(self.current_path)
        if parent != self.current_path:
            self.navigate(parent)

    def _path_entered(self, entry):
        self.navigate(entry.get_text().strip())

    def _sidebar_activated(self, lb, row):
        if hasattr(row, "nav_path"):
            self.navigate(row.nav_path)

    # ── Carregar directori ────────────────────────────────────────────────────

    def _load_directory(self, path):
        self.store.clear()
        self.preview_name.set_text("")
        self.preview_meta.set_text("")
        self.preview_img.clear()
        self.preview_buf.set_text("")

        try:
            entries = os.listdir(path)
        except PermissionError:
            self.status_lbl.set_text(f"⚠  Sense permís: {path}")
            return
        except Exception as e:
            self.status_lbl.set_text(f"⚠  Error: {e}")
            return

        entries.sort(key=lambda x: x.lower())
        dirs  = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        files = [e for e in entries if not os.path.isdir(os.path.join(path, e))]

        count = 0
        errors = 0

        for name in dirs + files:
            full = os.path.join(path, name)
            try:
                st       = os.stat(full)
                is_dir   = os.path.isdir(full)
                size_b   = st.st_size
                size_str = "—" if is_dir else human_size(size_b)
                mtime    = datetime.datetime.fromtimestamp(
                    st.st_mtime).strftime("%d/%m/%Y %H:%M")
                type_str = "Carpeta" if is_dir else self._get_type(name)

                icon_name, fallbacks = file_icon_name(full)
                pixbuf = safe_load_icon(
                    self._icon_theme, icon_name, 20, fallbacks)

                self.store.append([
                    pixbuf, name, size_str, mtime, type_str,
                    full, size_b, 1 if is_dir else 0
                ])
                count += 1
            except Exception:
                errors += 1

        status = f"{count} elements  ({len(dirs)} carpetes, {len(files)} fitxers)"
        if errors:
            status += f"  ·  ⚠ {errors} inaccessibles"
        self.status_lbl.set_text(status)

    def _get_type(self, name):
        mime, _ = mimetypes.guess_type(name)
        if mime:
            return mime.split("/")[-1].upper()
        ext = os.path.splitext(name)[1].lstrip(".").upper()
        return ext if ext else "Fitxer"

    def _filter_func(self, model, it, data):
        query = self.search_entry.get_text().lower().strip()
        if not query:
            return True
        name = model.get_value(it, 1) or ""
        return query in name.lower()

    def _on_search(self, entry):
        self.filter_store.refilter()

    # ── Preview ───────────────────────────────────────────────────────────────

    def _row_selected(self, tree):
        try:
            model, it = tree.get_selection().get_selected()
            if not it:
                return
            path = model.get_value(it, 5)
            name = model.get_value(it, 1)
            if path:
                self._show_preview(path, name)
        except Exception:
            pass

    def _show_preview(self, path, name):
        self.preview_name.set_text(name)
        self.preview_img.clear()
        self.preview_buf.set_text("")
        try:
            st    = os.stat(path)
            size  = human_size(st.st_size)
            mtime = datetime.datetime.fromtimestamp(
                st.st_mtime).strftime("%d/%m/%Y %H:%M")
            perms = oct(stat.S_IMODE(st.st_mode))
            self.preview_meta.set_text(
                f"Mida: {size}  ·  {mtime}  ·  {perms}")
        except Exception:
            self.preview_meta.set_text("")

        ext = os.path.splitext(name)[1].lstrip(".").lower()

        if ext in IMAGE_EXTS:
            threading.Thread(
                target=self._load_image_preview,
                args=(path,), daemon=True).start()
        elif ext in TEXT_EXTS:
            threading.Thread(
                target=self._load_text_preview,
                args=(path,), daemon=True).start()
        elif os.path.isdir(path):
            try:
                items = sorted(os.listdir(path))
                self.preview_buf.set_text(
                    f"{len(items)} elements:\n\n" + "\n".join(items[:30]))
            except Exception:
                self.preview_buf.set_text("(sense accés)")
        else:
            self.preview_buf.set_text(
                f"Tipus: {self._get_type(name)}\n\nSense previsualització.")

    def _load_image_preview(self, path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, 240, 240, True)
            GLib.idle_add(self.preview_img.set_from_pixbuf, pixbuf)
        except Exception as e:
            GLib.idle_add(
                self.preview_buf.set_text, f"Error carregant imatge:\n{e}")

    def _load_text_preview(self, path):
        try:
            with open(path, "r", errors="replace") as f:
                content = f.read(4000)
            GLib.idle_add(self.preview_buf.set_text, content)
        except Exception as e:
            GLib.idle_add(
                self.preview_buf.set_text, f"Error llegint fitxer:\n{e}")

    def _row_activated(self, tree, tree_path, column):
        try:
            model = tree.get_model()
            it    = model.get_iter(tree_path)
            full  = model.get_value(it, 5)
            if os.path.isdir(full):
                self.navigate(full)
            else:
                subprocess.Popen(["xdg-open", full],
                                 stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # ── Menú contextual ───────────────────────────────────────────────────────

    def _on_button_press(self, widget, event):
        if event.button == 3:
            self.ctx_menu.popup_at_pointer(event)
            return True
        return False

    def _selected_path(self):
        try:
            model, it = self.tree.get_selection().get_selected()
            if it:
                return model.get_value(it, 5)
        except Exception:
            pass
        return None

    def _ctx_open(self, mi):
        path = self._selected_path()
        if not path:
            return
        if os.path.isdir(path):
            self.navigate(path)
        else:
            subprocess.Popen(["xdg-open", path], stderr=subprocess.DEVNULL)

    def _ctx_copy_path(self, mi):
        path = self._selected_path()
        if path:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(path, -1)

    def _ctx_rename(self, mi):
        path = self._selected_path()
        if not path:
            return
        old_name = os.path.basename(path)

        dlg = Gtk.Dialog(title="Canviar nom",
                         transient_for=self, modal=True)
        dlg.add_button("Cancel·lar", Gtk.ResponseType.CANCEL)
        dlg.add_button("Canviar", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)

        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(12);   box.set_margin_bottom(12)

        lbl = Gtk.Label(label=f"Nou nom per a '{old_name}':")
        lbl.set_halign(Gtk.Align.START)
        entry = Gtk.Entry()
        entry.set_text(old_name)
        entry.select_region(0, -1)
        entry.set_activates_default(True)
        box.pack_start(lbl, False, False, 0)
        box.pack_start(entry, False, False, 0)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            new_name = entry.get_text().strip()
            if new_name and new_name != old_name:
                new_path = os.path.join(os.path.dirname(path), new_name)
                try:
                    os.rename(path, new_path)
                    self.navigate(self.current_path, push=False)
                except Exception as e:
                    self._show_error(str(e))
        dlg.destroy()

    def _ctx_properties(self, mi):
        path = self._selected_path()
        if not path:
            return
        try:
            st = os.stat(path)
            msg = (
                f"Nom:       {os.path.basename(path)}\n"
                f"Ruta:      {path}\n"
                f"Mida:      {human_size(st.st_size)}\n"
                f"Modificat: {datetime.datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M')}\n"
                f"Creat:     {datetime.datetime.fromtimestamp(st.st_ctime).strftime('%d/%m/%Y %H:%M')}\n"
                f"Permisos:  {oct(stat.S_IMODE(st.st_mode))}\n"
                f"UID:       {st.st_uid}  /  GID: {st.st_gid}\n"
            )
        except Exception as e:
            msg = str(e)
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"Propietats — {os.path.basename(path)}")
        dlg.format_secondary_text(msg)
        dlg.run(); dlg.destroy()

    def _ctx_delete(self, mi):
        path = self._selected_path()
        if not path:
            return
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Suprimir '{os.path.basename(path)}'?")
        dlg.format_secondary_text("Aquesta acció no es pot desfer.")
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.navigate(self.current_path, push=False)
            except Exception as e:
                self._show_error(str(e))

    def _show_error(self, msg):
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text="Error")
        dlg.format_secondary_text(msg)
        dlg.run(); dlg.destroy()


class FileManagerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.arcom.spectros.filemanager")

    def do_activate(self):
        FileManagerWindow(self).show()


if __name__ == "__main__":
    FileManagerApp().run()
