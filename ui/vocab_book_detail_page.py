# ui/vocab_book_detail_page.py
"""词本详情浏览页：滚动展示词本内全部单词（单词/释义/例句）。"""
import flet as ft

from data.db import get_words_by_book
from ui.theme import glass, page_shell, TEXT_COLOR


def build_vocab_book_detail_page(page: ft.Page) -> ft.Control:
    book_name = getattr(page, 'current_view_book', None)
    words = get_words_by_book(book_name) if book_name else []

    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回词库", on_click=lambda e: page.go("/wordbook"))
    title_text = ft.Text(book_name or "词本详情", size=20, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    count_text = ft.Text(f"{len(words)} 个单词", size=13, color=ft.Colors.GREY)

    items = []
    for w in words:
        example = (w.get('example') or '').strip()
        items.append(
            glass(
                ft.Column(
                    [
                        ft.Text(w['word'], size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(w['trans'] or '', size=14),
                        ft.Text(f"例句：{example}", size=13, italic=True, color=ft.Colors.GREY) if example else ft.Text(""),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                radius=14, padding=12,
            )
        )

    if not items:
        items.append(ft.Text("该词本暂无单词", size=16))

    list_view = ft.ListView(controls=items, expand=True, spacing=10)

    return page_shell(
        page,
        ft.Column(
            [
                ft.Container(
                    content=ft.Row([back_btn, title_text], alignment=ft.MainAxisAlignment.START),
                    padding=ft.padding.symmetric(horizontal=8, vertical=6),
                ),
                ft.Container(content=count_text, padding=ft.padding.symmetric(horizontal=8)),
                ft.Container(content=list_view, expand=True, padding=ft.padding.symmetric(horizontal=16)),
            ],
            expand=True,
            spacing=8,
        ),
    )
