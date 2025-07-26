# 💰 ExpenX – Your Personal AI Expense Manager

**ExpenX** is a local-first AI-powered expense manager built using Python.  
It helps you **track**, **analyze**, and **optimize** your expenses — with smart insights, budgeting recommendations, and automatic categorization.

---

## 🚀 Features

- 🧾 **Manual Expense Entry** (with date, amount, purpose)
- 🧠 **AI Auto-Categorization** of expenses
- 📊 **Daily / Monthly Insights & Graphs**
- 🎯 **Budget Goals** & overspending alerts
- 🔁 **Recurring Expense Tracking**
- 🏦 **Bank/UPI Transaction Import** & Analysis
- 🧠 **LLM Support** for natural language queries *(optional)*
- 🧮 **Local-first Design** (runs on your machine)
- 🌐 **Simple Web Interface** using Flask *(in progress)*

---

## 🛠️ Setup Instructions

1. **Clone the Repo**
   ```bash
   git clone https://github.com/<your-username>/ExpenX.git 
   cd ExpenX

2. **Create a Virtual Environment**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # for Windows

3. **Install Dependencies**
    ```bash
    pip install -r requirements.txt

4. **Run the Tracker**
    ```bash
    python main.py

## 📁 Project Structure (Planned)
```bash

    ExpenX/
    │
    ├── app/                         # Core logic
    │   ├── __init__.py
    │   ├── tracker.py               # Add/view expenses
    │   ├── categorizer.py           # ML-based auto categorization
    │   ├── visualizer.py            # Charts, summaries
    │   ├── recurring.py             # Recurring expense tracker
    │   └── parser.py                # UPI/Bank statement parser
    │
    ├── web/                         # Flask or Streamlit frontend
    │   ├── app.py                   # Simple local web interface
    │   └── templates/               # HTML (if Flask)
    │
    ├── data/
    │   └── expenses.csv             # Your core DB (for now)
    │
    ├── models/                      # ML models, LLM memory, vector store etc.
    │   ├── categorization_model.pkl
    │   └── memory.json
    │
    ├── static/                      # For UI assets (optional)
    │
    ├── .env                         # API keys (OpenAI etc.)
    ├── .gitignore
    ├── README.md
    ├── requirements.txt
    ├── main.py                      # CLI launcher for testing
    └── config.py                    # Budget goals, constants
```

## 📈 Future Plans
 - Smart NLP queries using LLMs (OpenAI or Ollama)

 - OCR for scanning printed receipts

 - Personalized insights based on spending history

 - Export reports as PDF / Excel





## 🤖 Powered By
- Python 3.11

- Pandas & Matplotlib

- Flask (for UI)

- LangChain / OpenAI API (optional)

- Tesseract OCR (for receipts)