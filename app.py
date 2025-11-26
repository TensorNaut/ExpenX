# app.py (with Ledger and Investments integrated)
import streamlit as st

from datetime import date as dt_date
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

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
from app.finance import delete_account
from app.finance import get_accounts

from app.ledger import (
    create_person,
    list_persons,
    add_entry_for_person,
    get_entries_by_person,
    settle_entry,
    mark_entry_settled,
    get_person_summary,
    overall_summary,
    due_reminders,
    person_leaderboard
)

from app.investments import (
    create_investment,
    list_investments,
    get_investment_by_id,
    redeem_investment,
    get_settlements_for_investment,
    portfolio_summary,
    _unit_label_for_type
)

from app.visualizer import (
    get_month_range, get_year_range, clamp_to_date,
    load_expenses_df, load_income_df, load_accounts_df, load_investments_df, load_budgets_df,
    filter_expenses, filter_income, net_flow, category_breakdown, top_categories, daily_spend,
    income_source_split, expense_trend, income_trend, category_trend_area, portfolio_trend,
    spending_heatmap_matrix, detect_recurring, detect_anomalies,
    investment_summary, investment_gain_loss, investment_distribution,
    ledger_activity,
    compute_budget_status, generate_budget_insights,
    get_dashboard_data
)


# -----------------------------------------------------------
# DATABASE INITIALIZATION & SCHEMA VALIDATION
# -----------------------------------------------------------

from app.schema_validator import validate_and_repair_schema

def init_db(auto_repair: bool = False):
    # existing init code: create tables if missing
    Base.metadata.create_all(bind=engine, checkfirst=True)

    # new: validate schema & optionally auto-repair mismatches
    try:
        # pass engine and metadata to validator
        report = validate_and_repair_schema(engine, Base.metadata, auto_repair=auto_repair)
        # optionally log the report, or keep simple print
        # logger.info(report)
    except Exception as e:
        # don't crash the entire app (but log it)
        import logging
        logging.getLogger("schema_validator").exception("Schema validation failed: %s", e)

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
    "📊 Analytics / Dashboard",
    "Add Expense",
    "View Expenses",
    "Edit Expense",
    "Income",
    "Accounts",
    "Transfer",
    "Ledger",
    "Investments",
    "Budgets",
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
# ANALYTICS / DASHBOARD
# ===========================================================

if choice == "📊 Analytics / Dashboard":
    st.title("📊 ExpenX — Analytics & Dashboard")

    import matplotlib.pyplot as plt
    import calendar
    from app.visualizer import get_dashboard_data
    from datetime import datetime

    # ---------------------
    # Controls: Period Mode
    # ---------------------
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([3, 1, 2])
    with col_ctrl1:
        period_mode = st.selectbox("Period mode", ["month", "year", "range"], index=0, help="Choose month / year / custom range for period-restricted widgets")
    # reference date stored in session for navigation
    if 'dashboard_ref_date' not in st.session_state:
        st.session_state.dashboard_ref_date = datetime.now()
    if 'dashboard_range' not in st.session_state:
        st.session_state.dashboard_range = (datetime.now().replace(day=1), datetime.now())

    # Prev / next navigation
    with col_ctrl2:
        if period_mode == 'month':
            if st.button("← Prev"):
                ref = st.session_state.dashboard_ref_date
                # move back one month
                y, m = ref.year, ref.month - 1
                if m < 1:
                    y -= 1
                    m = 12
                st.session_state.dashboard_ref_date = ref.replace(year=y, month=m, day=1)
            if st.button("Next →"):
                ref = st.session_state.dashboard_ref_date
                y, m = ref.year, ref.month + 1
                if m > 12:
                    y += 1
                    m = 1
                st.session_state.dashboard_ref_date = ref.replace(year=y, month=m, day=1)
        elif period_mode == 'year':
            if st.button("← Prev"):
                st.session_state.dashboard_ref_date = st.session_state.dashboard_ref_date.replace(year=st.session_state.dashboard_ref_date.year - 1)
            if st.button("Next →"):
                st.session_state.dashboard_ref_date = st.session_state.dashboard_ref_date.replace(year=st.session_state.dashboard_ref_date.year + 1)
        else:
            # range mode - no prev/next
            pass

    # Range / date inputs
    with col_ctrl3:
        if period_mode == 'month':
            # show current month label and a date_input to jump quick
            rd = st.date_input("Reference month (pick any day in month)", value=st.session_state.dashboard_ref_date.date())
            st.session_state.dashboard_ref_date = datetime(rd.year, rd.month, rd.day)
        elif period_mode == 'year':
            year_choice = st.number_input("Year", min_value=1970, max_value=2100, value=st.session_state.dashboard_ref_date.year)
            st.session_state.dashboard_ref_date = st.session_state.dashboard_ref_date.replace(year=int(year_choice))
        else:  # range
            rs, re = st.date_input("Range (start, end)", value=(st.session_state.dashboard_range[0].date(), st.session_state.dashboard_range[1].date()))
            st.session_state.dashboard_range = (datetime(rs.year, rs.month, rs.day), datetime(re.year, re.month, re.day))

    # Trend months selector (for trend-only panels)
    trend_months = st.sidebar.selectbox("Trend range (months)", options=[3, 6, 12, 24], index=2)

    # ---------------------
    # Fetch dashboard data (single call)
    # ---------------------
    if period_mode == 'month':
        ref = st.session_state.dashboard_ref_date
        data = get_dashboard_data(period_mode='month', reference_date=ref, trend_months=trend_months)
    elif period_mode == 'year':
        ref = st.session_state.dashboard_ref_date
        data = get_dashboard_data(period_mode='year', reference_date=ref, trend_months=trend_months)
    else:
        rs, re = st.session_state.dashboard_range
        data = get_dashboard_data(period_mode='range', range_start=rs, range_end=re, trend_months=trend_months)

    # ---------------------
    # Tabs: Overview | Trends | Accounts | Investments | Ledger & Insights
    # ---------------------
    tabs = st.tabs(["Overview", "Trends", "Accounts", "Investments", "Ledger & Insights"])

    # ---------------------
    # TAB: Overview (period-restricted)
    # ---------------------
    with tabs[0]:
        p = data['period']
        st.subheader(f"Overview — {p['start'].date()} → {p['end'].date()}")

        # Net flow + Budget in first row
        nf = data['net_flow']
        b_ins = data['budget_insights']
        col1, col2, col3 = st.columns([1.2, 1.2, 2])
        with col1:
            st.metric("Income", f"₹{nf['income']:.2f}")
            st.metric("Expense", f"₹{nf['expense']:.2f}")
        with col2:
            st.metric("Net", f"₹{nf['net']:.2f}", delta=f"₹{(nf['income'] - nf['expense']):.2f}")
        with col3:
            # Budget small panel
            budgets = data['budgets']
            if budgets and budgets.get('total_budget') is not None:
                tb = budgets['total_budget']
                used = budgets['total_spent']
                remaining = budgets['total_remaining']
                st.write(f"**Monthly budget:** ₹{tb:.0f} — Spent: ₹{used:.0f} — Remaining: ₹{remaining:.0f}")
                # simple gauge (matplotlib donut)
                fig, ax = plt.subplots(figsize=(3,3))
                ax.pie([used, max(0, tb - used)], labels=[f"Used ₹{used:.0f}", f"Remaining ₹{max(0, tb - used):.0f}"], autopct='%1.0f%%', startangle=90)
                ax.axis('equal')
                st.pyplot(fig)
            else:
                st.info("No total monthly budget set. Create a budget in Budgets.")

        st.markdown("---")

        # Category breakdown + Top categories
        cb = data['category_breakdown']
        if cb is None or cb.empty:
            st.info("No expense data for this period.")
        else:
            c1, c2 = st.columns([1.4, 1])
            with c1:
                st.subheader("Category breakdown")
                fig, ax = plt.subplots(figsize=(6, 4))
                cb.head(12).plot(kind='pie', y=None, ax=ax, autopct='%1.1f%%', legend=False)
                ax.set_ylabel("")
                st.pyplot(fig)
            with c2:
                st.subheader("Top categories")
                st.dataframe(data['top_categories'].rename_axis("Category").reset_index().rename(columns={'Category':'Category','top_categories':'Amount'}).head(10), use_container_width=True)

        st.markdown("---")

        # Daily spending pattern
        st.subheader("Daily spending pattern")
        daily_df = data['daily_spend']
        if daily_df is None or daily_df.empty:
            st.info("No daily spend data.")
        else:
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.bar(daily_df['Date'], daily_df['daily_spend'])
            ax.set_ylabel("Amount (₹)")
            ax.set_title("Daily spend")
            st.pyplot(fig)

        st.markdown("---")

        # Income source split + Heatmap (side-by-side)
        # s1, s2 = st.columns([1, 1])
        # with s1:
        st.subheader("Income sources")
        inc_split = data['income_split']
        if inc_split is None or inc_split.empty:
            st.info("No income data for this period.")
        else:
            fig, ax = plt.subplots(figsize=(4, 3))
            inc_split.plot(kind='pie', y=None, ax=ax, autopct='%1.1f%%', legend=False)
            ax.set_ylabel("")
            st.pyplot(fig)
        # with s2:
        #     st.subheader("Spending heatmap (day × hour)")
        #     hm = data['heatmap']
        #     if hm is None or hm.empty:
        #         st.info("No heatmap data (missing created_at or little data).")
        #     else:
        #         fig, ax = plt.subplots(figsize=(10, 3))
        #         im = ax.imshow(hm.values, aspect='auto')
        #         ax.set_yticks(range(len(hm.index)))
        #         ax.set_yticklabels(hm.index)
        #         ax.set_xlabel("Hour")
        #         fig.colorbar(im, ax=ax)
        #         st.pyplot(fig)

        st.markdown("---")

        # Recurring & Anomalies
        r1, r2 = st.columns(2)
        with r1:
            st.subheader("Recurring expenses (auto-detected)")
            rec = data['recurring']
            if rec is None or rec.empty:
                st.info("No recurring expenses detected in this period.")
            else:
                st.dataframe(rec.head(50))
        with r2:
            st.subheader("Anomalies (outliers)")
            anom = data['anomalies']
            if anom is None or anom.empty:
                st.info("No anomalies detected.")
            else:
                st.dataframe(anom[['Date','Amount','Description','Category','z']].sort_values('z', ascending=False).head(50))

    # ---------------------
    # TAB: Trends (multi-month)
    # ---------------------
    with tabs[1]:
        st.subheader(f"Trends — Last {trend_months} months")
        exp_tr = data['trend']['expense_trend']
        inc_tr = data['trend']['income_trend']
        cat_tr = data['trend']['category_trend']
        port_tr = data['trend']['portfolio_trend']

        # Expense vs Income line
        if (exp_tr is None or exp_tr.empty) and (inc_tr is None or inc_tr.empty):
            st.info("Not enough data for trend charts.")
        else:
            fig, ax = plt.subplots(figsize=(10, 3))
            if not exp_tr.empty:
                ax.plot(exp_tr.index.to_pydatetime(), exp_tr['total'].values, marker='o', label='Expenses')
            if not inc_tr.empty:
                ax.plot(inc_tr.index.to_pydatetime(), inc_tr['total'].values, marker='o', label='Income')
            ax.set_title("Income vs Expense (monthly)")
            ax.legend()
            st.pyplot(fig)

        st.markdown("---")

        # Category trend area (stacked)
        st.subheader("Category trend (area)")
        if cat_tr is None or cat_tr.empty:
            st.info("No category trend data.")
        else:
            fig, ax = plt.subplots(figsize=(10, 4))
            cat_tr.plot(kind='area', stacked=True, ax=ax)
            ax.set_title("Category spend over time")
            st.pyplot(fig)

        st.markdown("---")

        # Portfolio trend
        st.subheader("Portfolio value trend")
        if port_tr is None or port_tr.empty:
            st.info("No portfolio trend data (historical snapshots required).")
        else:
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.plot(port_tr['Date'], port_tr['value'], marker='o')
            ax.set_title("Portfolio Value")
            st.pyplot(fig)

    # ---------------------
    # TAB: Accounts
    # ---------------------
    with tabs[2]:
        st.subheader("Accounts — Snapshot")
        accounts = data['accounts']
        if accounts is None or accounts.empty:
            st.info("No accounts configured.")
        else:
            st.dataframe(accounts[['id','name','balance','currency','kind']].sort_values(by='balance', ascending=False), use_container_width=True)
            # account distribution pie
            fig, ax = plt.subplots(figsize=(6,4))
            try:
                series = accounts.set_index('name')['balance']
                series.plot(kind='pie', ax=ax, autopct='%1.1f%%')
                ax.set_ylabel("")
            except Exception:
                ax.text(0.5, 0.5, 'No distribution data', ha='center')
            st.pyplot(fig)

    # ---------------------
    # TAB: Investments
    # ---------------------
    with tabs[3]:
        st.subheader("Investments")
        inv = data['investments']
        inv_summary = inv['summary']
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Principal", f"₹{inv_summary['total_principal']:.2f}")
        c2.metric("Principal Remaining", f"₹{inv_summary['total_remaining']:.2f}")
        c3.metric("Current Value", f"₹{inv_summary['current_value']:.2f}")

        st.markdown("---")
        st.subheader("Investment gain/loss")
        gain_tbl = inv['gain_table']
        if gain_tbl is None or gain_tbl.empty:
            st.info("No gain/loss data available (current_value missing).")
        else:
            st.dataframe(gain_tbl.sort_values('gain', ascending=False).head(50), use_container_width=True)

        st.markdown("---")
        st.subheader("Investment distribution")
        inv_dist = inv['distribution']
        if inv_dist is None or inv_dist.empty or inv_dist.sum() == 0:
            st.info("No distribution data to display.")
        else:
            inv_dist = inv_dist.fillna(0)
            fig, ax = plt.subplots(figsize=(6,4))
            inv_dist.plot(kind='pie', ax=ax, autopct='%1.1f%%')
            ax.set_ylabel("")
            st.pyplot(fig)

    # ---------------------
    # TAB: Ledger & Insights
    # ---------------------
    with tabs[4]:
        st.subheader("Ledger & Insights")
        ledger = data['ledger']
        st.write(ledger)

        st.markdown("---")
        st.subheader("Budget insights (auto)")
        for insight in data['budget_insights']:
            st.write("•", insight)

        st.markdown("---")
        st.subheader("Raw data quick links")
        st.write("Expenses rows:", len(data['raw']['expenses']))
        st.write("Income rows:", len(data['raw']['income']))
        st.write("Budget rows:", len(data['raw']['budgets']))



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
# BUDGET MANAGEMENT
# ===========================================================
elif choice == "Budgets":
    st.subheader("💰 Budget Management")

    from app.finance import set_budget, get_budgets, delete_budget

    budgets = get_budgets()

    # ----------- Add Total Budget -----------
    st.markdown("### 🟦 Total Monthly Budget")
    with st.form("total_budget_form"):
        total_amount = st.number_input("Set total monthly budget (₹)", min_value=0.0, format="%.2f")
        submitted = st.form_submit_button("Save Total Budget")
        if submitted:
            try:
                set_budget(category=None, amount=total_amount, period="monthly", active=True)
                st.success("Total monthly budget saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("---")

    # ----------- Category Budgets -----------
    st.markdown("### 🟨 Category Budgets")

    # Fetch category options dynamically
    from app.tracker import get_category_options
    categories = get_category_options()

    with st.form("cat_budget_form"):
        cat = st.selectbox("Select category", categories)
        amt = st.number_input("Monthly budget amount (₹)", min_value=0.0, format="%.2f")
        save_cat = st.form_submit_button("Save Category Budget")
        if save_cat:
            try:
                set_budget(category=cat, amount=amt, period="monthly", active=True)
                st.success(f"Budget saved for '{cat}'.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

    st.markdown("---")

    # ----------- List Existing Budgets -----------
    st.markdown("### 📋 Existing Budgets")
    if not budgets:
        st.info("No budgets created yet.")
    else:
        import pandas as pd
        df_b = pd.DataFrame(budgets)
        st.dataframe(df_b[["id","category","amount","period","active","created_at"]], use_container_width=True)

        # Delete section
        del_id = st.number_input("Enter Budget ID to delete", min_value=0, step=1)
        if st.button("Delete Budget"):
            if del_id == 0:
                st.warning("Enter a valid ID.")
            else:
                try:
                    ok = delete_budget(int(del_id))
                    if ok:
                        st.success(f"Deleted budget ID {del_id}")
                        st.rerun()
                    else:
                        st.error("Budget not found.")
                except Exception as e:
                    st.error(f"Error deleting: {e}")


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

    with st.expander("💳 Settle Credit Card"):
        cards = [a for a in accounts if a["kind"] == "card"]
        banks = [a for a in accounts if a["kind"] in ("bank", "cash")]

        if not cards:
            st.info("No credit card accounts found.")
        elif not banks:
            st.info("No bank/cash account to pay from.")
        else:
            card_sel = st.selectbox("Select Credit Card", [c["name"] for c in cards])
            from_sel = st.selectbox("Pay From", [b["name"] for b in banks])
            amt = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
            note = st.text_input("Note (optional)")
            if st.button("Settle Now"):
                try:
                    from app.finance import get_account_by_name, settle_credit_card
                    card_id = get_account_by_name(card_sel)["id"]
                    payer_id = get_account_by_name(from_sel)["id"]
                    settle_credit_card(card_id, payer_id, amt, note)
                    st.success(f"✅ Payment of ₹{amt:.2f} made from {from_sel} to {card_sel}")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed: {ex}")
    
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
# ==========================================================
elif choice == "Ledger":
    st.subheader("📒 Ledger — People & Entries")

    # --- Top summary metrics ---
    summary = overall_summary()
    col1, col2, col3, col4 = st.columns(4)
    net_val = summary['net']
    if net_val >= 0:
        col1.metric("Net Position (You are owed)", f"₹{net_val:.2f}")
    else:
        col1.metric("Net Position (You owe)", f"₹{net_val:.2f}")
    col2.metric("Total Lent (open)", f"₹{summary['total_lent']:.2f}")
    col3.metric("Total Borrowed (open)", f"₹{summary['total_borrowed']:.2f}")
    col4.metric("Open Dues", f"{summary['open_dues']}")

    st.markdown("---")

    # --- Due reminders ---
    st.markdown("### 🔔 Due reminders (next 14 days)")
    reminders = due_reminders(days_ahead=14)
    inc = reminders.get('incoming', [])
    out = reminders.get('outgoing', [])

    persons_cache = list_persons()

    with st.expander(f"Incoming (People owe you) — {len(inc)} due soon"):
        if not inc:
            st.info("No incoming dues within next 14 days.")
        else:
            for r in inc:
                person_name = next((p['name'] for p in persons_cache if p['id']==r.get('person_id')), r.get('party') or "Unknown")
                days = r.get('days_left')
                cols = st.columns([3,2,2,2])
                cols[0].write(f"**{person_name}** — ₹{r['remaining_amount']:.2f} — {r.get('purpose') or ''}")
                cols[1].write(f"Due: {r.get('due_date')}")
                cols[2].write(f"{days} days")
                if cols[3].button(f"Settle (id {r['id']})", key=f"settle_in_{r['id']}"):
                    # create settle-focus flag for this id to show settle UI below
                    st.session_state[f"settle_focus_{r['id']}"] = True
                    st.rerun()

    with st.expander(f"Outgoing (You owe others) — {len(out)} due soon"):
        if not out:
            st.info("No outgoing dues within next 14 days.")
        else:
            for r in out:
                person_name = next((p['name'] for p in persons_cache if p['id']==r.get('person_id')), r.get('party') or "Unknown")
                days = r.get('days_left')
                cols = st.columns([3,2,2,2])
                cols[0].write(f"**{person_name}** — ₹{r['remaining_amount']:.2f} — {r.get('purpose') or ''}")
                cols[1].write(f"Due: {r.get('due_date')}")
                cols[2].write(f"{days} days")
                if cols[3].button(f"Settle (id {r['id']})", key=f"settle_out_{r['id']}"):
                    st.session_state[f"settle_focus_{r['id']}"] = True
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
            for p in persons:
                s = get_person_summary(p['id'])
                net = s['net']
                badge = " (owes you)" if net>0 else (" (you owe)" if net<0 else "")
                st.write(f"**{p['name']}** — Net open: ₹{net:.2f}{badge} — Open dues: {s['open_dues_count']} — Last: {s['last_activity'] or '—'}")

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
        person_sel = st.selectbox("Person", person_options, key="add_person_select")
        direction = st.selectbox("Direction", ["lent", "borrowed"], key="add_direction")
        amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="ledger_amount_form")
        date_val = st.date_input("Date", dt_date.today(), key="ledger_date_form")
        due_date = st.date_input("Due date (optional)", value=None, key="ledger_due_form")
        purpose = st.text_input("Purpose / Reason", key="ledger_purpose_form")
        interest_rate = st.number_input("Interest rate (%) (optional)", min_value=0.0, value=0.0, format="%.2f")
        # Account dropdown replaces checkbox; default Main if present
        acct_list = get_accounts()
        acct_map = {a['name']: a['id'] for a in acct_list}
        acct_options = ["<Does not affect>"] + list(acct_map.keys())
        default_idx = 0
        if "Main" in acct_map:
            default_idx = acct_options.index("Main")
        account_choice = st.selectbox("Affects which account? (choose '<Does not affect>' if none)", acct_options, index=default_idx)
        notes = st.text_area("Notes (optional)", key="ledger_notes_form")
        submit = st.form_submit_button("Add Ledger Entry")
        if submit:
            # resolve person
            person_id = None
            if person_sel and person_sel not in ("<Choose person>", "<Type new person>"):
                p = next((p for p in persons if p['name'] == person_sel), None)
                if p:
                    person_id = p['id']
            else:
                st.error("Please select or type a person name.")
                person_id = None

            if person_id:
                try:
                    acct_id = acct_map.get(account_choice) if account_choice and account_choice != "<Does not affect>" else None
                    eid = add_entry_for_person(
                        person_id=person_id,
                        amount=amount,
                        direction=direction,
                        date_val=date_val,
                        due_date=due_date if due_date else None,
                        purpose=purpose,
                        contact=None,
                        notes=notes,
                        affects_balance=True if acct_id else False,
                        account_id=acct_id,
                        interest_rate=interest_rate
                    )
                    st.success(f"Entry created (id {eid}).")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed to add entry: {ex}")

    st.markdown("---")

    # --- Person-wise entries & settlement ---
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
            st.markdown(f"**{sel_person_name}** — Lent total: ₹{p_summary['lent']:.2f} | Borrowed total: ₹{p_summary['borrowed']:.2f} | Open Lent: ₹{p_summary['lent_open']:.2f} | Open Borrowed: ₹{p_summary['borrowed_open']:.2f} | Net open: ₹{p_summary['net']:.2f} | Open dues: {p_summary['open_dues_count']}")
            entries = get_entries_by_person(pid, include_settled=True, limit=1000)
            if not entries:
                st.info("No entries for this person.")
            else:
                # show entries and settle UI
                acct_map = {a['name']: a['id'] for a in get_accounts()}
                acct_options = ["<Does not affect>"] + list(acct_map.keys())
                for e in entries:
                    remaining = float(e.get('remaining_amount') if e.get('remaining_amount') is not None else e.get('amount'))
                    cols = st.columns([4,1,1,2])
                    cols[0].write(f"#{e['id']} — {e['direction']} — ₹{e['amount']:.2f} — Remaining: ₹{remaining:.2f} — {e.get('purpose') or ''} — Due: {e.get('due_date') or '—'} — Status: {e['status']}")
                    # settle expander
                    with cols[3].expander("Settle"):
                        st.write("Settle this entry (partial/full)")
                        settle_max = remaining
                        settle_amt = st.number_input(f"Amount to settle (max {settle_max:.2f})", min_value=0.0, max_value=settle_max, format="%.2f", key=f"settle_amt_{e['id']}")
                        acct_choice = st.selectbox("Affect which account?", acct_options, index=0, key=f"settle_acc_{e['id']}")
                        acct_choice_id = acct_map.get(acct_choice) if acct_choice and acct_choice != "<Does not affect>" else None
                        settle_note = st.text_input("Note (optional)", key=f"settle_note_{e['id']}")
                        if st.button(f"Apply settle {e['id']}", key=f"apply_settle_{e['id']}"):
                            try:
                                if settle_amt <= 0:
                                    st.error("Enter an amount > 0")
                                else:
                                    settle_entry(e['id'], settle_amt, account_id=acct_choice_id, note=settle_note)
                                    st.success("Settlement applied.")
                                    st.rerun()
                            except Exception as ex:
                                st.error(f"Failed to settle: {ex}")

    st.markdown("---")

    # --- Leaderboard: person net balances ---
    st.markdown("### 🏆 Overall Summary (by net open)")
    leaderboard = person_leaderboard(limit=100)
    if not leaderboard:
        st.info("No data yet.")
    else:
        df_lb = pd.DataFrame(leaderboard)
        st.dataframe(df_lb[['name','lent_open','borrowed_open','net','open_dues','last_activity']], use_container_width=True)


# ===========================================================
# INVESTMENTS
# ===========================================================
elif choice == "Investments":
    st.subheader("📈 Investments")

    # Summary metrics
    ps = portfolio_summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Invested", f"₹{ps['total_principal']:.2f}")
    c2.metric("Principal Remaining", f"₹{ps['total_remaining']:.2f}")
    c3.metric("Current Value (est.)", f"₹{ps['current_value']:.2f}")

    st.markdown("---")

    # Add investment form
    st.markdown("### ➕ Add Investment")
    with st.form("add_inv_form", clear_on_submit=False):
        amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f", key="inv_amount")
        inv_date = st.date_input("Date", dt_date.today(), key="inv_date")
        inv_type = st.selectbox("Type", ["FD","Mutual Fund","Stock","Bond","Gold","Silver","Crypto","SIP","Other"], key="inv_type")
        unit_label, has_unit = _unit_label_for_type(inv_type)
        qty = None
        purchase_price = None
        if has_unit:
            qty = st.number_input(f"Quantity ({unit_label})", min_value=0.0, key="inv_qty")
            purchase_price = st.number_input(f"Purchase price per {unit_label} (optional)", min_value=0.0, format="%.2f", key="inv_ppu")
        risk = st.selectbox("Risk", ["Low","Medium","High","Unknown"], index=3, key="inv_risk")
        maturity_date = st.date_input("Maturity date (optional)", value=None, key="inv_mature")
        expected_return = st.number_input("Expected annual return (%)", min_value=0.0, format="%.2f", key="inv_return")
        accounts = get_accounts()
        acct_map = {a['name']: a['id'] for a in accounts}
        acct_options = ["<Does not debit>"] + list(acct_map.keys())
        default_idx = 0
        if "Main" in acct_map:
            default_idx = acct_options.index("Main")
        fund_account = st.selectbox("Debit which account (optional)", acct_options, index=default_idx)
        debit_flag = fund_account != "<Does not debit>"
        notes = st.text_area("Notes (optional)", key="inv_notes")
        submit = st.form_submit_button("Create Investment")
        if submit:
            acct_id = acct_map.get(fund_account) if debit_flag else None
            try:
                inv_id = create_investment(
                    amount=amount,
                    inv_type=inv_type,
                    date_val=inv_date,
                    account_id=acct_id,
                    risk=risk,
                    expected_return_percent=expected_return,
                    debit_account=debit_flag,
                    maturity_date=maturity_date if maturity_date else None,
                    notes=notes,
                    quantity=qty if qty and qty>0 else None,
                    purchase_price_per_unit=purchase_price if purchase_price and purchase_price>0 else None
                )
                st.success(f"Investment created (id {inv_id}).")
                st.experimental_rerun()
            except Exception as ex:
                st.error(f"Failed to create investment: {ex}")

    st.markdown("---")

    # Active investments (available for redemption)
    st.markdown("### Active investments (available for redemption)")
    active = list_investments(status=None, include_zero_remaining=False)
    if not active:
        st.info("No active investments available for redemption.")
    else:
        for inv in active:
            title = f"#{inv['id']} | {inv['type']} — ₹{inv['amount']:.2f} (rem ₹{inv['principal_remaining']:.2f})"
            st.write(title)
            meta = []
            if inv.get('quantity') is not None:
                meta.append(f"{inv['quantity']} {inv.get('unit_label') or ''}")
                if inv.get('purchase_price_per_unit'):
                    meta.append(f"p.p.u ₹{inv['purchase_price_per_unit']}")
            if inv.get('risk'):
                meta.append(inv['risk'])
            if inv.get('maturity_date'):
                meta.append(f"matures {inv['maturity_date']}")
            st.write(" • ".join(meta))

            # Redeem UI
            with st.expander("Redeem / Partial redeem"):
                max_redeem = inv['principal_remaining']
                redeem_amount = st.number_input(f"Amount to redeem (max ₹{max_redeem:.2f})", min_value=0.0, max_value=max_redeem, format="%.2f", key=f"redeem_amt_{inv['id']}")
                qty = None
                if inv.get('quantity') is not None and inv.get('unit_label'):
                    ppu = inv.get('current_price_per_unit') or inv.get('purchase_price_per_unit')
                    st.write(f"Unit: {inv.get('unit_label')} | Available qty: {inv.get('quantity')}")
                    qty = st.number_input(f"Quantity to redeem (max {inv.get('quantity')})", min_value=0.0, max_value=inv.get('quantity'), format="%.4f", key=f"redeem_qty_{inv['id']}")
                    st.write(f"Using price per unit: {ppu if ppu else 'N/A'}")

                acct_map = {a['name']: a['id'] for a in get_accounts()}
                acct_options = ["<Do not credit>"] + list(acct_map.keys())
                default_idx = 0
                if "Main" in acct_map:
                    default_idx = acct_options.index("Main")
                credit_choice = st.selectbox("Credit proceeds to", acct_options, index=default_idx, key=f"redeem_credit_{inv['id']}")
                credit_id = acct_map.get(credit_choice) if credit_choice and credit_choice != "<Do not credit>" else None
                note = st.text_input("Note (optional)", key=f"redeem_note_{inv['id']}")
                if st.button(f"Redeem now (id {inv['id']})", key=f"redeem_btn_{inv['id']}"):
                    try:
                        if qty and qty > 0:
                            settlement_id = redeem_investment(inv['id'], quantity=qty, credit_account=credit_id, note=note)
                        else:
                            if redeem_amount <= 0:
                                st.error("Enter amount to redeem or quantity")
                                continue
                            settlement_id = redeem_investment(inv['id'], amount=redeem_amount, credit_account=credit_id, note=note)
                        st.success(f"Redeemed (settlement id {settlement_id}).")
                        st.experimental_rerun()
                    except Exception as ex:
                        st.error(f"Failed to redeem: {ex}")

            # Details & settlement history
            with st.expander("Details & settlements"):
                inv_full = get_investment_by_id(inv['id'])
                # Display key fields
                st.write({
                    'id': inv_full['id'],
                    'type': inv_full['type'],
                    'amount': f"₹{inv_full['amount']:.2f}",
                    'principal_remaining': f"₹{inv_full['principal_remaining']:.2f}",
                    'quantity': inv_full.get('quantity'),
                    'unit': inv_full.get('unit_label'),
                    'current_price_per_unit': inv_full.get('current_price_per_unit'),
                    'current_value': inv_full.get('current_value'),
                    'status': inv_full.get('status'),
                    'notes': inv_full.get('notes')
                })
                st.markdown("**Settlement history**")
                settlements = get_settlements_for_investment(inv['id'])
                if not settlements:
                    st.info("No settlements yet for this investment.")
                else:
                    import pandas as pd
                    df = pd.DataFrame(settlements)
                    st.dataframe(df, use_container_width=True)

    st.markdown("---")
