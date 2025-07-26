import pandas as pd
from datetime import datetime
import os

EXPENSES_FILE = 'data/expenses.csv'

# Ensure the file exists
def initialize_expense_file():
    if not os.path.exists(EXPENSES_FILE):
        df = pd.DataFrame(columns=['Date', 'Amount', 'Description', 'Category'])
        df.to_csv(EXPENSES_FILE, index=False)

# Add a new expense
def add_expense(amount: float, description: str, date=None, category='Uncategorized'):
    initialize_expense_file()
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')

    new_expense = pd.DataFrame([{
        'Date': date,
        'Amount': amount,
        'Description': description,
        'Category': category
    }])
    
    df = pd.read_csv(EXPENSES_FILE)
    df = pd.concat([df, new_expense], ignore_index=True)
    df.to_csv(EXPENSES_FILE, index=False)

    print(f"✅ Expense added: ₹{amount} for '{description}' on {date}")
