import streamlit as st
from app.tracker import add_expense, get_expenses, delete_expense_by_index
from datetime import date
import pandas as pd

st.set_page_config(page_title="ExpenX - Expense Tracker", layout="centered")
st.title("💸 ExpenX - Expense Tracker")

menu = ["Add Expense", "View Expenses", "Delete Expense"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Add Expense":
    st.subheader("➕ Add a New Expense")
    amount = st.number_input("Amount (₹)", min_value=0)
    description = st.text_input("Description")
    exp_date = st.date_input("Date", date.today())

    if st.button("Add Expense"):
        if amount > 0 and description.strip():
            add_expense(amount, description, str(exp_date))
            st.success("✅ Expense added successfully!")
        else:
            st.warning("⚠️ Please enter valid details.")

elif choice == "View Expenses":
    st.subheader("📋 Expense History")
    df = get_expenses()
    if df.empty:
        st.info("No expenses found.")
    else:
        # Convert Date column to datetime
        df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        df["RowIndex"] = df.index  # preserve row order
        
        # Sort: Newer dates first, then more recent rows
        df_sorted = df.sort_values(by=["Date", "RowIndex"], ascending=[False, False]).drop(columns=["RowIndex"])
        
        st.dataframe(df_sorted, use_container_width=True)
        st.write("💰 Total Spent:", f"₹{df_sorted['Amount'].sum():.2f}")

elif choice == "Delete Expense":
    st.subheader("🗑️ Delete an Expense")
    df = get_expenses()

    if df.empty:
        st.info("No expenses available to delete.")
    else:
        df_display = df.copy()
        df_display["Row"] = df_display.index

        row_to_delete = st.selectbox("Select expense to delete:", df_display.apply(
            lambda x: f"{x['Row']} - ₹{x['Amount']} | {x['Description']} on {x['Date']} [{x['Category']}]", axis=1))

        index = int(row_to_delete.split(" - ")[0])  # Extract index from display string

        if st.button("Delete Selected Expense"):
            delete_expense_by_index(index)
            st.success("✅ Expense deleted successfully.")
