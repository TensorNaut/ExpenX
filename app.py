# app.py (Streamlit front-end)
import streamlit as st
from app.tracker import add_expense, get_expenses, delete_expense_by_id
from datetime import date as dt_date
import pandas as pd

st.set_page_config(page_title="ExpenX - Expense Tracker", layout="centered")
st.title("💸 ExpenX - Expense Tracker")

menu = ["Add Expense", "View Expenses", "Delete Expense"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Add Expense":
    st.subheader("➕ Add a New Expense")
    amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
    description = st.text_input("Description")
    exp_date = st.date_input("Date", dt_date.today())
    use_model = st.checkbox("Auto-categorize using local model", value=True)

    if st.button("Add Expense"):
        if amount > 0 and description.strip():
            try:
                eid = add_expense(amount=amount, description=description, date=exp_date, use_model=use_model)
                st.success(f"✅ Expense added successfully! (id: {eid})")
            except Exception as ex:
                st.error(f"Failed to add expense: {ex}")
        else:
            st.warning("⚠️ Please enter valid details.")

elif choice == "View Expenses":
    st.subheader("📋 Expense History")
    df = get_expenses(limit=2000)
    if df.empty:
        st.info("No expenses found.")
    else:
        # Format df for display
        df_display = df.copy()
        # Rename Date to Date (already) and ensure datetime formatting
        df_display['Date'] = pd.to_datetime(df_display['Date'], errors='coerce').dt.date
        df_display['RowIndex'] = df_display.index  # preserve row order if needed

        # Sort: Newer dates first, then id
        df_sorted = df_display.sort_values(by=["Date", "id"], ascending=[False, False]).drop(columns=['RowIndex'], errors='ignore')

        st.dataframe(df_sorted.reset_index(drop=True), use_container_width=True)
        st.write("💰 Total Spent:", f"₹{df_sorted['Amount'].sum():.2f}")

elif choice == "Delete Expense":
    st.subheader("🗑️ Delete an Expense")
    df = get_expenses(limit=5000)
    if df.empty:
        st.info("No expenses available to delete.")
    else:
        # Build display strings with id
        df_display = df.copy()
        df_display['Date'] = pd.to_datetime(df_display['Date'], errors='coerce').dt.date
        df_display['display'] = df_display.apply(lambda x: f"{int(x['id'])} - ₹{x['Amount']} | {x['Description']} on {x['Date']} [{x['Category']}]", axis=1)

        selection = st.selectbox("Select expense to delete:", df_display['display'].tolist())
        if selection:
            eid = int(selection.split(" - ")[0])
            if st.button("Delete Selected Expense"):
                try:
                    ok = delete_expense_by_id(eid)
                    if ok:
                        st.success("✅ Expense deleted successfully.")
                    else:
                        st.warning("⚠️ Could not find the selected expense.")
                except Exception as ex:
                    st.error(f"Failed to delete expense: {ex}")
