from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv(dotenv_path=ROOT / ".env", override=True)

from student_budget_ai.defaults import get_default_config
from student_budget_ai.budget_engine import load_budget_dataframe, build_llm_inputs
from student_budget_ai.crew_logic import build_budget_crew

# Безопасно читаем Streamlit secrets, если они есть
try:
    secrets_dict = dict(st.secrets)
except Exception:
    secrets_dict = {}

if secrets_dict.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = secrets_dict["GOOGLE_API_KEY"]

if secrets_dict.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = secrets_dict["GEMINI_API_KEY"]

if secrets_dict.get("MODEL"):
    os.environ["MODEL"] = secrets_dict["MODEL"]

st.set_page_config(
    page_title="Распределение бюджета студенческого самоуправления",
    layout="wide",
)

st.title("Распределение бюджета студенческого самоуправления")
st.caption("Тема 7 — CrewAI + Streamlit")

default_config = get_default_config()

st.subheader("1. Зона редактирования конфигурации")

with st.expander("Настройка агентов и задач", expanded=True):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Агент 1 — Бюджетный аналитик")
        analyst_role = st.text_input(
            "Role аналитика",
            value=default_config["agents"]["budget_analyst"]["role"],
        )
        analyst_goal = st.text_area(
            "Goal аналитика",
            value=default_config["agents"]["budget_analyst"]["goal"],
            height=100,
        )
        analyst_backstory = st.text_area(
            "Backstory аналитика",
            value=default_config["agents"]["budget_analyst"]["backstory"],
            height=140,
        )
        analysis_task_desc = st.text_area(
            "Описание задачи аналитика",
            value=default_config["tasks"]["analysis_task"]["description"],
            height=100,
        )
        analysis_expected = st.text_area(
            "Ожидаемый вывод аналитика",
            value=default_config["tasks"]["analysis_task"]["expected_output"],
            height=100,
        )

    with col2:
        st.markdown("### Агент 2 — Координатор")
        coordinator_role = st.text_input(
            "Role координатора",
            value=default_config["agents"]["coordinator"]["role"],
        )
        coordinator_goal = st.text_area(
            "Goal координатора",
            value=default_config["agents"]["coordinator"]["goal"],
            height=100,
        )
        coordinator_backstory = st.text_area(
            "Backstory координатора",
            value=default_config["agents"]["coordinator"]["backstory"],
            height=140,
        )
        final_task_desc = st.text_area(
            "Описание финальной задачи",
            value=default_config["tasks"]["final_task"]["description"],
            height=100,
        )
        final_expected = st.text_area(
            "Ожидаемый финальный вывод",
            value=default_config["tasks"]["final_task"]["expected_output"],
            height=100,
        )

app_config = {
    "agents": {
        "budget_analyst": {
            "role": analyst_role,
            "goal": analyst_goal,
            "backstory": analyst_backstory,
        },
        "coordinator": {
            "role": coordinator_role,
            "goal": coordinator_goal,
            "backstory": coordinator_backstory,
        },
    },
    "tasks": {
        "analysis_task": {
            "description": analysis_task_desc,
            "expected_output": analysis_expected,
        },
        "final_task": {
            "description": final_task_desc,
            "expected_output": final_expected,
        },
    },
}

st.subheader("2. Зона ввода переменных данных")

left, right = st.columns([1.1, 1])

with left:
    uploaded_excel = st.file_uploader(
        "Загрузите Excel с заявками клубов",
        type=["xlsx", "xls"],
    )
    total_budget = st.number_input(
        "Общий бюджет на распределение",
        min_value=10000,
        step=10000,
        value=1800000,
    )

with right:
    sample_priorities = (ROOT / "data" / "university_priorities.txt").read_text(encoding="utf-8")
    priorities_text = st.text_area(
        "Приоритеты развития вуза на текущий год",
        value=sample_priorities,
        height=220,
    )

st.info(
    "Ожидаемые столбцы Excel: Club, RequestedAmount, PriorityLevel, Members, "
    "PreviousFunding, EventCount, StrategicFit, Description. "
    "Также поддерживаются некоторые русские названия столбцов."
)

if uploaded_excel is None:
    st.warning("Excel не загружен. Пока показываю демо-файл из папки data.")
    excel_source = ROOT / "data" / "sample_budget_requests.xlsx"
else:
    excel_source = uploaded_excel

try:
    df = load_budget_dataframe(excel_source)
    st.markdown("### Предпросмотр таблицы")
    st.dataframe(df, use_container_width=True)
except Exception as exc:
    st.error(f"Не удалось прочитать Excel: {exc}")
    st.stop()

llm_inputs, scored_df, summary = build_llm_inputs(df, priorities_text, float(total_budget))

st.markdown("### Предварительная машинная оценка")
metric_cols = st.columns(4)
metric_cols[0].metric("Клубов", summary["club_count"])
metric_cols[1].metric("Запрошено", f'{summary["total_requested"]:,.0f}')
metric_cols[2].metric("Бюджет", f'{summary["total_budget"]:,.0f}')
metric_cols[3].metric("Предв. утверждено", f'{summary["approved_total"]:,.0f}')
st.dataframe(scored_df, use_container_width=True)

st.subheader("3. Зона запуска и визуализации")

run_clicked = st.button("Запустить CrewAI", type="primary", use_container_width=True)

if run_clicked:
    api_key_exists = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    if not api_key_exists:
        st.error("Не найден GOOGLE_API_KEY или GEMINI_API_KEY. Добавьте ключ в .env или в secrets Streamlit.")
        st.stop()

    with st.spinner("Агенты анализируют заявки и готовят итоговый отчёт..."):
        try:
            result = build_budget_crew(app_config, llm_inputs)
            final_text = result.raw if hasattr(result, "raw") else str(result)

            analysis_text = ""
            if hasattr(result, "tasks_output") and result.tasks_output:
                if len(result.tasks_output) > 0:
                    analysis_text = getattr(result.tasks_output[0], "raw", "") or str(result.tasks_output[0])
        except Exception as exc:
            st.exception(exc)
            st.stop()

    st.success("Готово. Экипаж завершил работу.")

    tab1, tab2 = st.tabs(["Финальный отчёт", "Промежуточный анализ"])
    with tab1:
        st.markdown(final_text)
        st.download_button(
            "Скачать итоговый отчёт (.md)",
            data=final_text.encode("utf-8"),
            file_name="budget_report.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with tab2:
        st.markdown(analysis_text or "_Промежуточный вывод пустой._")