# app.py (with Ledger and Investments integrated)
import streamlit as st
from app.tracker import (
    add_expense,
    get_expenses,
    delete_expense_by_id,
    get_expense_by_id,
    update_expense,
    get_category_options,
    predict_category,
    load_model,
)
from app.finance import (
    get_accounts,
    create_account,
    add_income,
    transfer_between_accounts,
    get_account_by_name,
    add_ledger_entry,
    get_ledger,
)
from app.investments import create_investment, list_investments, redeem_investment
from datetime import date as dt_date
import pandas as pd
from app.finance import delete_account

# -----------------------------------------------------------
# APP CONFIG
# -----------------------------------------------------------
st.set_page_config(page_title="💸 ExpenX - Expense Manager", layout="centered")
st.title("💸 ExpenX - Expense Manager")

# -----------------------------------------------------------
# SESSION STATE HANDLER
# -----------------------------------------------------------
if 'model_loaded' not in st.session_state:
    st.session_state['model_loaded'] = False
if not st.session_state['model_loaded']:
    with st.spinner("Loading AI model and classifier..."):
        ok = load_model()
        st.session_state['model_loaded'] = bool(ok)
    if st.session_state['model_loaded']:
        st.sidebar.success("AI Model Loaded ✅")
    else:
        st.sidebar.warning("Model not loaded (predictions disabled).")

# Field clear logic
if 'add_description' not in st.session_state:
    st.session_state['add_description'] = ""
if 'add_custom_category' not in st.session_state:
    st.session_state['add_custom_category'] = ""
if st.session_state.get('clear_add_form', False):
    st.session_state['add_description'] = ""
    st.session_state['add_custom_category'] = ""
    st.session_state['clear_add_form'] = False

# -----------------------------------------------------------
# Ensure default accounts exist
# -----------------------------------------------------------
accounts_now = get_accounts()
existing_names = [a['name'].lower() for a in accounts_now]
needed_defaults = [
    ("Main", "bank"),
    ("Cash", "cash"),
    ("Credit Card", "card")
]
for name, kind in needed_defaults:
    if name.lower() not in existing_names:
        try:
            create_account(name, 0.0, kind=kind)
        except Exception:
            pass

# Reload accounts after ensuring defaults
accounts_now = get_accounts()

# -----------------------------------------------------------
# MENU
# -----------------------------------------------------------
menu = [
    "Add Expense",
    "View Expenses",
    "Edit Expense",
    "Income",
    "Accounts",
    "Transfer",
    "Ledger",
    "Investments",
    "Delete Expense"
]
choice = st.sidebar.selectbox("Menu", menu)

# -----------------------------------------------------------
# Helper
# -----------------------------------------------------------
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


# ===========================================================
# ADD EXPENSE
# ===========================================================
if choice == "Add Expense":
    st.subheader("➕ Add New Expense")

    amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
    description = st.text_input("Description", key="add_description")
    exp_date = st.date_input("Date", dt_date.today())

    # Predict category
    base_options = get_category_options()
    predicted = None
    if description and description.strip():
        with st.spinner("Predicting category..."):
            predicted = predict_category(description)

    dropdown_options = build_dropdown_options(base_options, predicted)
    category_selected = st.selectbox(
        "Category (change if needed)", options=dropdown_options, index=0
    )
    custom_cat = None
    if category_selected == "Other":
        custom_cat = st.text_input(
            "Enter custom category", value="", key="add_custom_category"
        ).strip()
        if not custom_cat:
            st.info("Please type your custom category.")

    # Payment Source
    accounts = get_accounts()
    acct_names = [a["name"] for a in accounts]
    payment_options = acct_names
    default_idx = 0
    if "Main" in acct_names:
        default_idx = acct_names.index("Main")
    payment_selected = st.selectbox("Payment Source", payment_options, index=default_idx)

    if st.button("Add Expense"):
        if amount > 0 and description.strip():
            try:
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

                # Get account id by name
                acc_obj = get_account_by_name(payment_selected)
                selected_account_id = acc_obj["id"] if acc_obj else None

                eid = add_expense(
                    amount=amount,
                    description=description,
                    date=exp_date,
                    category=pass_category,
                    payment_source=payment_selected,
                    account_id=selected_account_id,
                    use_model_when_none=use_model_flag,
                )
                st.success(f"✅ Expense added successfully! (id: {eid})")
                st.session_state["clear_add_form"] = True
                st.rerun()
            except Exception as ex:
                st.error(f"Failed to add expense: {ex}")
        else:
            st.warning("⚠️ Please enter valid details.")


# ===========================================================
# VIEW EXPENSES
# ===========================================================
elif choice == "View Expenses":
    st.subheader("📋 Expense History")
    df = get_expenses()
    if df.empty:
        st.info("No expenses found.")
    else:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df_sorted = df.sort_values(
            by=["Date", "id"], ascending=[False, False]
        ).reset_index(drop=True)
        st.dataframe(df_sorted, use_container_width=True)
        st.write("💰 Total Spent:", f"₹{df_sorted['Amount'].sum():.2f}")


# ===========================================================
# EDIT EXPENSE
# ===========================================================
elif choice == "Edit Expense":
    st.subheader("✏️ Edit Expense")
    df = get_expenses(limit=2000)
    if df.empty:
        st.info("No expenses found.")
    else:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df["display"] = df.apply(
            lambda x: f"{int(x['id'])} - ₹{x['Amount']} | {x['Description']} on {x['Date']} [{x['Category']}]",
            axis=1,
        )
        selection = st.selectbox("Select expense:", df["display"].tolist())
        if selection:
            eid = int(selection.split(" - ")[0])
            record = get_expense_by_id(eid)
            if record:
                edit_description = st.text_input(
                    "Description", value=record["Description"] or ""
                )
                edit_amount = st.number_input(
                    "Amount (₹)", value=float(record["Amount"]), format="%.2f"
                )
                edit_date = st.date_input(
                    "Date",
                    value=pd.to_datetime(record["Date"]).date()
                    if record["Date"]
                    else dt_date.today(),
                )

                predicted_edit = None
                if edit_description.strip():
                    with st.spinner("Predicting category..."):
                        predicted_edit = predict_category(edit_description)

                base_options = get_category_options()
                edit_options = build_dropdown_options(base_options, predicted_edit)
                cur_cat = record.get("Category", "")
                if cur_cat and cur_cat not in edit_options:
                    edit_options.insert(1, cur_cat)
                edit_category_selected = st.selectbox(
                    "Category", options=edit_options, index=0
                )
                if edit_category_selected == "Other":
                    edit_custom_cat = st.text_input("Custom category").strip()
                else:
                    edit_custom_cat = None

                # Payment Source
                accounts = get_accounts()
                acct_names = [a["name"] for a in accounts]
                cur_ps = record.get("PaymentSource") or "Main"
                if cur_ps not in acct_names:
                    acct_names.insert(0, cur_ps)
                edit_payment_selected = st.selectbox(
                    "Payment Source", options=acct_names, index=0
                )

                if st.button("Save Changes"):
                    try:
                        pass_cat = (
                            edit_custom_cat
                            if edit_category_selected == "Other"
                            else (
                                None
                                if edit_category_selected == predicted_edit
                                else edit_category_selected
                            )
                        )
                        acc_obj = get_account_by_name(edit_payment_selected)
                        acc_id = acc_obj["id"] if acc_obj else None
                        ok = update_expense(
                            eid,
                            date=edit_date,
                            amount=edit_amount,
                            description=edit_description,
                            category=pass_cat,
                            payment_source=edit_payment_selected,
                            account_id=acc_id,
                        )
                        if ok:
                            st.success("✅ Expense updated successfully.")
                            st.rerun()
                        else:
                            st.warning("⚠️ Expense not found or update failed.")
                    except Exception as ex:
                        st.error(f"Failed to update: {ex}")


# ===========================================================
# INCOME
# ===========================================================
elif choice == "Income":
    st.subheader("➕ Add Income / Credit")
    accounts = get_accounts()
    acct_map = {a["name"]: a["id"] for a in accounts}
    acct_names = list(acct_map.keys())
    if not acct_names:
        st.warning("No accounts available.")
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
                add_income(
                    account_id=acct_map[acct_sel],
                    amount=amount,
                    source=src or "Other",
                    date_val=date_val,
                    description=desc,
                )
                st.success("✅ Income added successfully!")
                st.rerun()
            except Exception as ex:
                st.error(f"Failed: {ex}")


# ===========================================================
# ACCOUNTS
# ===========================================================
elif choice == "Accounts":
    st.subheader("🏦 Accounts Overview")
    accounts = get_accounts()
    for a in accounts:
        if a["kind"] == "card":
            label = f"{a['name']} (Credit Card - outstanding)"
            val = f"₹{a['balance']:.2f}"
        else:
            label = f"{a['name']} ({a['kind']})"
            val = f"₹{a['balance']:.2f}"
        st.metric(label=label, value=val)

    with st.expander("Create New Account"):
        new_name = st.text_input("Account name")
        kind = st.selectbox("Kind", ["bank", "cash", "card"], index=0)
        init_bal = st.number_input("Initial balance", value=0.0, format="%.2f")
        if st.button("Create Account"):
            try:
                aid = create_account(new_name.strip(), init_bal, kind=kind)
                st.success(f"Created account: {new_name} ({kind}) [id={aid}]")
                st.rerun()
            except Exception as ex:
                st.error(f"Failed to create: {ex}")

    with st.expander("Account Details"):
        sel_acct = st.selectbox("Select account", [a["name"] for a in accounts])
        acct_obj = get_account_by_name(sel_acct)
        if acct_obj:
            st.write(f"**Account ID:** {acct_obj['id']}")
            st.write(f"**Name:** {acct_obj['name']}")
            st.write(f"**Kind:** {acct_obj['kind']}")
            st.write(f"**Currency:** {acct_obj['currency']}")
            st.write(f"**Balance:** ₹{acct_obj['balance']:.2f}")
        else:
            st.warning("Account not found.")

    with st.expander("Delete Account"):
        accounts = get_accounts()
        acct_map = {a["name"]: a["id"] for a in accounts}
        acct_names = list(acct_map.keys())

        if not acct_names:
            st.info("No accounts to delete.")
        else:
            sel_acct_del = st.selectbox("Select account to delete", acct_names)
            # Protect common default accounts
            protected = {"Main", "Cash", "Credit Card"}
            if sel_acct_del in protected:
                st.warning("Cannot delete default account.")
            else:
                confirm_text = st.text_input(
                    f"Type the account name ('{sel_acct_del}') to confirm deletion", key="confirm_delete"
                ).strip()
                if st.button("Delete Account"):
                    if confirm_text != sel_acct_del:
                        st.warning("Confirmation text does not match account name.")
                    else:
                        try:
                            ok = delete_account(acct_map[sel_acct_del])
                            if ok:
                                st.success(f"✅ Account '{sel_acct_del}' deleted.")
                                st.rerun()
                            else:
                                st.warning("⚠️ Account is in use. Please confirm deletion again.")
                        except Exception as ex:
                            st.error(f"Error deleting account: {ex}")


# ===========================================================
# TRANSFER
# ===========================================================
elif choice == "Transfer":
    st.subheader("🔄 Transfer Between Accounts")
    accounts = get_accounts()
    if len(accounts) < 2:
        st.info("Need at least two accounts.")
    else:
        acct_map = {a["name"]: a for a in accounts}
        acct_names = list(acct_map.keys())
        from_sel = st.selectbox("From Account", acct_names, index=0)
        to_sel = st.selectbox("To Account", acct_names, index=1)
        amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
        memo = st.text_input("Description (optional)")
        if st.button("Transfer"):
            try:
                if from_sel == to_sel:
                    st.warning("Choose different accounts!")
                else:
                    transfer_between_accounts(
                        acct_map[from_sel]["id"],
                        acct_map[to_sel]["id"],
                        amount,
                        description=memo,
                    )
                    st.success("✅ Transfer completed.")
                    st.rerun()
            except Exception as ex:
                st.error(f"Transfer failed: {ex}")


# ===========================================================
# LEDGER
# ===========================================================
elif choice == "Ledger":
    st.subheader("📒 Ledger (Lent / Borrowed)")

    # Create ledger entry
    with st.expander("➕ Add ledger entry"):
        accounts = get_accounts()
        acct_names = [a["name"] for a in accounts]
        acct_map = {a["name"]: a["id"] for a in accounts}

        ledger_account = st.selectbox("Link to Account (optional)", ["<none>"] + acct_names)
        amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="ledger_amount")
        direction = st.selectbox("Direction", ["lent", "borrowed"], index=0)
        party = st.text_input("Person / Party", key="ledger_party")
        due_date = st.date_input("Due date (optional)", value=None)
        purpose = st.text_input("Purpose", key="ledger_purpose")
        contact = st.text_input("Contact (optional)", key="ledger_contact")
        notes = st.text_area("Notes (optional)", key="ledger_notes")
        affects_bal = st.checkbox("Affects linked account balance?", value=False)

        if st.button("Add Ledger Entry"):
            try:
                aid = acct_map.get(ledger_account) if ledger_account and ledger_account != "<none>" else None
                lid = add_ledger_entry(
                    account_id=aid,
                    amount=amount,
                    direction=direction,
                    party=party,
                    date_val=None,
                    due_date=due_date if due_date else None,
                    purpose=purpose,
                    contact=contact,
                    notes=notes,
                    affects_balance=affects_bal
                )
                st.success(f"Ledger entry added (id {lid}).")
                st.rerun()
            except Exception as ex:
                st.error(f"Failed to add ledger entry: {ex}")

    # Display recent ledger entries
    st.markdown("### Recent ledger entries")
    ledger_rows = get_ledger(limit=200)
    if not ledger_rows:
        st.info("No ledger entries yet.")
    else:
        df_ledger = pd.DataFrame(ledger_rows)
        # format date columns
        if 'date' in df_ledger.columns:
            df_ledger['date'] = pd.to_datetime(df_ledger['date'], errors='coerce').dt.date
        st.dataframe(df_ledger, use_container_width=True)


# ===========================================================
# INVESTMENTS
# ===========================================================
elif choice == "Investments":
    st.subheader("📈 Investments")

    # Create investment form
    with st.expander("➕ Add new investment"):
        accounts = get_accounts()
        acct_map = {a['name']: a['id'] for a in accounts}
        acct_names = list(acct_map.keys())

        invest_amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="inv_amount")
        inv_date = st.date_input("Date", dt_date.today(), key="inv_date")
        inv_type = st.selectbox("Type", ["FD", "Mutual Fund", "Stock", "Bond", "Crypto", "Gold", "SIP", "Other"], key="inv_type")
        if inv_type == "Other":
            inv_type = st.text_input("Specify type", key="inv_type_other")
        risk = st.selectbox("Risk", ["Low", "Medium", "High", "Unknown"], index=3, key="inv_risk")
        mature_months = st.number_input("Mature period (months, optional)", min_value=0, value=0, key="inv_months")
        expected_return = st.number_input("Expected annual return (%) (optional)", min_value=0.0, format="%.2f", key="inv_return")
        description = st.text_input("Description (optional)", key="inv_desc")
        notes = st.text_area("Notes (optional)", key="inv_notes")

        # Funding source: choose account or other
        funding_opts = ["Other source (cash / external)"] + acct_names
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
                    # approximate maturity date by adding months
                    maturity_date = (pd.Timestamp(inv_date) + pd.DateOffset(months=int(mature_months))).date()
                aid = account_id if account_id else None
                inv_id = create_investment(
                    amount=invest_amount,
                    inv_type=inv_type,
                    date_val=inv_date,
                    account_id=aid,
                    description=description,
                    risk=risk,
                    mature_period_months=int(mature_months) if mature_months > 0 else None,
                    expected_return_percent=expected_return if expected_return > 0 else None,
                    debit_account=debit_account,
                    maturity_date=maturity_date,
                    notes=notes
                )
                st.success(f"Investment created (id {inv_id}).")
                st.rerun()
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

    # Redeem / mark matured
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
                ra = redeem_amt if redeem_amt > 0 else None
                ok = redeem_investment(inv_id, redeem_amount=ra, credit_account=credit_account_id)
                if ok:
                    st.success("Investment redeemed & account credited (if selected).")
                    st.rerun()
                else:
                    st.warning("Could not redeem (maybe already redeemed).")
            except Exception as ex:
                st.error(f"Failed to redeem: {ex}")


# ===========================================================
# DELETE EXPENSE
# ===========================================================
elif choice == "Delete Expense":
    st.subheader("🗑️ Delete Expense")
    df = get_expenses()
    if df.empty:
        st.info("No expenses to delete.")
    else:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df["display"] = df.apply(
            lambda x: f"{int(x['id'])} - ₹{x['Amount']} | {x['Description']} on {x['Date']} [{x['Category']}]",
            axis=1,
        )
        selection = st.selectbox("Select expense:", df["display"].tolist())
        if selection:
            eid = int(selection.split(" - ")[0])
            if st.button("Delete Selected"):
                try:
                    ok = delete_expense_by_id(eid)
                    if ok:
                        st.success("✅ Expense deleted.")
                        st.rerun()
                    else:
                        st.warning("⚠️ Expense not found.")
                except Exception as ex:
                    st.error(f"Failed: {ex}")
