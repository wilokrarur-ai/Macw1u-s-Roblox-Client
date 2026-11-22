"""Games tab — real Roblox game discovery."""

from __future__ import annotations

import webbrowser
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout,
                                QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from core.games import Games
from ui.widgets import AsyncImageLabel, GlassCard, make_icon


class _FetchGames(QThread):
    done = Signal(dict, object)
    def __init__(self, games: Games, mode: str, kw: str = ""):
        super().__init__(); self.games = games; self.mode = mode; self.kw = kw
    def run(self):
        out = {}
        err = None
        try:
            if self.mode in ("popular", "trending"):
                # Roblox popular/trending sort requires auth — we don't fake it.
                # Surface local favorites + recently-viewed as the default view.
                out["list"] = []
                out["requires_auth"] = True
                out["reason"] = ("Roblox's popular/trending sort endpoint requires an "
                                 "authenticated session, which this client does not "
                                 "impersonate. Use the search box above to find real "
                                 "games, or browse your favorited / recently-viewed "
                                 "games from the Library tab.")
            elif self.mode == "search":
                out["list"] = self.games.search(self.kw, limit=12)
                out["requires_auth"] = False
        except Exception as e: err = e
        self.done.emit(out, err)


class GameCard(QFrame):
    def __init__(self, game: dict, services, parent_tab):
        super().__init__()
        self.game = game
        self.services = services
        self.parent_tab = parent_tab
        self.setFixedSize(280, 290)
        self.setStyleSheet("""
            QFrame { background: rgba(255,255,255,220); border: 1px solid rgba(124,92,255,40);
                     border-radius: 16px; }
            QFrame:hover { border-color: #7C5CFF; }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()

    def _build(self) -> None:
        l = QVBoxLayout(self); l.setContentsMargins(12, 12, 12, 12); l.setSpacing(6)
        thumb = AsyncImageLabel(self.services["cache"])
        thumb.setFixedSize(256, 140)
        thumb.setStyleSheet("background: rgba(124,92,255,30); border-radius: 10px;")
        thumb.load(self.game.get("thumbnail_url"))
        l.addWidget(thumb, 0, Qt.AlignmentFlag.AlignCenter)
        title = QLabel(self.game.get("name", ""))
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #1A1730;")
        title.setMaximumHeight(36)
        l.addWidget(title)
        creator = QLabel(self.game.get("creator", ""))
        creator.setStyleSheet("font-size: 10px; color: #8A85A3;")
        l.addWidget(creator)
        playing = self.game.get("playing")
        stats = QLabel(f"{playing:,} playing" if playing else "Live data")
        stats.setStyleSheet("font-size: 10px; color: #34C759; font-weight: 700;")
        l.addWidget(stats)
        btns = QHBoxLayout(); btns.setSpacing(6)
        play = QPushButton("Play")
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setStyleSheet("""
            QPushButton { background: #7C5CFF; color: white; border: none;
                          border-radius: 8px; padding: 7px 14px; font-weight: 600; font-size: 11px; }
            QPushButton:hover { background: #6B4DE8; }
        """)
        play.clicked.connect(self._play)
        details = QPushButton("Details")
        details.setCursor(Qt.CursorShape.PointingHandCursor)
        details.setStyleSheet("""
            QPushButton { background: rgba(124,92,255,30); color: #7C5CFF; border: none;
                          border-radius: 8px; padding: 7px 10px; font-weight: 600; font-size: 11px; }
            QPushButton:hover { background: rgba(124,92,255,60); }
        """)
        details.clicked.connect(self._details)
        btns.addWidget(play)
        btns.addWidget(details)
        btns.addStretch(1)
        fav = QPushButton("♥")
        fav.setFixedSize(30, 28)
        fav.setCursor(Qt.CursorShape.PointingHandCursor)
        is_fav = self.services["games"].is_favorite(int(self.game.get("universe_id") or 0))
        fav.setStyleSheet(self._fav_style(is_fav))
        fav.clicked.connect(lambda _=False, b=fav: self._toggle_fav(b))
        btns.addWidget(fav)
        l.addLayout(btns)

    def _fav_style(self, on: bool) -> str:
        if on:
            return "QPushButton { background: #FF3B30; border: none; border-radius: 8px; color: white; }"
        return "QPushButton { background: rgba(124,92,255,30); border: none; border-radius: 8px; color: #7C5CFF; }"

    def _toggle_fav(self, btn) -> None:
        added = self.services["games"].toggle_favorite(self.game)
        btn.setStyleSheet(self._fav_style(added))
        if added:
            self.services["notifier"].success("Favorited", self.game.get("name", ""))
        else:
            self.services["notifier"].info("Unfavorited", self.game.get("name", ""))

    def _play(self) -> None:
        self.services["games"].mark_viewed(self.game)
        self.parent_tab.open_gameplay(self.game)

    def _details(self) -> None:
        self.services["games"].mark_viewed(self.game)
        dlg = GameDetailsDialog(self.game, self.services, self)
        dlg.exec()


class GameDetailsDialog(QDialog):
    def __init__(self, game: dict, services, parent=None):
        super().__init__(parent)
        self.game = game
        self.services = services
        self.setWindowTitle("Game details")
        self.setModal(True)
        self.resize(560, 600)
        self._build()

    def _build(self) -> None:
        l = QVBoxLayout(self); l.setContentsMargins(20, 20, 20, 20); l.setSpacing(10)
        thumb = AsyncImageLabel(self.services["cache"])
        thumb.setFixedSize(520, 220)
        thumb.setStyleSheet("background: rgba(124,92,255,30); border-radius: 14px;")
        thumb.load(self.game.get("thumbnail_url"))
        l.addWidget(thumb)
        title = QLabel(self.game.get("name", ""))
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #1A1730;")
        l.addWidget(title)
        creator = QLabel(f"By {self.game.get('creator', '')}")
        creator.setStyleSheet("color: #7C5CFF; font-weight: 600;")
        l.addWidget(creator)
        desc = QLabel(self.game.get("description", "") or "No description available.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #1A1730; font-size: 13px;")
        l.addWidget(desc)
        # stats grid
        stats = QGridLayout()
        for i, (k, v) in enumerate([
            ("Playing", self.game.get("playing")), ("Visits", self.game.get("visits")),
            ("Max players", self.game.get("max_players")), ("Genre", self.game.get("genre")),
            ("Created", (self.game.get("created") or "")[:10]),
            ("Updated", (self.game.get("updated") or "")[:10]),
        ]):
            kl = QLabel(k); kl.setStyleSheet("color: #8A85A3; font-size: 11px;")
            vl = QLabel(str(v) if v is not None else "—")
            vl.setStyleSheet("color: #1A1730; font-size: 13px; font-weight: 600;")
            stats.addWidget(kl, i // 2, (i % 2) * 2)
            stats.addWidget(vl, i // 2, (i % 2) * 2 + 1)
        l.addLayout(stats)
        # buttons
        btns = QHBoxLayout()
        play = QPushButton("Launch via Roblox Player")
        play.setObjectName("primary")
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.clicked.connect(self._play)
        btns.addWidget(play)
        web = QPushButton("Open on roblox.com")
        web.setCursor(Qt.CursorShape.PointingHandCursor)
        web.clicked.connect(self._web)
        btns.addWidget(web)
        creator_link = QPushButton("Creator profile")
        creator_link.setCursor(Qt.CursorShape.PointingHandCursor)
        creator_link.clicked.connect(self._creator)
        btns.addWidget(creator_link)
        l.addLayout(btns)

    def _play(self) -> None:
        ok, msg = self.services["launcher"].launch(self.game)
        self.services["notifier"].info("Launch", msg)

    def _web(self) -> None:
        webbrowser.open(self.services["launcher"].web_url(self.game))

    def _creator(self) -> None:
        url = self.game.get("creator_url")
        if url:
            webbrowser.open(url)


class GamesTab(QWidget):
    def __init__(self, services: dict[str, Any], main_window) -> None:
        super().__init__()
        self.services = services
        self.main = main_window
        self._build()
        self.on_show()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)
        title = QLabel("Games")
        title.setObjectName("bigtitle")
        outer.addWidget(title)
        sub = QLabel("Real Roblox experiences from the official games API.")
        sub.setStyleSheet("color: #8A85A3; font-size: 13px;")
        outer.addWidget(sub)

        # Filter row
        fr = QHBoxLayout(); fr.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Roblox games…")
        self.search.setFixedHeight(38)
        self.search.returnPressed.connect(lambda: self._fetch("search"))
        fr.addWidget(self.search, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.setFixedHeight(38)
        self.mode_combo.addItem("Popular")
        self.mode_combo.addItem("Trending")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        fr.addWidget(self.mode_combo)
        go = QPushButton("Search")
        go.setObjectName("primary")
        go.setFixedHeight(38)
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.clicked.connect(lambda: self._fetch("search"))
        fr.addWidget(go)
        outer.addLayout(fr)

        # Results scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setSpacing(12)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.scroll.setWidget(self.grid_widget)
        outer.addWidget(self.scroll, 1)

        # loading label
        self.loading = QLabel("Loading popular games…")
        self.loading.setStyleSheet("color: #8A85A3;")
        outer.addWidget(self.loading)

    def _on_mode_changed(self, _idx: int) -> None:
        self._fetch("trending" if self.mode_combo.currentIndex() == 1 else "popular")

    def on_show(self) -> None:
        self._fetch("popular")

    def _fetch(self, mode: str) -> None:
        kw = self.search.text().strip()
        self.loading.setText("Fetching games…")
        self.loading.show()
        self._thread = _FetchGames(self.services["games"], mode, kw)
        self._thread.done.connect(self._on_data)
        self._thread.start()

    def _on_data(self, data: dict, err) -> None:
        self.loading.hide()
        # clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if err is not None:
            ph = QLabel(f"Could not load games: {err}")
            ph.setStyleSheet("color: #FF3B30;")
            ph.setWordWrap(True)
            self.grid.addWidget(ph, 0, 0)
            return
        games = data.get("list", []) or []
        if not games:
            if data.get("requires_auth"):
                # Honest limitation card + the user's own favorited / viewed games
                self._show_limitation_card(data.get("reason", ""))
                self._show_local_games()
            else:
                ph = QLabel("No games found. Try a different search term.")
                ph.setStyleSheet("color: #8A85A3;")
                ph.setWordWrap(True)
                self.grid.addWidget(ph, 0, 0)
            return
        cols = 4
        for i, g in enumerate(games):
            r, c = divmod(i, cols)
            card = GameCard(g, self.services, self)
            self.grid.addWidget(card, r, c)

    def _show_limitation_card(self, reason: str) -> None:
        card = QFrame()
        card.setStyleSheet("""
            QFrame { background: rgba(255, 149, 0, 25); border: 1px solid rgba(255, 149, 0, 80);
                     border-radius: 14px; }
        """)
        l = QVBoxLayout(card); l.setContentsMargins(18, 14, 18, 14); l.setSpacing(6)
        title = QLabel("Popular & Trending games require an authenticated Roblox session")
        title.setStyleSheet("color: #C77600; font-size: 13px; font-weight: 700;")
        title.setWordWrap(True)
        l.addWidget(title)
        body = QLabel(reason)
        body.setStyleSheet("color: #5B5478; font-size: 12px;")
        body.setWordWrap(True)
        l.addWidget(body)
        self.grid.addWidget(card, 0, 0, 1, 4)

    def _show_local_games(self) -> None:
        """Show the user's favorited + recently-viewed games as a real fallback."""
        favs = self.services["games"].list_favorites()
        viewed = self.services["games"].list_viewed(limit=8)
        local = []
        seen = set()
        for r in favs + viewed:
            uid = int(r.get("universe_id") or 0)
            if uid and uid not in seen:
                seen.add(uid)
                local.append({
                    "universe_id": uid,
                    "root_place_id": r.get("root_place_id"),
                    "name": r.get("name", "Untitled"),
                    "creator": r.get("creator", ""),
                    "thumbnail_url": r.get("thumbnail_url"),
                    "playing": None,
                    "visits": None,
                    "description": "",
                })
        if not local:
            empty = QLabel("Tip: use the search box above to find real Roblox games, "
                           "then favorite them to see them here.")
            empty.setStyleSheet("color: #8A85A3; font-size: 12px;")
            empty.setWordWrap(True)
            self.grid.addWidget(empty, 1, 0, 1, 4)
            return
        header = QLabel("Your favorited & recently viewed games")
        header.setStyleSheet("color: #1A1730; font-size: 13px; font-weight: 700;")
        self.grid.addWidget(header, 1, 0, 1, 4)
        cols = 4
        for i, g in enumerate(local[:8]):
            r, c = divmod(i, cols)
            card = GameCard(g, self.services, self)
            self.grid.addWidget(card, 2 + r, c)

    def open_gameplay(self, game: dict) -> None:
        self.main.open_gameplay_window(game)
