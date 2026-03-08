from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

from src.student_budget_ai.defaults import get_default_config
from src.student_budget_ai.budget_engine import load_budget_dataframe, build_llm_inputs
from src.student_budget_ai.crew_logic import build_budget_crew


def main() -> None:
    root = Path(__file__).resolve().parent
    excel_path = root / "data" / "sample_budget_requests.xlsx"
    priorities_path = root / "data" / "university_priorities.txt"
    reports_dir = root / "reports"
    reports_dir.mkdir(exist_ok=True)

    df = load_budget_dataframe(excel_path)
    priorities_text = priorities_path.read_text(encoding="utf-8")
    total_budget = 1800000

    llm_inputs, scored_df, summary = build_llm_inputs(df, priorities_text, total_budget)
    config = get_default_config()
    result = build_budget_crew(config, llm_inputs)

    output_path = reports_dir / "latest_budget_report.md"
    final_text = result.raw if hasattr(result, "raw") else str(result)
    output_path.write_text(final_text, encoding="utf-8")

    print("Готово.")
    print(f"Отчёт сохранён: {output_path}")
    print("Краткая сводка:")
    print(summary)


if __name__ == "__main__":
    main()