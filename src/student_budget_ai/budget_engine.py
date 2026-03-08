
from __future__ import annotations

import math
from io import BytesIO
from typing import Dict, Any, Tuple

import pandas as pd

REQUIRED_COLUMNS = [
    "Club",
    "RequestedAmount",
    "PriorityLevel",
    "Members",
    "PreviousFunding",
    "EventCount",
    "StrategicFit",
    "Description",
]

RUS_TO_EN_COLUMNS = {
    "Клуб": "Club",
    "Название клуба": "Club",
    "Сумма запроса": "RequestedAmount",
    "Запрашиваемая сумма": "RequestedAmount",
    "Приоритет": "PriorityLevel",
    "Количество участников": "Members",
    "Участники": "Members",
    "Предыдущее финансирование": "PreviousFunding",
    "Количество мероприятий": "EventCount",
    "Мероприятия": "EventCount",
    "Стратегическое соответствие": "StrategicFit",
    "Описание": "Description",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        cleaned = str(col).strip()
        if cleaned in RUS_TO_EN_COLUMNS:
            renamed[col] = RUS_TO_EN_COLUMNS[cleaned]
        else:
            renamed[col] = cleaned
    return df.rename(columns=renamed)


def load_budget_dataframe(file_like: Any) -> pd.DataFrame:
    if isinstance(file_like, (str, bytes)):
        df = pd.read_excel(file_like)
    elif hasattr(file_like, "read"):
        content = file_like.read()
        if hasattr(file_like, "seek"):
            file_like.seek(0)
        df = pd.read_excel(BytesIO(content))
    else:
        df = pd.read_excel(file_like)

    df = normalize_columns(df)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            "В Excel не хватает обязательных столбцов: " + ", ".join(missing)
        )

    numeric_cols = [
        "RequestedAmount",
        "PriorityLevel",
        "Members",
        "PreviousFunding",
        "EventCount",
        "StrategicFit",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["Club"] = df["Club"].astype(str).str.strip()
    df["Description"] = df["Description"].astype(str).str.strip()

    return df


def score_budget_requests(df: pd.DataFrame, total_budget: float) -> pd.DataFrame:
    work = df.copy()

    max_requested = max(float(work["RequestedAmount"].max()), 1.0)
    max_members = max(float(work["Members"].max()), 1.0)
    max_events = max(float(work["EventCount"].max()), 1.0)
    max_prev = max(float(work["PreviousFunding"].max()), 1.0)

    work["req_norm"] = work["RequestedAmount"] / max_requested
    work["members_norm"] = work["Members"] / max_members
    work["events_norm"] = work["EventCount"] / max_events
    work["prev_norm"] = work["PreviousFunding"] / max_prev if max_prev else 0

    # Итоговый балл: чем выше, тем выше приоритет к финансированию.
    work["Score"] = (
        work["PriorityLevel"] * 0.30
        + work["StrategicFit"] * 0.30
        + work["members_norm"] * 5 * 0.15
        + work["events_norm"] * 5 * 0.15
        + (1 - work["prev_norm"]) * 5 * 0.10
    )

    score_sum = max(float(work["Score"].sum()), 1.0)
    work["BaseRecommendation"] = (work["Score"] / score_sum) * float(total_budget)
    work["RecommendedAmount"] = work[["BaseRecommendation", "RequestedAmount"]].min(axis=1)

    allocated = float(work["RecommendedAmount"].sum())

    # Дораспределяем остаток тем, кто ещё не добрал до requested amount.
    leftover = float(total_budget) - allocated
    if leftover > 0:
        candidates = work[work["RecommendedAmount"] < work["RequestedAmount"]].copy()
        if not candidates.empty:
            candidates["NeedLeft"] = candidates["RequestedAmount"] - candidates["RecommendedAmount"]
            need_sum = float(candidates["NeedLeft"].sum())
            if need_sum > 0:
                for idx in candidates.index:
                    share = float(candidates.loc[idx, "NeedLeft"]) / need_sum
                    add_value = min(
                        leftover * share,
                        float(work.loc[idx, "RequestedAmount"] - work.loc[idx, "RecommendedAmount"]),
                    )
                    work.loc[idx, "RecommendedAmount"] += add_value

    work["RecommendedAmount"] = work["RecommendedAmount"].round(0)

    work["DecisionType"] = work.apply(
        lambda row: (
            "Одобрить полностью"
            if row["RecommendedAmount"] >= row["RequestedAmount"]
            else "Частично одобрить"
            if row["RecommendedAmount"] > 0
            else "Отклонить"
        ),
        axis=1,
    )

    work["FundingGap"] = (work["RequestedAmount"] - work["RecommendedAmount"]).clip(lower=0).round(0)
    work = work.sort_values(["Score", "RequestedAmount"], ascending=[False, False]).reset_index(drop=True)

    return work


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    preferred_cols = [
        "Club",
        "RequestedAmount",
        "PriorityLevel",
        "Members",
        "PreviousFunding",
        "EventCount",
        "StrategicFit",
        "Score",
        "RecommendedAmount",
        "FundingGap",
        "DecisionType",
        "Description",
    ]
    export_cols = [col for col in preferred_cols if col in df.columns]
    safe_df = df[export_cols].copy()
    if "Score" in safe_df.columns:
        safe_df["Score"] = safe_df["Score"].round(2)
    return safe_df.to_markdown(index=False)


def build_summary(df: pd.DataFrame, scored_df: pd.DataFrame, total_budget: float) -> Dict[str, Any]:
    total_requested = float(df["RequestedAmount"].sum())
    approved_total = float(scored_df["RecommendedAmount"].sum())
    fully_approved = int((scored_df["DecisionType"] == "Одобрить полностью").sum())
    partial = int((scored_df["DecisionType"] == "Частично одобрить").sum())
    rejected = int((scored_df["DecisionType"] == "Отклонить").sum())
    over_request = total_requested - float(total_budget)

    return {
        "club_count": int(len(df)),
        "total_requested": round(total_requested, 2),
        "total_budget": round(float(total_budget), 2),
        "approved_total": round(approved_total, 2),
        "budget_gap_before_optimization": round(max(over_request, 0), 2),
        "fully_approved": fully_approved,
        "partial": partial,
        "rejected": rejected,
    }


def build_llm_inputs(
    df: pd.DataFrame,
    priorities_text: str,
    total_budget: float,
) -> Tuple[Dict[str, Any], pd.DataFrame, Dict[str, Any]]:
    scored_df = score_budget_requests(df, total_budget)
    summary = build_summary(df, scored_df, total_budget)

    inputs = {
        "total_budget": int(total_budget),
        "priorities_text": priorities_text.strip(),
        "requests_table": dataframe_to_markdown(df.assign(
            RequestedAmount=df["RequestedAmount"].round(0),
            PreviousFunding=df["PreviousFunding"].round(0),
        )),
        "scored_table": dataframe_to_markdown(scored_df),
        "club_count": summary["club_count"],
        "total_requested": summary["total_requested"],
        "approved_total": summary["approved_total"],
        "budget_gap_before_optimization": summary["budget_gap_before_optimization"],
        "fully_approved": summary["fully_approved"],
        "partial": summary["partial"],
        "rejected": summary["rejected"],
    }
    return inputs, scored_df, summary
