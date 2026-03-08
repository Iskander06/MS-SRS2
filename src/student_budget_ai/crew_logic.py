import os
from pathlib import Path
from dotenv import load_dotenv
from crewai import Agent, Crew, Task, Process, LLM

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)


def build_budget_crew(config, llm_inputs):
    agents_conf = config["agents"]
    tasks_conf = config["tasks"]

  

    model_name = os.getenv("MODEL", "gemini/gemini-2.5-flash")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    print("GOOGLE_API_KEY EXISTS:", bool(os.getenv("GOOGLE_API_KEY")))
    print("GEMINI_API_KEY EXISTS:", bool(os.getenv("GEMINI_API_KEY")))
    print("API KEY PASSED TO LLM:", bool(api_key))

    if not api_key:
        raise ValueError(
            "API key not found. Проверь файл .env и переменные GOOGLE_API_KEY / GEMINI_API_KEY."
        )

    llm = LLM(
        model=model_name,
        api_key=api_key,
        temperature=0.3
    )

    analyst = Agent(
        role=agents_conf["budget_analyst"]["role"],
        goal=agents_conf["budget_analyst"]["goal"],
        backstory=agents_conf["budget_analyst"]["backstory"],
        llm=llm,
        verbose=True,
    )

    coordinator = Agent(
        role=agents_conf["coordinator"]["role"],
        goal=agents_conf["coordinator"]["goal"],
        backstory=agents_conf["coordinator"]["backstory"],
        llm=llm,
        verbose=True,
    )

    analysis_task = Task(
        description=tasks_conf["analysis_task"]["description"].format(**llm_inputs),
        expected_output=tasks_conf["analysis_task"]["expected_output"],
        agent=analyst,
    )

    final_task = Task(
        description=tasks_conf["final_task"]["description"].format(**llm_inputs),
        expected_output=tasks_conf["final_task"]["expected_output"],
        agent=coordinator,
        context=[analysis_task],
    )

    crew = Crew(
        agents=[analyst, coordinator],
        tasks=[analysis_task, final_task],
        process=Process.sequential,
        verbose=True,
    )

    return crew.kickoff()