# ui/group_summary_page.py
"""本组学习小结页：毛玻璃卡片列出本组单词及艾宾浩斯复习天数。"""
import flet as ft

from ui.theme import glass, glass_button, page_shell, TEXT_COLOR


def build_group_summary_page(page: ft.Page) -> ft.Control:
    completed = page.learn_state.get('completed', []) if hasattr(page, 'learn_state') else []

    rows = []
    for it in completed:
        rows.append(
            glass(
                ft.Row(
                    [
                        ft.Text(it['word'], size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(it.get('trans', ''), size=14, color=ft.Colors.GREY),
                        ft.Text(f"{it['interval']} 天", size=16, color=ft.Colors.GREEN),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=14, radius=14,
            )
        )

    if not rows:
        rows.append(ft.Text("本组没有已学完的单词", size=16, color=ft.Colors.GREY))

    list_col = ft.Column(rows, spacing=10)

    bottom_bar = ft.Container(
        content=ft.Row(
            [
                glass_button("再学一组", lambda e: page.go("/learn"), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900),
                glass_button("休息一下", lambda e: page.go("/learn_stats")),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        ),
        padding=ft.padding.symmetric(vertical=12),
    )

    layout = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Text("本组学习小结", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
            ft.Text(f"共 {len(completed)} 个单词", size=13, color=ft.Colors.GREY),
            list_col,
        ],
        alignment=ft.MainAxisAlignment.START,
        spacing=20,
    )

    return page_shell(
        page,
        ft.Column(
            [
                ft.Container(content=layout, expand=True, padding=ft.padding.symmetric(horizontal=16, vertical=12)),
                bottom_bar,
            ],
            spacing=0,
            expand=True,
        ),
    )
