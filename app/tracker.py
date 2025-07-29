import pandas as pd
from datetime import datetime
import os
from sentence_transformers import SentenceTransformer
import pickle

EXPENSES_FILE = 'data/expenses.csv'

# Ensure the file exists
def initialize_expense_file():
    if not os.path.exists(EXPENSES_FILE):
        df = pd.DataFrame(columns=['Date', 'Amount', 'Description', 'Category'])
        df.to_csv(EXPENSES_FILE, index=False)

#--------------------------------------------------------------------------

def get_expenses():
    initialize_expense_file()
    if not os.path.exists(EXPENSES_FILE):
        return pd.DataFrame(columns=['Date', 'Amount', 'Description', 'Category'])
    return pd.read_csv(EXPENSES_FILE)

def delete_expense_by_index(index):
    df = get_expenses()
    df.drop(index, inplace=True)
    df.to_csv(EXPENSES_FILE, index=False)

#--------------------------------------------------------------------------    

# Add a new expense
def add_expense(amount: float, description: str, date=None, category='Uncategorized'):
    initialize_expense_file()
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')

    # Load local BERT model
    model = SentenceTransformer('D:/PROJECTS/Version Control/ExpenX/models/new_bert_model')

    # Load classifier
    with open('D:/PROJECTS/Version Control/ExpenX/models/new_bert_classifier.pkl', 'rb') as f:
        clf = pickle.load(f)

    # Predict category
    category_embedding = model.encode([description])
    category = clf.predict(category_embedding)[0]

    new_expense = pd.DataFrame([{
        'Date': date,
        'Amount': amount,
        'Description': description,
        'Category': category
    }])
    
    df = pd.read_csv(EXPENSES_FILE)
    df = pd.concat([df, new_expense], ignore_index=True)
    df.to_csv(EXPENSES_FILE, index=False)

    print(f"Expense added: ₹{amount} for '{description}' on {date}, catgory: {category}")
