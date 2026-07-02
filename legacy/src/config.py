import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-4o-mini"

# Pricing (USD per 1M tokens) - GPT-4o-mini
PRICE_PER_1M_INPUT_TOKENS = 0.15
PRICE_PER_1M_OUTPUT_TOKENS = 0.60

# File Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
SYSTEM_PROMPT_PATH = os.path.join(DOCS_DIR, "system_prompt.md")
PHILO_CSV_PATH = os.path.join(DOCS_DIR, "philo.csv")
QUESTION_LIST_PATH = os.path.join(DOCS_DIR, "question_list.json")

# UI Configuration
PAGE_TITLE = "PhiloScope"
PAGE_ICON = "🧭"
LAYOUT = "centered"
