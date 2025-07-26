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
    ├── main.py                  # CLI runner (Phase 1)
    ├── expense_tracker.py       # Core logic
    ├── db/                      # SQLite or CSV storage
    ├── utils/                   # Helpers: categorization, analyzers, etc.
    ├── static/                  # For Flask UI (images, css, js)
    ├── templates/               # Flask HTML templates
    ├── uploads/                 # Bank statements, receipts
    ├── README.md
    └── requirements.txt
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