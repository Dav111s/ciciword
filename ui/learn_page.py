# ui/learn_page.py
"""学习模式：三关闯关流程（毛玻璃卡片 + 动画 + 词义详情两阶段交互）。

- 第1关：四选一（4 个固定统一尺寸的毛玻璃释义词条方块，选正确中文释义）。
- 第2关：单词 + 例句提示（例句仅来自 CSV 导入），【认识/不认识】。
- 第3关：无提示，只展示单词，【认识/不认识】。

规则：
- 任意一关答错/不认识 -> 本单词回到第 1 关，切换到组内另一个单词。
- 一关答对 -> 进入本单词下一关；三关全过即学完。

交互：
- 点击选项/认识/不认识 -> 动画展开正确词义详情卡片（答对绿色毛玻璃，答错红色毛玻璃）。
- 答对：底部出现【下一个】【记错了】；答错：底部仅【下一个】。
"""
import random
import time

import flet as ft

from config import get_current_book, get_study_group_size, add_study_duration, is_spelling_test_enabled
from data import db, universe
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def build_learn_page(page: ft.Page) -> ft.Control:
    page.learn_state = {
        'mode': 'learn',
        'group_ids': [],
        'pending': [],
        'completed': [],
        'current_id': None,
        'start_time': time.time(),
        'mcq_correct_index': 0,
        'tentative_correct': True,
    }

    # ---- 顶栏：返回、进度、收藏、标记熟词 ----
    back_btn = ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="返回首页", on_click=lambda e: page.go("/"))
    favorite_btn = ft.IconButton(icon=ft.Icons.STAR_BORDER, tooltip="收藏", on_click=lambda e: _toggle_favorite(page))
    known_btn = ft.TextButton("标记熟词", on_click=lambda e: _mark_known(page))
    progress_text = ft.Text("", size=13, color=ft.Colors.GREY)

    # ---- 单词卡 ----
    word_text = ft.Text("", size=26, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    word_card = glass(
        ft.Column([word_text], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        height=170, radius=20,
    )

    # ---- 第1关：4 个固定统一尺寸的毛玻璃释义词条方块 ----
    option_col = ft.Column(spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    option_area = ft.Container(content=option_col, visible=False)

    # ---- 第2关：例句提示（仅 CSV 导入） ----
    example_text = ft.Text("", size=15, italic=True, text_align=ft.TextAlign.CENTER)
    example_card = glass(
        ft.Column([example_text], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=18, radius=16,
    )
    example_card.visible = False

    # ---- 第3关：无提示 ----
    level3_hint = ft.Text("请在无提示的情况下判断", size=13, color=ft.Colors.ORANGE, visible=False)

    # ---- 认识/不认识（第2/3关） ----
    known_action = glass_button("认识", lambda e: _answer(page, True), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    unknown_action = glass_button("不认识", lambda e: _answer(page, False), tint=ft.Colors.RED_400, opacity=0.32, text_color=ft.Colors.RED_900)
    action_row = ft.Row([known_action, unknown_action], alignment=ft.MainAxisAlignment.CENTER, spacing=16, visible=False)

    # ---- 词义详情（动画展开） ----
    detail_switcher = ft.AnimatedSwitcher(
        content=ft.Container(),
        transition=ft.AnimatedSwitcherTransition.SCALE,
        duration=350,
        switch_in_curve=ft.AnimationCurve.EASE_OUT,
        switch_out_curve=ft.AnimationCurve.EASE_IN,
    )

    # ---- 底部按钮（答完出现） ----
    next_btn = glass_button("下一个", lambda e: _commit(page, None), tint=ft.Colors.GREEN_400, opacity=0.32, text_color=ft.Colors.GREEN_900)
    flip_btn = glass_button("记错了", lambda e: _commit(page, True), tint=ft.Colors.ORANGE, opacity=0.32, text_color=ft.Colors.ORANGE_900)
    bottom_bar = ft.Container(
        content=ft.Row([next_btn, flip_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=16),
        padding=ft.padding.symmetric(vertical=12),
        visible=False,
    )

    def _build_mcq(word):
        state = page.learn_state
        correct = word['trans']
        distractors = [d for d in db.get_distractors(word['id'], get_current_book(), 3) if d != correct]
        options = [correct] + distractors
        while len(options) < 4:
            options.append("（暂无干扰项）")
        options = options[:4]
        random.shuffle(options)
        state['mcq_correct_index'] = options.index(correct)
        option_col.controls = [
            glass(
                ft.Text(opt, size=15, text_align=ft.TextAlign.CENTER),
                width=300, height=76, padding=12, radius=14, ink=True,
                alignment=ft.alignment.center,
                on_click=lambda e, i=idx: _answer(page, i == state['mcq_correct_index']),
            )
            for idx, opt in enumerate(options)
        ]

    def _render_question():
        state = page.learn_state
        detail_switcher.content = ft.Container()
        bottom_bar.visible = False

        if state['current_id'] is None:
            progress_text.value = ""
            word_text.value = "暂无新词可学，去词库导入或切换词库吧"
            favorite_btn.visible = False
            known_btn.visible = False
            option_area.visible = False
            example_card.visible = False
            level3_hint.visible = False
            action_row.visible = False
            page.update()
            return

        word = db.get_word_by_id(state['current_id'])
        stage = int(word.get('stage') or 1)
        progress_text.value = f"本组进度 {len(state['completed'])}/{len(state['group_ids'])}"
        word_text.value = word['word']

        favorite_btn.visible = True
        known_btn.visible = True
        favorite_btn.icon = ft.Icons.STAR if word.get('favorite') else ft.Icons.STAR_BORDER

        option_area.visible = (stage == 1)
        example_card.visible = (stage == 2)
        level3_hint.visible = (stage == 3)
        action_row.visible = (stage in (2, 3))

        if stage == 1:
            _build_mcq(word)
        elif stage == 2:
            example_text.value = f"例句：{word['example']}" if word.get('example') else ""
        page.update()

    def _answer(page, correct):
        state = page.learn_state
        if state['current_id'] is None or state.get('_answered'):
            return
        state['_answered'] = True
        state['tentative_correct'] = correct
        word = db.get_word_by_id(state['current_id'])

        option_area.visible = False
        example_card.visible = False
        level3_hint.visible = False
        action_row.visible = False

        tags = universe.get_stage_tags(word['word'])
        detail_controls = [
            ft.Text("✓ 答对了" if correct else "✗ 答错了", size=17, weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREEN_900 if correct else ft.Colors.RED_900),
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
            tint=ft.Colors.GREEN_400 if correct else ft.Colors.RED_400,
            opacity=0.32, radius=18, padding=18,
        )

        next_btn.visible = True
        flip_btn.visible = correct
        bottom_bar.visible = True
        page.update()

    def _commit(page, flip):
        state = page.learn_state
        wid = state['current_id']
        if wid is None:
            return
        is_correct = state['tentative_correct']
        if flip:
            is_correct = False
        word, interval, completed = db.submit_answer(wid, is_correct, 'learn')
        if completed:
            state['completed'].append({
                'id': wid, 'word': word['word'], 'trans': word['trans'], 'interval': interval,
            })
            if wid in state['pending']:
                state['pending'].remove(wid)
        state['_answered'] = False
        _next(page)

    def _next(page):
        state = page.learn_state
        if not state['pending']:
            _finish_group(page)
            return
        candidates = [w for w in state['pending'] if w != state['current_id']]
        if not candidates:
            candidates = list(state['pending'])
        state['current_id'] = random.choice(candidates)
        _render_question()

    def _finish_group(page):
        state = page.learn_state
        add_study_duration(int(time.time() - state['start_time']))
        words = [{'id': it['id'], 'word': it['word'], 'trans': it['trans']} for it in state['completed']]
        page.spelling_state = {'words': words, 'return_route': '/summary'}
        if is_spelling_test_enabled() and words:
            page.go("/spelling")
        else:
            page.go("/summary")

    def _toggle_favorite(page):
        wid = page.learn_state['current_id']
        if wid is None:
            return
        word = db.get_word_by_id(wid)
        new_val = 0 if word.get('favorite') else 1
        db.set_word_favorite(wid, new_val)
        favorite_btn.icon = ft.Icons.STAR if new_val else ft.Icons.STAR_BORDER
        page.update()

    def _mark_known(page):
        state = page.learn_state
        wid = state['current_id']
        if wid is None:
            return
        word = db.mark_word_known(wid)
        state['completed'].append({
            'id': wid, 'word': word['word'], 'trans': word['trans'], 'interval': 30,
        })
        if wid in state['pending']:
            state['pending'].remove(wid)
        state['_answered'] = False
        _next(page)

    page.learn_state['render'] = _render_question

    layout = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Row(
                [back_btn, ft.Container(progress_text, expand=True, alignment=ft.alignment.center), favorite_btn, known_btn],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            word_card,
            option_area,
            example_card,
            level3_hint,
            action_row,
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


def load_learn_data(page: ft.Page):
    """供 main.py 调用：加载一组新词并渲染。"""
    state = page.learn_state
    book = get_current_book()
    group = db.get_learn_queue(book, get_study_group_size())
    state['group_ids'] = [w['id'] for w in group]
    state['pending'] = [w['id'] for w in group]
    state['completed'] = []
    state['current_id'] = random.choice(state['pending']) if state['pending'] else None
    state['_answered'] = False
    state['start_time'] = time.time()
    state['render']()
