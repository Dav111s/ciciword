# ui/review_page.py
"""复习模式：三档反馈（记住/模糊/忘记）+ 词义详情两阶段交互。

- 记住：记忆概率上升、间隔拉长，移出队列。
- 模糊：记忆概率适度下调、间隔中等，移出队列（下次提前复习）。
- 忘记：记忆概率大幅下降、间隔缩短，换到队尾稍后重试（不退关卡）。
"""
import flet as ft

from config import get_current_book, is_spelling_test_enabled
from data import db, universe
from srs import ReviewFeedback
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def build_review_page(page: ft.Page) -> ft.Control:
    page.review_state = {
        'queue': [], 'index': 0, 'tentative_feedback': ReviewFeedback.REMEMBER,
        '_answered': False, 'reviewed': {},
    }

    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回首页", on_click=lambda e: page.go("/"))
    title_text = ft.Text("复习模式", size=20, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    remain_text = ft.Text("", size=13, color=ft.Colors.GREY)

    word_text = ft.Text("", size=26, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    word_card = glass(
        ft.Column([word_text], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        height=180, radius=20,
    )

    remember_btn = glass_button("记住🟢", lambda e: _answer(page, ReviewFeedback.REMEMBER), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    hazy_btn = glass_button("模糊🟡", lambda e: _answer(page, ReviewFeedback.HAZY), tint=ft.Colors.AMBER_400, opacity=0.32, text_color=ft.Colors.AMBER_900)
    forget_btn = glass_button("忘记🔴", lambda e: _answer(page, ReviewFeedback.FORGET), tint=ft.Colors.RED_400, opacity=0.32, text_color=ft.Colors.RED_900)
    action_row = ft.Row([remember_btn, hazy_btn, forget_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=12, wrap=True)

    status_text = ft.Text("请在无提示的情况下选择记住/模糊/忘记", size=14)

    detail_switcher = ft.AnimatedSwitcher(
        content=ft.Container(),
        transition=ft.AnimatedSwitcherTransition.SCALE,
        duration=350,
        switch_in_curve=ft.AnimationCurve.EASE_OUT,
        switch_out_curve=ft.AnimationCurve.EASE_IN,
    )

    next_btn = glass_button("下一个", lambda e: _commit(page), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    bottom_bar = ft.Container(
        content=ft.Row([next_btn], alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.padding.symmetric(vertical=12),
        visible=False,
    )

    def _render():
        state = page.review_state
        detail_switcher.content = ft.Container()
        bottom_bar.visible = False
        state['_answered'] = False
        if not state['queue']:
            word_card.visible = False
            action_row.visible = False
            remain_text.value = ""
            status_text.value = "🎉 今日复习已完成！"
            page.update()
            return
        word = state['queue'][state['index']]
        word_card.visible = True
        action_row.visible = True
        word_text.value = word['word']
        remain_text.value = f"剩余 {len(state['queue'])} 个单词"
        status_text.value = "请在无提示的情况下选择记住/模糊/忘记"
        page.update()

    def _answer(page, feedback):
        state = page.review_state
        if not state['queue'] or state['_answered']:
            return
        state['_answered'] = True
        state['tentative_feedback'] = feedback
        word = state['queue'][state['index']]

        if feedback == ReviewFeedback.REMEMBER:
            head, hcolor, tint = "✓ 记住", ft.Colors.GREEN_900, ft.Colors.GREEN_400
        elif feedback == ReviewFeedback.HAZY:
            head, hcolor, tint = "◐ 模糊", ft.Colors.AMBER_900, ft.Colors.AMBER_400
        else:
            head, hcolor, tint = "✗ 忘记", ft.Colors.RED_900, ft.Colors.RED_400

        action_row.visible = False
        tags = universe.get_stage_tags(word['word'])
        detail_controls = [
            ft.Text(head, size=17, weight=ft.FontWeight.BOLD, color=hcolor),
            ft.Text(word['word'], size=22, weight=ft.FontWeight.BOLD),
            ft.Text(f"释义：{word['trans']}", size=15),
        ]
        if tags:
            detail_controls.append(
                ft.Text("  ".join(f"#{t}" for t in tags), size=13, color=SUB_TEXT_COLOR))
        detail_switcher.content = glass(
            ft.Column(
                detail_controls,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
            ),
            tint=tint, opacity=0.32, radius=18, padding=18,
        )
        next_btn.visible = True
        bottom_bar.visible = True
        page.update()

    def _commit(page):
        state = page.review_state
        if not state['queue']:
            return
        word = state['queue'][state['index']]
        wid = word['id']
        fb = state['tentative_feedback']
        db.submit_review_three_tier(wid, fb)
        state['reviewed'][wid] = {'id': wid, 'word': word['word'], 'trans': word['trans']}

        if fb == ReviewFeedback.FORGET:
            # 忘记：换到队尾稍后重试
            state['queue'].append(state['queue'].pop(state['index']))
        else:
            # 记住/模糊：移出队列（SRS 已排期）
            state['queue'].pop(state['index'])
        if state['index'] >= len(state['queue']):
            state['index'] = 0
        if not state['queue']:
            _finish_review(page)
        else:
            _render()

    def _finish_review(page):
        state = page.review_state
        words = list(state['reviewed'].values())
        page.spelling_state = {'words': words, 'return_route': '/'}
        # 复习完成后：样本充足且满足训练条件时，后台增量训练神经网络（不阻塞界面）
        try:
            from ai.memory_model import should_train, train_async
            if should_train():
                train_async()
        except Exception:
            pass
        if is_spelling_test_enabled() and words:
            page.go("/spelling")
        else:
            _render()

    page.review_state['render'] = _render

    layout = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Row([back_btn, title_text], alignment=ft.MainAxisAlignment.START),
            remain_text,
            word_card,
            action_row,
            status_text,
            detail_switcher,
        ],
        spacing=16,
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


def load_review_data(page: ft.Page):
    """供 main.py 调用：加载复习队列并渲染。"""
    state = page.review_state
    book = get_current_book()
    state['queue'] = db.get_review_queue(book)
    state['index'] = 0
    state['reviewed'] = {}
    state['render']()
