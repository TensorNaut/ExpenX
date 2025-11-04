# app.py (Streamlit front-end) — auto-load model at startup
import streamlit as st
from app.tracker import (
    add_expense,
    get_expenses,
    delete_expense_by_id,
    get_expense_by_id,
    update_expense,
    get_category_options,
    predict_category,
    load_model
)
from datetime import date as dt_date
import pandas as pd

st.set_page_config(page_title="ExpenX - Expense Tracker", layout="centered")
st.title("💸 ExpenX - Expense Tracker")

# Auto-load the model once when Streamlit app starts.
# Use session_state to avoid re-loading on every rerun.
if 'model_loaded' not in st.session_state:
    st.session_state['model_loaded'] = False

if not st.session_state['model_loaded']:
    # Show a spinner in the sidebar while loading to avoid blocking main UI view
    with st.spinner("Warming up local model and classifier (this happens once)..."):
        ok = load_model()
        st.session_state['model_loaded'] = bool(ok)
    if st.session_state['model_loaded']:
        st.sidebar.success("Model loaded ✅")
    else:
        st.sidebar.warning("Model not loaded (missing files or load error). Predictions will be disabled.")

menu = ["Add Expense", "View Expenses", "Edit Expense", "Delete Expense"]
choice = st.sidebar.selectbox("Menu", menu)

# Helper to build dropdown options given a predicted label
def build_dropdown_options(base_options, predicted):
    dropdown_options = []
    if predicted:
        dropdown_options.append(predicted)
    for opt in base_options:
        if opt != predicted and opt not in dropdown_options:
            dropdown_options.append(opt)
    if "Other" not in dropdown_options:
        dropdown_options.append("Other")
    return dropdown_options

if choice == "Add Expense":
    st.subheader("➕ Add a New Expense")

    amount = st.number_input("Amount (₹)", min_value=0)
    description = st.text_input("Description")
    exp_date = st.date_input("Date", dt_date.today())

    # base category options (classifier classes / DB / defaults)
    base_options = get_category_options()

    predicted = None
    if description and description.strip():
        with st.spinner("Predicting category..."):
            try:
                predicted = predict_category(description)
            except Exception:
                predicted = None

    # Build dropdown with predicted first
    dropdown_options = []
    if predicted:
        dropdown_options.append(predicted)
    for opt in base_options:
        if opt != predicted and opt not in dropdown_options:
            dropdown_options.append(opt)
    if "Other" not in dropdown_options:
        dropdown_options.append("Other")

    category_selected = st.selectbox("Category (change if you want)",
                                     options=dropdown_options,
                                     index=0)

    custom_cat = None
    if category_selected == "Other":
        custom_cat = st.text_input("Enter custom category", value="").strip()
        if not custom_cat:
            st.info("You chose 'Other' — please type a custom category.")

    if predicted:
        st.caption(f"Model suggestion: **{predicted}** (updates as you type)")

    if st.button("Add Expense"):
        if amount > 0 and description.strip():
            try:
                if category_selected == "Other":
                    final_category = custom_cat if custom_cat else "Uncategorized"
                    pass_category = final_category
                    use_model_flag = False
                else:
                    # if user left dropdown on the predicted value, let server predict (pass None)
                    if predicted and category_selected == predicted:
                        pass_category = None
                        use_model_flag = True
                    else:
                        pass_category = category_selected
                        use_model_flag = False

                eid = add_expense(amount=amount,
                                  description=description,
                                  date=exp_date,
                                  category=pass_category,
                                  use_model_when_none=use_model_flag)
                st.success(f"✅ Expense added successfully! (id: {eid})")

                # optional refresh — but no session state mutation
                st.rerun()

            except Exception as ex:
                st.error(f"Failed to add expense: {ex}")
        else:
            st.warning("⚠️ Please enter valid details.")


elif choice == "View Expenses":
    st.subheader("📋 Expense History")
    df = get_expenses()
    if df.empty:
        st.info("No expenses found.")
    else:
        df_display = df.copy()
        df_display['Date'] = pd.to_datetime(df_display['Date'], errors='coerce').dt.date
        df_display['RowIndex'] = df_display.index
        df_sorted = df_display.sort_values(by=["Date", "id"], ascending=[False, False]).drop(columns=['RowIndex'], errors='ignore')

        st.dataframe(df_sorted.reset_index(drop=True), use_container_width=True)
        st.write("💰 Total Spent:", f"₹{df_sorted['Amount'].sum():.2f}")

elif choice == "Edit Expense":
    st.subheader("✏️ Edit an Expense")
    df = get_expenses(limit=2000)
    if df.empty:
        st.info("No expenses available to edit.")
    else:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df['display'] = df.apply(lambda x: f"{int(x['id'])} - ₹{x['Amount']} | {x['Description']} on {x['Date']} [{x['Category']}]", axis=1)
        selection = st.selectbox("Choose expense to edit:", df['display'].tolist(), key="edit_select")
        if selection:
            eid = int(selection.split(" - ")[0])
            record = get_expense_by_id(eid)
            if record:
                # Pre-fill fields into session state so changing description triggers prediction
                default_desc_key = f"edit_desc_{eid}"
                default_custom_key = f"edit_custom_{eid}"
                if default_desc_key not in st.session_state:
                    st.session_state[default_desc_key] = record['Description'] or ""
                edit_description = st.text_input("Description", value=st.session_state[default_desc_key], key=default_desc_key)
                edit_amount = st.number_input("Amount (₹)", value=float(record['Amount']), format="%.2f", key=f"edit_amount_{eid}")
                edit_date = st.date_input("Date", value=pd.to_datetime(record['Date']).date() if record['Date'] else dt_date.today(), key=f"edit_date_{eid}")

                # Predict-as-you-type for edit description
                predicted_edit = None
                if edit_description and edit_description.strip():
                    with st.spinner("Predicting category..."):
                        try:
                            predicted_edit = predict_category(edit_description)
                        except Exception:
                            predicted_edit = None

                # Build edit category dropdown: predicted first, current category next, then others, then Other
                base_options = get_category_options()
                cur_cat = record.get('Category') or ''
                edit_options = []
                if predicted_edit:
                    edit_options.append(predicted_edit)
                if cur_cat and cur_cat not in edit_options:
                    edit_options.append(cur_cat)
                for opt in base_options:
                    if opt not in edit_options:
                        edit_options.append(opt)
                if "Other" not in edit_options:
                    edit_options.append("Other")

                # Determine default idx: 0 (predicted first), but if predicted is None, put current category first
                default_idx = 0
                if not predicted_edit:
                    # prefer current category to appear first
                    if cur_cat in edit_options:
                        default_idx = edit_options.index(cur_cat)
                edit_category_selected = st.selectbox("Category", options=edit_options, index=default_idx, key=f"edit_cat_{eid}")

                edit_custom_cat = None
                if edit_category_selected == "Other":
                    if default_custom_key not in st.session_state:
                        st.session_state[default_custom_key] = ""
                    edit_custom_cat = st.text_input("Enter custom category", value=st.session_state[default_custom_key], key=default_custom_key).strip()
                    if edit_custom_cat == "":
                        st.info("You chose 'Other' — please type a custom category.")

                # show model suggestion note
                if predicted_edit:
                    st.caption(f"Model suggestion (updates as you type): **{predicted_edit}**")

                if st.button("Save Changes", key=f"save_edit_{eid}"):
                    try:
                        if edit_category_selected == "Other":
                            final_edit_category = edit_custom_cat if edit_custom_cat else "Uncategorized"
                        else:
                            # If user left dropdown at predicted_edit, let server predict by passing None
                            if predicted_edit and edit_category_selected == predicted_edit:
                                pass_category = None
                                use_model_flag = True
                            else:
                                pass_category = edit_category_selected
                                use_model_flag = False
                            final_edit_category = pass_category

                        ok = update_expense(eid,
                                            date=edit_date,
                                            amount=edit_amount,
                                            description=edit_description,
                                            category=final_edit_category)
                        if ok:
                            st.success("✅ Expense updated successfully.")
                            # update session_state desc to the saved value to persist UI
                            st.session_state[default_desc_key] = edit_description
                        else:
                            st.warning("⚠️ Expense not found or update failed.")
                    except Exception as ex:
                        st.error(f"Failed to update: {ex}")

elif choice == "Delete Expense":
    st.subheader("🗑️ Delete an Expense")
    df = get_expenses()
    if df.empty:
        st.info("No expenses available to delete.")
    else:
        df_display = df.copy()
        df_display["Date"] = pd.to_datetime(df_display["Date"], errors='coerce').dt.date
        df_display["display"] = df_display.apply(lambda x: f"{int(x['id'])} - ₹{x['Amount']} | {x['Description']} on {x['Date']} [{x['Category']}]", axis=1)

        selection = st.selectbox("Select expense to delete:", df_display['display'].tolist(), key="delete_select")
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
