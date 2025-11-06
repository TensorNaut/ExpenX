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
from app.finance import get_accounts

from app.ledger import (
    create_person,
    list_persons,
    add_entry_for_person,
    get_entries_by_person,
    mark_entry_settled,
    get_person_summary,
    overall_summary,
    due_reminders,
    person_leaderboard
)

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
    st.subheader("📒 Ledger — People & Entries")

    # --- Top summary metrics ---
    summary = overall_summary()
    col1, col2, col3, col4 = st.columns(4)
    net_val = summary['net']
    net_label = f"₹{net_val:.2f}"
    # color hint in caption
    if net_val >= 0:
        col1.metric("Net Position (You are owed)", net_label)
    else:
        col1.metric("Net Position (You owe)", net_label)
    col2.metric("Total Lent", f"₹{summary['total_lent']:.2f}")
    col3.metric("Total Borrowed", f"₹{summary['total_borrowed']:.2f}")
    col4.metric("Open Dues", f"{summary['open_dues']}")

    st.markdown("---")

    # --- Due reminders (incoming / outgoing) ---
    st.markdown("### 🔔 Due reminders")
    reminders = due_reminders(days_ahead=14)  # next 14 days
    inc = reminders.get('incoming', [])
    out = reminders.get('outgoing', [])

    with st.expander(f"Incoming (People owe you) — {len(inc)} due soon"):
        if not inc:
            st.info("No incoming dues within next 14 days.")
        else:
            for r in inc:
                person_name = None
                # try to resolve person name
                if r.get('person_id'):
                    ps = next((p for p in list_persons() if p['id']==r['person_id']), None)
                    person_name = ps['name'] if ps else r.get('party') or "Unknown"
                else:
                    person_name = r.get('party') or "Unknown"
                days = r.get('days_left')
                cols = st.columns([3,2,2,2])
                cols[0].write(f"**{person_name}** — ₹{r['amount']:.2f} — {r.get('purpose') or ''}")
                cols[1].write(f"Due: {r.get('due_date')}")
                cols[2].write(f"{days} days")
                if cols[3].button(f"Mark settled (id {r['id']})", key=f"settle_in_{r['id']}"):
                    mark_entry_settled(r['id'], settled=True)
                    st.success("Marked settled.")
                    st.rerun()

    with st.expander(f"Outgoing (You owe others) — {len(out)} due soon"):
        if not out:
            st.info("No outgoing dues within next 14 days.")
        else:
            for r in out:
                person_name = None
                if r.get('person_id'):
                    ps = next((p for p in list_persons() if p['id']==r['person_id']), None)
                    person_name = ps['name'] if ps else r.get('party') or "Unknown"
                else:
                    person_name = r.get('party') or "Unknown"
                days = r.get('days_left')
                cols = st.columns([3,2,2,2])
                cols[0].write(f"**{person_name}** — ₹{r['amount']:.2f} — {r.get('purpose') or ''}")
                cols[1].write(f"Due: {r.get('due_date')}")
                cols[2].write(f"{days} days")
                if cols[3].button(f"Mark settled (id {r['id']})", key=f"settle_out_{r['id']}"):
                    mark_entry_settled(r['id'], settled=True)
                    st.success("Marked settled.")
                    st.rerun()

    st.markdown("---")

    # --- Person directory & Add Person ---
    st.markdown("### 👥 People")
    persons = list_persons()
    col_a, col_b = st.columns([3,2])
    with col_a:
        st.write("People in your ledger")
        if not persons:
            st.info("No people added yet. Use the form to add someone.")
        else:
            # show a compact list with net
            for p in persons:
                s = get_person_summary(p['id'])
                net = s['net']
                badge = " (owes you)" if net>0 else (" (you owe)" if net<0 else "")
                st.write(f"**{p['name']}** — Net: ₹{net:.2f}{badge} — Open dues: {s['open_dues_count']} — Last: {s['last_activity'] or '—'}")

    with col_b:
        st.write("➕ Add new person")
        new_name = st.text_input("Name", key="new_person_name")
        new_contact = st.text_input("Contact (phone/email)", key="new_person_contact")
        new_note = st.text_area("Notes (optional)", key="new_person_note", height=120)
        if st.button("Create Person"):
            if not new_name.strip():
                st.warning("Name is required.")
            else:
                try:
                    create_person(new_name.strip(), contact=new_contact.strip() or None, note=new_note.strip() or None)
                    st.success("Person created.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed to create person: {ex}")

    st.markdown("---")

    # --- Add entry (person-wise) ---
    st.markdown("### ➕ Add ledger entry")
    with st.form("add_ledger_form", clear_on_submit=False):
        persons = list_persons()
        person_options = ["<Choose person>"] + [p['name'] for p in persons]
        person_sel = st.selectbox("Person", person_options)
        direction = st.selectbox("Direction", ["lent", "borrowed"])  # lent = you lent (they owe you)
        amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="ledger_amount_form")
        date_val = st.date_input("Date", dt_date.today(), key="ledger_date_form")
        due_date = st.date_input("Due date (optional)", value=None, key="ledger_due_form")
        purpose = st.text_input("Purpose / Reason", key="ledger_purpose_form")
        # link to account if affects_balance
        acct_map = {a['name']: a['id'] for a in get_accounts()}
        acct_names = list(acct_map.keys())
        affects_balance = st.checkbox("Affects account balance?", value=False)
        account_choice = None
        if affects_balance:
            if acct_names:
                account_choice = st.selectbox("Select account to affect", ["<Choose account>"] + acct_names)
        notes = st.text_area("Notes (optional)", key="ledger_notes_form")
        submit = st.form_submit_button("Add Ledger Entry")
        if submit:
            # validate
            person_id = None
            party_text = None
            if person_sel and person_sel != "<Choose person>":
                # find id
                p = next((p for p in persons if p['name'] == person_sel), None)
                if p:
                    person_id = p['id']
            else:
                party_text = st.text_input("Party name (free-text)", key="ledger_party_temp")
                # note: above is rendered only now; advise user to re-submit if they entered free-text - simpler design: require person
                # For now if neither selected and no free-text, ask user to create person first
            if not person_id and not party_text:
                st.error("Please select a person or create one first (free-text not supported inline).")
            else:
                try:
                    acct_id = None
                    if affects_balance and account_choice and account_choice != "<Choose account>":
                        acct_id = acct_map.get(account_choice)
                    eid = add_entry_for_person(
                        person_id=person_id,
                        amount=amount,
                        direction=direction,
                        date_val=date_val,
                        due_date=due_date if due_date else None,
                        purpose=purpose,
                        contact=None,
                        notes=notes,
                        affects_balance=bool(affects_balance),
                        account_id=acct_id
                    )
                    st.success(f"Entry created (id {eid}).")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed to add entry: {ex}")

    st.markdown("---")

    # --- Person-wise entries & actions ---
    st.markdown("### 📁 Person-wise view")
    persons = list_persons()
    if not persons:
        st.info("No persons available. Add someone above to track ledger entries.")
    else:
        person_names = [p['name'] for p in persons]
        sel_person_name = st.selectbox("Select person to view", person_names, index=0)
        sel_person = next((p for p in persons if p['name'] == sel_person_name), None)
        if sel_person:
            pid = sel_person['id']
            p_summary = get_person_summary(pid)
            st.markdown(f"**{sel_person_name}** — Lent: ₹{p_summary['lent']:.2f} | Borrowed: ₹{p_summary['borrowed']:.2f} | Net: ₹{p_summary['net']:.2f} | Open dues: {p_summary['open_dues_count']}")
            entries = get_entries_by_person(pid, include_settled=True, limit=1000)
            if not entries:
                st.info("No entries for this person.")
            else:
                # show table and action buttons
                df_entries = pd.DataFrame(entries)
                # format dates
                if 'date' in df_entries.columns:
                    df_entries['date'] = pd.to_datetime(df_entries['date']).dt.date
                if 'due_date' in df_entries.columns:
                    df_entries['due_date'] = pd.to_datetime(df_entries['due_date'], errors='coerce').dt.date
                st.dataframe(df_entries, use_container_width=True)

                # Provide per-entry settle toggle
                st.markdown("**Actions**")
                for e in entries:
                    cols = st.columns([3,1,1,1])
                    cols[0].write(f"#{e['id']} — {e['direction']} — ₹{e['amount']:.2f} — {e.get('purpose') or ''} — Due: {e.get('due_date') or '—'} — Status: {e['status']}")
                    if e['status'] != 'settled':
                        if cols[2].button(f"Mark settled {e['id']}", key=f"person_settle_{e['id']}"):
                            mark_entry_settled(e['id'], settled=True)
                            st.success("Marked settled")
                            st.rerun()
                    else:
                        if cols[2].button(f"Mark active {e['id']}", key=f"person_unsettle_{e['id']}"):
                            mark_entry_settled(e['id'], settled=False)
                            st.success("Marked active")
                            st.rerun()

    st.markdown("---")

    # --- Leaderboard: person net balances ---
    st.markdown("### 🏆 Person leaderboard (by net)")
    leaderboard = person_leaderboard(limit=100)
    if not leaderboard:
        st.info("No data yet.")
    else:
        df_lb = pd.DataFrame(leaderboard)
        # format and colorize net (Streamlit dataframes can't color easily without st.table styler; keep simple)
        st.dataframe(df_lb[['name','lent','borrowed','net','open_dues','last_activity']], use_container_width=True)


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
