# ui/batch_page.py
"""批量单词识别页：粘贴大量单词，清洗去重，逐个在总词库检索并标注学段；
识别结果可一键保存到自定义词本（仅保存总词库内已有释义的单词）。"""
import flet as ft

from data import word_matcher
from data import wordbooks as wb
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR

STAGE_COLORS = {
    "考研": ft.Colors.PURPLE_400,
    "四级": ft.Colors.BLUE_400,
    "六级": ft.Colors.INDIGO_400,
    "高考": ft.Colors.ORANGE_400,
    "中考": ft.Colors.GREEN_400,
}


def build_batch_page(page: ft.Page) -> ft.Control:
    input_field = ft.TextField(
        label="粘贴单词（空格 / 换行分隔）",
        multiline=True, min_lines=5, max_lines=12,
    )
    result_list = ft.ListView(expand=True, spacing=8)
    save_btn = glass_button(
        "保存结果到词本", lambda e: _save(page), tint=ft.Colors.BLUE_400, opacity=0.32, text_color=ft.Colors.BLUE_900,
    )
    page.batch_results = []

    def _run(e):
        result_list.controls.clear()
        items = word_matcher.recognize(input_field.value or "")
        page.batch_results = items
        if not items:
            result_list.controls.append(ft.Text("请先粘贴单词", color=SUB_TEXT_COLOR))
        else:
            for w, trans, stages in items:
                if trans is None:
                    tag_text = "【无内置分类】"
                    tag_color = ft.Colors.RED
                else:
                    tag_text = "  ".join(f"#{s}" for s in stages) if stages else "（无学段标签）"
                    tag_color = ft.Colors.GREY
                content = ft.Column(
                    [
                        ft.Row(
                            [ft.Text(w, size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                             ft.Text(trans or "", size=14, color=SUB_TEXT_COLOR)],
                            spacing=8, wrap=True,
                        ),
                        ft.Text(tag_text, size=12, color=tag_color),
                    ],
                    spacing=2,
                )
                result_list.controls.append(glass(content, padding=10, radius=12))
            result_list.controls.append(save_btn)
        result_list.update()

    back_btn = glass_button("返回词库", lambda e: page.go("/wordbook"))
    run_btn = glass_button("开始识别", _run, tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)

    return page_shell(
        page,
        ft.Container(
            content=ft.Column(
                [
                    ft.Row([back_btn, ft.Text("批量识别", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)],
                           alignment=ft.MainAxisAlignment.START),
                    input_field,
                    ft.Row([run_btn], alignment=ft.MainAxisAlignment.END),
                    ft.Text("识别结果", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    result_list,
                ],
                spacing=14, expand=True,
            ),
            expand=True, padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )


def _save(page):
    """把识别结果（含释义的）保存到自定义词本。"""
    items = getattr(page, 'batch_results', []) or []
    savable = [(w, t) for w, t, _s in items if t]
    if not savable:
        _snack(page, "没有可保存的单词（均无内置释义）", ft.Colors.RED)
        return

    name_field = ft.TextField(label="保存到词本名称", value="我的词本", autofocus=True)
    hint = ft.Text(f"将保存 {len(savable)} 个词；无内置分类的单词会被跳过。", size=12, color=ft.Colors.GREY)

    def _do(_):
        dialog = page._active_dialog
        name = name_field.value.strip()
        if not name:
            _snack(page, "词本名称不能为空", ft.Colors.RED)
            return
        wb.create_wordbook(name)
        ok = 0
        for w, t in savable:
            if wb.add_word(name, w, t):
                ok += 1
        _close(page, dialog)
        _snack(page, f"已保存 {ok}/{len(savable)} 个单词到「{name}」", ft.Colors.GREEN)

    dialog = ft.AlertDialog(
        title=ft.Text("保存到自定义词本"),
        content=ft.Column([name_field, hint]),
        actions=[
            ft.TextButton("取消", on_click=lambda _: _close(page, dialog)),
            ft.ElevatedButton("保存", on_click=_do),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page._active_dialog = dialog
    page.open(dialog)


def _close(page, dialog):
    page.close(dialog)


def _snack(page, msg, color):
    page.open(ft.SnackBar(ft.Text(msg), bgcolor=color))
