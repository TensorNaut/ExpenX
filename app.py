# app.py (Streamlit front-end - full file)
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
from app.finance import get_accounts, create_account
from datetime import date as dt_date
import pandas as pd

st.set_page_config(page_title="ExpenX - Expense Tracker", layout="centered")
st.title("💸 ExpenX - Expense Tracker")

# Auto-load model at startup (once)
if 'model_loaded' not in st.session_state:
    st.session_state['model_loaded'] = False

if not st.session_state['model_loaded']:
    with st.spinner("Warming up local model and classifier (this happens once)..."):
        ok = load_model()
        st.session_state['model_loaded'] = bool(ok)
    if st.session_state['model_loaded']:
        st.sidebar.success("Model loaded ✅")
    else:
        st.sidebar.warning("Model not loaded. Predictions disabled.")

# ensure default Main account exists
accounts_now = get_accounts()
if not any(a['name'] == 'Main' for a in accounts_now):
    try:
        create_account('Main', initial_balance=0.0)
        st.sidebar.info("Created default account 'Main'.")
    except Exception:
        pass

menu = ["Add Expense", "View Expenses", "Edit Expense", "Delete Expense", "Accounts", "Income", "Ledger", "Investments"]
choice = st.sidebar.selectbox("Menu", menu)

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
    amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
    description = st.text_input("Description", key="add_description")
    exp_date = st.date_input("Date", dt_date.today())

    # category options & predict-as-you-type
    base_options = get_category_options()
    predicted = None
    if description and description.strip():
        with st.spinner("Predicting category..."):
            predicted = predict_category(description)

    # Payment source dropdown: accounts + 'Cash' + 'Credit Card'
    accounts = get_accounts()
    acct_names = [a['name'] for a in accounts]
    payment_options = acct_names + ['Cash', 'Credit Card']
    default_idx = payment_options.index('Main') if 'Main' in payment_options else 0
    payment_selected = st.selectbox("Payment Source", options=payment_options, index=default_idx)

    # category dropdown (predicted first)
    dropdown_options = build_dropdown_options(base_options, predicted)
    category_selected = st.selectbox("Category (change if you want)", options=dropdown_options, index=0)

    custom_cat = None
    if category_selected == "Other":
        custom_cat = st.text_input("Enter custom category", value="", key="add_custom_category").strip()
        if custom_cat == "":
            st.info("You chose 'Other' — please type a custom category.")

    if st.button("Add Expense"):
        if amount > 0 and description.strip():
            try:
                # determine pass_category behavior: if user left predicted as-is, let server predict by passing None
                if category_selected == "Other":
                    final_category = custom_cat if custom_cat else "Uncategorized"
                    pass_category = final_category
                    use_model_flag = False
                else:
                    if predicted and category_selected == predicted:
                        pass_category = None
                        use_model_flag = True
                    else:
                        pass_category = category_selected
                        use_model_flag = False

                # map payment source to account_id if it's an account
                selected_account_id = None
                if payment_selected not in ('Cash', 'Credit Card'):
                    acct_map = {a['name']: a['id'] for a in accounts}
                    selected_account_id = acct_map.get(payment_selected)

                eid = add_expense(amount=amount,
                                  description=description,
                                  date=exp_date,
                                  category=pass_category,
                                  payment_source=payment_selected,
                                  account_id=selected_account_id,
                                  use_model_when_none=use_model_flag)
                st.success(f"✅ Expense added successfully! (id: {eid})")
                # clear inputs
                st.session_state['add_description'] = ""
                if 'add_custom_category' in st.session_state:
                    st.session_state['add_custom_category'] = ""
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
                default_desc_key = f"edit_desc_{eid}"
                default_custom_key = f"edit_custom_{eid}"
                if default_desc_key not in st.session_state:
                    st.session_state[default_desc_key] = record['Description'] or ""
                edit_description = st.text_input("Description", value=st.session_state[default_desc_key], key=default_desc_key)
                edit_amount = st.number_input("Amount (₹)", value=float(record['Amount']), format="%.2f", key=f"edit_amount_{eid}")
                edit_date = st.date_input("Date", value=pd.to_datetime(record['Date']).date() if record['Date'] else dt_date.today(), key=f"edit_date_{eid}")

                # predict-as-you-type
                predicted_edit = None
                if edit_description and edit_description.strip():
                    with st.spinner("Predicting category..."):
                        predicted_edit = predict_category(edit_description)

                # Payment source edit: include current payment_source first, then others
                accounts = get_accounts()
                acct_names = [a['name'] for a in accounts]
                edit_payment_options = []
                cur_ps = record.get('PaymentSource') or record.get('payment_source') or 'Main'
                if cur_ps:
                    edit_payment_options.append(cur_ps)
                for name in acct_names:
                    if name not in edit_payment_options:
                        edit_payment_options.append(name)
                for extra in ('Cash','Credit Card'):
                    if extra not in edit_payment_options:
                        edit_payment_options.append(extra)
                default_idx = 0
                edit_payment_selected = st.selectbox("Payment Source", options=edit_payment_options, index=default_idx, key=f"edit_payment_{eid}")

                # category dropdown
                base_options = get_category_options()
                edit_options = []
                if predicted_edit:
                    edit_options.append(predicted_edit)
                cur_cat = record.get('Category') or ''
                if cur_cat and cur_cat not in edit_options:
                    edit_options.append(cur_cat)
                for opt in base_options:
                    if opt not in edit_options:
                        edit_options.append(opt)
                if "Other" not in edit_options:
                    edit_options.append("Other")

                default_idx_cat = 0
                if not predicted_edit and cur_cat in edit_options:
                    default_idx_cat = edit_options.index(cur_cat)
                edit_category_selected = st.selectbox("Category", options=edit_options, index=default_idx_cat, key=f"edit_cat_{eid}")

                edit_custom_cat = None
                if edit_category_selected == "Other":
                    if default_custom_key not in st.session_state:
                        st.session_state[default_custom_key] = ""
                    edit_custom_cat = st.text_input("Enter custom category", value=st.session_state[default_custom_key], key=default_custom_key).strip()
                    if edit_custom_cat == "":
                        st.info("You chose 'Other' — please type a custom category.")

                if predicted_edit:
                    st.caption(f"Model suggestion (updates as you type): **{predicted_edit}**")

                if st.button("Save Changes", key=f"save_edit_{eid}"):
                    try:
                        if edit_category_selected == "Other":
                            final_edit_category = edit_custom_cat if edit_custom_cat else "Uncategorized"
                            pass_cat = final_edit_category
                            use_model_flag = False
                        else:
                            if predicted_edit and edit_category_selected == predicted_edit:
                                pass_cat = None
                                use_model_flag = True
                            else:
                                pass_cat = edit_category_selected
                                use_model_flag = False

                        # map edit payment source to account_id
                        selected_account_id = None
                        if edit_payment_selected not in ('Cash', 'Credit Card'):
                            acct_map = {a['name']: a['id'] for a in accounts}
                            selected_account_id = acct_map.get(edit_payment_selected)

                        ok = update_expense(eid,
                                            date=edit_date,
                                            amount=edit_amount,
                                            description=edit_description,
                                            category=pass_cat,
                                            payment_source=edit_payment_selected,
                                            account_id=selected_account_id)
                        if ok:
                            st.success("✅ Expense updated successfully.")
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


elif choice == "Accounts":
    st.subheader("🏦 Accounts & Balances")
    from app.finance import get_accounts, create_account, get_account_by_id
    accounts = get_accounts()
    if not accounts:
        st.info("No accounts yet. Create one.")
    else:
        for a in accounts:
            st.metric(label=f"{a['name']}", value=f"₹{a['balance']:.2f}")
    with st.expander("Create new account"):
        name = st.text_input("Account name", key="new_acct_name")
        init_bal = st.number_input("Initial balance", value=0.0, format="%.2f", key="new_acct_bal")
        if st.button("Create account"):
            try:
                aid = create_account(name.strip() or "Account", initial_balance=init_bal)
                st.success(f"Created account id {aid}")
            except Exception as ex:
                st.error(f"Failed to create account: {ex}")


elif choice == "Income":
    st.subheader("➕ Add Income / Credit")
    from app.finance import get_accounts, add_income
    accounts = get_accounts()
    acct_map = {a['name']: a['id'] for a in accounts}
    acct_names = list(acct_map.keys())
    if not acct_names:
        st.warning("No accounts exist — create one first under Accounts tab.")
    else:
        acct_sel = st.selectbox("Account", acct_names)
        amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
        date_val = st.date_input("Date", dt_date.today())
        sources = ["Salary", "Freelance", "Gift", "Interest", "Other"]
        src = st.selectbox("Source", sources)
        if src == "Other":
            src = st.text_input("Enter source")
        desc = st.text_input("Description (optional)")
        if st.button("Add Income"):
            try:
                aid = add_income(account_id=acct_map[acct_sel], amount=amount, source=src or "Other", date_val=date_val, description=desc)
                st.success(f"Income added (id {aid}). Balance updated.")
            except Exception as ex:
                st.error(f"Failed to add income: {ex}")


elif choice == "Ledger":
    st.subheader("📒 Ledger (lend/borrow)")
    from app.finance import get_accounts, add_ledger_entry, get_ledger
    accounts = get_accounts()
    acct_names = [a['name'] for a in accounts]
    acct_map = {a['name']: a['id'] for a in accounts}
    acct_selected = st.selectbox("Account (optional - affects balance if selected)", ["<none>"] + acct_names)
    amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
    direction = st.selectbox("Direction", ["lent", "borrowed"])  # lent = you gave money to someone
    party = st.text_input("Person / Party")
    due_date = st.date_input("Due date (optional)", value=None)
    purpose = st.text_input("Purpose")
    contact = st.text_input("Contact")
    notes = st.text_area("Notes")
    affects = st.checkbox("Affects account balance?", value=False)
    if st.button("Add Ledger Entry"):
        try:
            aid = acct_map.get(acct_selected) if acct_selected and acct_selected != "<none>" else None
            lid = add_ledger_entry(account_id=aid, amount=amount, direction=direction, party=party, due_date=due_date if due_date else None, purpose=purpose, contact=contact, notes=notes, affects_balance=affects)
            st.success(f"Ledger entry added (id {lid}).")
        except Exception as ex:
            st.error(f"Failed to add ledger entry: {ex}")
    # show recent ledger
    rows = get_ledger(limit=100)
    if rows:
        st.table(rows)


elif choice == "Investments":
    st.subheader("📈 Investments")
    from app.finance import get_accounts
    from app.investments import create_investment, list_investments, redeem_investment

    # Create investment form
    with st.expander("➕ Add new investment"):
        accounts = get_accounts()
        acct_map = {a['name']: a['id'] for a in accounts}
        acct_names = list(acct_map.keys())
        invest_amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="inv_amount")
        inv_date = st.date_input("Date", dt_date.today(), key="inv_date")
        inv_type = st.selectbox("Type", ["FD","Mutual Fund","Stock","Bond","Crypto","Gold","SIP","Other"], key="inv_type")
        if inv_type == "Other":
            inv_type = st.text_input("Specify type", key="inv_type_other")
        risk = st.selectbox("Risk", ["Low","Medium","High","Unknown"], index=3, key="inv_risk")
        mature_months = st.number_input("Mature period (months, optional)", min_value=0, value=0, key="inv_months")
        expected_return = st.number_input("Expected annual return (%) (optional)", min_value=0.0, format="%.2f", key="inv_return")
        description = st.text_input("Description (optional)", key="inv_desc")
        notes = st.text_area("Notes (optional)", key="inv_notes")

        # Funding source: choose account or other
        funding_opts = ["Other source (cash / external)"]
        funding_opts += acct_names
        funding_sel = st.selectbox("Funding source", funding_opts, key="inv_funding")
        debit_account = False
        account_id = None
        if funding_sel != "Other source (cash / external)":
            account_id = acct_map[funding_sel]
            debit_account = st.checkbox("Debit selected account for investment amount?", value=True, key="inv_debit")
        else:
            debit_account = False

        if st.button("Create Investment"):
            try:
                maturity_date = None
                if mature_months and mature_months > 0:
                    maturity_date = (dt_date.today() + pd.DateOffset(months=int(mature_months))).date()
                aid = account_id if account_id else None
                inv_id = create_investment(amount=invest_amount,
                                           inv_type=inv_type,
                                           date_val=inv_date,
                                           account_id=aid,
                                           description=description,
                                           risk=risk,
                                           mature_period_months=int(mature_months) if mature_months>0 else None,
                                           expected_return_percent=expected_return if expected_return>0 else None,
                                           debit_account=debit_account,
                                           maturity_date=maturity_date,
                                           notes=notes)
                st.success(f"Investment created (id {inv_id}).")
            except Exception as ex:
                st.error(f"Failed to create investment: {ex}")

    # List current investments
    st.markdown("### Active investments")
    investments = list_investments(status='active')
    if not investments:
        st.info("No active investments.")
    else:
        df_inv = pd.DataFrame(investments)
        st.dataframe(df_inv, use_container_width=True)

    # Redeem section
    st.markdown("### Redeem / mark as matured")
    inv_rows = list_investments(status='active')
    if inv_rows:
        inv_map = {f"{r['id']} - {r['type']} | ₹{r['amount']} on {r['date']}": r['id'] for r in inv_rows}
        sel = st.selectbox("Select investment to redeem", list(inv_map.keys()))
        redeem_amt = st.number_input("Redeem amount (leave 0 to redeem full)", min_value=0.0, format="%.2f", key="redeem_amt")
        # choose credit account
        accounts = get_accounts()
        acct_map = {a['name']: a['id'] for a in accounts}
        acct_names = list(acct_map.keys())
        if acct_names:
            credit_choice = st.selectbox("Credit proceeds to", ["Do not credit to account (manual)"] + acct_names)
            credit_account_id = acct_map.get(credit_choice) if credit_choice in acct_map else None
        else:
            credit_account_id = None

        if st.button("Redeem selected investment"):
            try:
                inv_id = inv_map[sel]
                ra = redeem_amt if redeem_amt>0 else None
                ok = redeem_investment(inv_id, redeem_amount=ra, credit_account=credit_account_id)
                if ok:
                    st.success("Investment redeemed & account credited (if selected).")
                else:
                    st.warning("Could not redeem (maybe already redeemed).")
            except Exception as ex:
                st.error(f"Failed to redeem: {ex}")
