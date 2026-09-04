# ui/stats_page.py
"""数据统计页：学习/掌握统计、正确率趋势图、遗忘曲线（Flet 原生图表）。

统计界面支持：侧边下拉框切换趋势周期（近7天/近30天），滚轮滚动 + 手机端滑动。
"""
import flet as ft

from config import get_current_book
from data import statistics as st
from ui.theme import glass, glass_button, page_shell, TEXT_COLOR, SUB_TEXT_COLOR


def build_stats_page(page: ft.Page) -> ft.Control:
    book = get_current_book()
    total = st.get_total_words_count(book)
    learned = st.get_learned_words_count(book)
    mastered = st.get_mastered_words_count(book)
    today_learn = st.get_today_study_count(book)
    today_review = st.get_today_reviewed_count(book)
    new_words = st.get_new_words_count(book)

    sp_total, sp_correct = st.get_spelling_stats(book)
    sp_text = f"{round(sp_correct / sp_total * 100, 1)}%" if sp_total else "暂无"

    back_btn = glass_button("返回首页", lambda _: page.go("/"))

    def _card(title, value, subtitle=""):
        return glass(
            ft.Column(
                [
                    ft.Text(title, size=13, color=SUB_TEXT_COLOR),
                    ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    ft.Text(subtitle, size=11, color=SUB_TEXT_COLOR) if subtitle else ft.Text("", size=11),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=14, radius=16,
        )

    cards = ft.Row(
        controls=[
            _card("总单词数", total),
            _card("已学习", learned),
            _card("已掌握", mastered, "连续答对≥3次"),
            _card("今日学习", today_learn),
            _card("今日复习", today_review),
            _card("待学新词", new_words),
            _card("拼写正确率", sp_text),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        wrap=True,
        spacing=12,
        run_spacing=12,
    )

    trend_label = ft.Text("近7天正确率趋势", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    trend_box = ft.Container(content=_build_accuracy_chart(book, 7), expand=True)

    def _on_period_change(e):
        days = int(e.control.value or 7)
        trend_label.value = f"近{days}天正确率趋势"
        trend_box.content = _build_accuracy_chart(book, days)
        page.update()

    period_dropdown = ft.Dropdown(
        label="趋势周期",
        width=130,
        options=[
            ft.dropdown.Option("7", "近7天"),
            ft.dropdown.Option("30", "近30天"),
        ],
        value="7",
        on_change=_on_period_change,
    )

    forgetting_chart = _build_forgetting_chart(book)

    return page_shell(
        page,
        ft.Container(
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row([back_btn], alignment=ft.MainAxisAlignment.START),
                    ft.Text("数据统计", size=22, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    cards,
                    ft.Row([trend_label, period_dropdown], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    trend_box,
                    ft.Text("遗忘曲线（间隔天数 → 记忆保持率）", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    forgetting_chart,
                ],
                alignment=ft.MainAxisAlignment.START,
                spacing=16,
            ),
            expand=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    )


def _build_accuracy_chart(book, days=7):
    data = st.get_accuracy_trend(days, book)
    points = [ft.LineChartDataPoint(i, acc) for i, (_, acc) in enumerate(data) if acc is not None]
    if not points:
        return ft.Container(
            content=ft.Text("暂无复习记录，无法绘制趋势图", color=ft.Colors.GREY),
            padding=20,
        )
    series = ft.LineChartData(
        data_points=points,
        stroke_width=3,
        color=ft.Colors.PURPLE,
        curved=True,
        stroke_cap_round=True,
    )
    return ft.LineChart(
        data_series=[series],
        min_y=0,
        max_y=100,
        min_x=0,
        max_x=max(days - 1, 1),
        height=240,
        expand=True,
        left_axis=ft.ChartAxis(labels_size=30, title=ft.Text("正确率%"), title_size=30),
        bottom_axis=ft.ChartAxis(
            labels_size=30,
            labels=[ft.ChartAxisLabel(value=i, label=ft.Text(d[5:])) for i, (d, _) in enumerate(data)],
        ),
        horizontal_grid_lines=ft.ChartGridLines(interval=25, color=ft.Colors.GREY_300, width=1),
        tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.PURPLE_100),
    )


def _build_forgetting_chart(book):
    data = st.get_forgetting_curve(book)
    if not data:
        return ft.Container(
            content=ft.Text("暂无复习记录，无法计算遗忘曲线", color=ft.Colors.GREY),
            padding=20,
        )
    points = [ft.LineChartDataPoint(g, keep) for g, keep in data]
    max_x = max((g for g, _ in data), default=1)
    series = ft.LineChartData(
        data_points=points,
        stroke_width=3,
        color=ft.Colors.PINK,
        curved=True,
        stroke_cap_round=True,
    )
    return ft.LineChart(
        data_series=[series],
        min_y=0,
        max_y=100,
        min_x=0,
        max_x=max_x,
        height=240,
        expand=True,
        left_axis=ft.ChartAxis(labels_size=30, title=ft.Text("保持率%"), title_size=30),
        bottom_axis=ft.ChartAxis(labels_size=30, title=ft.Text("间隔天数"), title_size=30),
        horizontal_grid_lines=ft.ChartGridLines(interval=25, color=ft.Colors.GREY_300, width=1),
        tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.PINK_100),
    )
