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

    import plotly.express as px
    import plotly.graph_objects as go
    import pandas as pd
    import io
    from datetime import datetime
    from app.visualizer import get_dashboard_data
    from streamlit import session_state as ss

    PLOTLY_TEMPLATE = "plotly_dark"
    DARK_BG = "#0b1320"
    CARD_BG = "#0f1724"
    ACCENT = "#2dd4bf"
    WARNING = "#ff7b6b"
    POSITIVE = "#6ee7b7"

    # ---------- utils ----------
    def fmt_cur(v):
        try:
            return f"₹{float(v):,.0f}"
        except Exception:
            return "₹0"

    def to_csv_bytes(df: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8")
        return buf.getvalue()

    def safe_df(x):
        return (x is not None) and (hasattr(x, "empty") and not x.empty) or (isinstance(x, pd.DataFrame) and not x.empty)

    # session defaults
    if 'dashboard_ref_date' not in ss:
        ss.dashboard_ref_date = datetime.now()
    if 'dashboard_range' not in ss:
        ss.dashboard_range = (datetime.now().replace(day=1), datetime.now())
    if 'dashboard_category_filter' not in ss:
        ss.dashboard_category_filter = None
    if 'dashboard_inv_filter' not in ss:
        ss.dashboard_inv_filter = None

    # ---------- Controls: period + nav + trend ----------
    cL, cM, cR = st.columns([3,1,2])
    with cL:
        period_mode = st.selectbox("Period mode", ["month", "year", "range"], index=0,
                                   help="Choose month / year / custom range for overview widgets")
    with cM:
        if period_mode == 'month':
            if st.button("← Prev"):
                ref = ss.dashboard_ref_date
                y, m = ref.year, ref.month - 1
                if m < 1:
                    y -= 1; m = 12
                ss.dashboard_ref_date = ref.replace(year=y, month=m, day=1)
            if st.button("Next →"):
                ref = ss.dashboard_ref_date
                y, m = ref.year, ref.month + 1
                if m > 12:
                    y += 1; m = 1
                ss.dashboard_ref_date = ref.replace(year=y, month=m, day=1)
        elif period_mode == 'year':
            if st.button("← Prev"):
                ss.dashboard_ref_date = ss.dashboard_ref_date.replace(year=ss.dashboard_ref_date.year - 1)
            if st.button("Next →"):
                ss.dashboard_ref_date = ss.dashboard_ref_date.replace(year=ss.dashboard_ref_date.year + 1)
    with cR:
        if period_mode == 'month':
            rd = st.date_input("Reference month (pick any day)", value=ss.dashboard_ref_date.date())
            ss.dashboard_ref_date = datetime(rd.year, rd.month, rd.day)
        elif period_mode == 'year':
            year_choice = st.number_input("Year", min_value=1970, max_value=2100, value=ss.dashboard_ref_date.year)
            ss.dashboard_ref_date = ss.dashboard_ref_date.replace(year=int(year_choice))
        else:
            rs, re = st.date_input("Range (start, end)", value=(ss.dashboard_range[0].date(), ss.dashboard_range[1].date()))
            ss.dashboard_range = (datetime(rs.year, rs.month, rs.day), datetime(re.year, re.month, re.day))

    trend_months = st.sidebar.selectbox("Trend range (months)", [3, 6, 12, 24], index=2)

    # ---------- Fetch data ----------
    try:
        if period_mode == 'month':
            data = get_dashboard_data(period_mode='month', reference_date=ss.dashboard_ref_date, trend_months=trend_months)
        elif period_mode == 'year':
            data = get_dashboard_data(period_mode='year', reference_date=ss.dashboard_ref_date, trend_months=trend_months)
        else:
            rs, re = ss.dashboard_range
            data = get_dashboard_data(period_mode='range', range_start=rs, range_end=re, trend_months=trend_months)
    except Exception as e:
        st.error(f"Failed to load dashboard data: {e}")
        st.stop()

    # ---------- Top-level filters ----------
    cat_choices = []
    try:
        cb = data.get('category_breakdown', pd.Series(dtype=float))
        if hasattr(cb, "index"):
            cat_choices = list(cb.index)
    except Exception:
        cat_choices = []
    with st.sidebar.expander("Filters", expanded=False):
        if cat_choices:
            sel_cat = st.multiselect("Filter categories (Overview)", options=cat_choices, default=ss.dashboard_category_filter or [])
            ss.dashboard_category_filter = sel_cat if sel_cat else None
        else:
            st.write("No categories")
        # investments filter
        inv_raw = data.get('investments', {}).get('raw', pd.DataFrame())
        inv_types = sorted(inv_raw['type'].dropna().unique().tolist()) if (hasattr(inv_raw, "empty") and not inv_raw.empty and 'type' in inv_raw.columns) else []
        if inv_types:
            sel_inv = st.multiselect("Investment types", options=inv_types, default=ss.dashboard_inv_filter or [])
            ss.dashboard_inv_filter = sel_inv if sel_inv else None

    # ---------- Download helper ----------
    def download_df(df: pd.DataFrame, label: str):
        if df is None or (hasattr(df, "empty") and df.empty):
            st.info(f"No {label} to download.")
            return
        b = to_csv_bytes(df)
        st.download_button(f"Download {label} CSV", data=b, file_name=f"{label}.csv", mime="text/csv")

    # ---------- Tabs ----------
    tabs = st.tabs(["Overview", "Trends", "Accounts", "Investments", "Ledger & Insights", "Data Export"])

    # ----------------- OVERVIEW -----------------
    with tabs[0]:
        p = data.get('period', {})
        start = p.get('start'); end = p.get('end')
        st.subheader(f"Overview — {start.date() if start else 'N/A'} → {end.date() if end else 'N/A'}")

        # Net Flow + Budget
        net = data.get('net_flow', {'income':0.0,'expense':0.0,'net':0.0})
        budgets = data.get('budgets', {})
        col1, col2, col3, col4 = st.columns([1,1,1,1])
        col1.metric("Income", fmt_cur(net.get('income', 0.0)))
        col2.metric("Expense", fmt_cur(net.get('expense', 0.0)))
        col3.metric("Net Flow", fmt_cur(net.get('net', 0.0)))
        if budgets and budgets.get('total_budget') is not None:
            col4.metric("Budget Remaining", fmt_cur(budgets.get('total_remaining', 0.0)))
        else:
            col4.metric("Budget Remaining", "Not Set")

        st.markdown("---")


        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Net Flow Overview")

            income_val = net.get('income', 0)
            expense_val = net.get('expense', 0)

            fig = go.Figure(
                data=go.Pie(
                    values=[income_val, expense_val],
                    labels=["Income", "Expense"],
                    hole=0.45,
                    marker=dict(colors=["#2dd4bf", "#ff7b6b"]),
                    hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>"
                )
            )

            fig.update_layout(
                template=PLOTLY_TEMPLATE,
                height=320,
                paper_bgcolor=DARK_BG,
                plot_bgcolor=DARK_BG,
                showlegend=True
            )

            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if budgets and budgets.get('total_budget') is not None:
                st.subheader("Budget Usage")

                total_b = budgets['total_budget']
                spent_b = budgets['total_spent']
                rem_b = budgets['total_remaining']

                fig2 = go.Figure(
                    data=go.Pie(
                        values=[spent_b, rem_b],
                        labels=["Spent", "Remaining"],
                        hole=0.45,
                        marker=dict(colors=["#ff7b6b", "#2dd4bf"]),
                        hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>"
                    )
                )

                fig2.update_layout(
                    template=PLOTLY_TEMPLATE,
                    height=320,
                    paper_bgcolor=DARK_BG,
                    plot_bgcolor=DARK_BG,
                    showlegend=True
                )

                st.plotly_chart(fig2, use_container_width=True)
        st.markdown("---")



        # Category Donut + Top categories
        cb = data.get('category_breakdown', pd.Series(dtype=float))
        if not (cb is None or (hasattr(cb,'empty') and cb.empty)):
            if ss.dashboard_category_filter:
                cb = cb[cb.index.isin(ss.dashboard_category_filter)]
            series = cb.fillna(0)
            series = series[series > 0]
            if series.sum() <= 0:
                st.info("No meaningful category spend to display.")
            else:
                left, right = st.columns([2,1])
                with left:
                    st.subheader("Category breakdown (donut)")
                    fig = px.pie(values=series.values, names=series.index, hole=0.45, template=PLOTLY_TEMPLATE,
                                 color_discrete_sequence=px.colors.sequential.Blues)
                    # INR hover
                    fig.update_traces(textinfo="percent+label", hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>")
                    fig.update_layout(height=420, paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG)
                    st.plotly_chart(fig, use_container_width=True)
                with right:
                    st.subheader("Top categories")
                    top_df = pd.DataFrame({'Category': series.index, 'Amount': series.values})
                    top_df['Amount_display'] = top_df['Amount'].map(lambda x: fmt_cur(x))
                    st.dataframe(top_df[['Category','Amount_display']].rename(columns={'Amount_display':'Amount'}), use_container_width=True)
                    download_df(top_df[['Category','Amount']], "top_categories")
        else:
            st.info("No expense data for this period.")

        st.markdown("---")

        # Daily Spending pattern
        st.subheader("Daily spending pattern")
        daily_df = data.get('daily_spend', pd.DataFrame())
        if daily_df is None or (hasattr(daily_df,'empty') and daily_df.empty):
            st.info("No daily spend data.")
        else:
            try:
                daily_df['Date'] = pd.to_datetime(daily_df['Date'])
                days_span = (daily_df['Date'].max() - daily_df['Date'].min()).days
                if days_span > 120:
                    plot_df = daily_df.set_index('Date').resample('W')['daily_spend'].sum().reset_index().rename(columns={'daily_spend':'value'})
                    xlabel = "Week"
                else:
                    plot_df = daily_df.rename(columns={'daily_spend':'value'})
                    xlabel = "Day"
                fig = px.bar(plot_df, x=plot_df.columns[0], y='value', labels={plot_df.columns[0]: xlabel, 'value': 'Amount (₹)'}, template=PLOTLY_TEMPLATE, height=340)
                st.plotly_chart(fig, use_container_width=True)
                download_df(plot_df, "daily_spend")
            except Exception as e:
                st.error(f"Failed to render daily spend: {e}")

        st.markdown("---")

        st.subheader("Income source split")
        inc_split = data.get('income_split', pd.Series(dtype=float))
        if inc_split is None or (hasattr(inc_split,'empty') and inc_split.empty) or inc_split.sum() == 0:
            st.info("No income data for this period.")
        else:
            series = inc_split.fillna(0)
            series = series[series > 0]
            fig = px.pie(values=series.values, names=series.index, hole=0.45, template=PLOTLY_TEMPLATE,
                            color_discrete_sequence=px.colors.sequential.Teal)
            fig.update_traces(textinfo="percent+label", hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>")
            fig.update_layout(height=320, paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG)
            st.plotly_chart(fig, use_container_width=True)
            download_df(pd.DataFrame({'source':series.index, 'amount':series.values}), "income_split")

        st.markdown("---")

        # ---------------------------------------------
        # DAY-OF-WEEK SPENDING PATTERN (BAR CHART)
        # ---------------------------------------------
        st.subheader("Day-of-Week Spending Pattern")

        # Compute day-of-week spend
        if daily_df is None or (hasattr(daily_df,'empty') and daily_df.empty):
            st.info("No spend data available for this period.")
        else:
            try:
                daily_df['Date'] = pd.to_datetime(daily_df['Date'])
                dow_df = (
                    daily_df.groupby(daily_df['Date'].dt.day_name())['daily_spend']
                    .sum()
                    .reindex(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
                    .reset_index()
                    .rename(columns={"Date":"day","daily_spend":"amount"})
                )
                fig = px.bar(
                    dow_df,
                    x="day",
                    y="amount",
                    labels={"day":"Day of Week", "amount":"Amount (₹)"},
                    template=PLOTLY_TEMPLATE,
                    color="amount",
                    color_continuous_scale=px.colors.sequential.Blues,
                    height=320
                )
                fig.update_layout(paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG)
                fig.update_traces(hovertemplate="₹%{y:,.0f} spent on %{x}<extra></extra>")
                st.plotly_chart(fig, use_container_width=True)

                download_df(dow_df, "day_of_week_spending")

            except Exception as e:
                st.error(f"Failed to generate day-of-week pattern: {e}")

        st.markdown("---")

        # ---------------------------------------------
        # MONTHLY CALENDAR HEATMAP (CLASSIC GRID)
        # ---------------------------------------------
        st.subheader("Calendar Heatmap (Monthly)")

        try:
            # Determine month start & end
            if period_mode == "month":
                ref = ss.dashboard_ref_date
                year = ref.year
                month = ref.month
            elif period_mode == "year":
                # default to current month in the selected year
                ref = ss.dashboard_ref_date
                year = ref.year
                month = ref.month
            else:
                # range mode → take start month
                rs, _ = ss.dashboard_range
                year = rs.year
                month = rs.month

            # Get a calendar matrix for the month
            import calendar
            cal = calendar.Calendar(firstweekday=0)  # Monday=0
            month_days = cal.monthdayscalendar(year, month)

            # Create mapping date → amount
            daily_map = dict(zip(pd.to_datetime(daily_df['Date']).dt.date, daily_df['daily_spend']))

            # Prepare heatmap matrix (0 if no spend)
            heat_values = []
            day_labels = []

            for week in month_days:
                row = []
                labels = []
                for d in week:
                    if d == 0:
                        # No date on this cell
                        row.append(None)
                        labels.append("")
                    else:
                        date_obj = datetime(year, month, d).date()
                        amt = float(daily_map.get(date_obj, 0))
                        row.append(float(amt))
                        labels.append(str(d))
                heat_values.append(row)
                day_labels.append(labels)

            # Build axes
            x_labels = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
            y_labels = [f"Week {i+1}" for i in range(len(heat_values))]

            # Convert to plotly heatmap
            fig = go.Figure(
                data=go.Heatmap(
                    z=heat_values,
                    x=x_labels,
                    y=y_labels,
                    text=day_labels,
                    texttemplate="%{text}",               # <--- FIXED (shows numbers)
                    textfont={"color": "black", "size": 20},
                    colorscale="Blues",
                    hovertemplate="Day %{text}<br>Spend: ₹%{z:,.0f}<extra></extra>",
                    showscale=True
                )
            )

            fig.update_layout(
                height=120 * len(heat_values),  # Auto height per month
                paper_bgcolor=DARK_BG,
                plot_bgcolor=DARK_BG,
                xaxis=dict(side="top"),
                margin=dict(l=10, r=10, t=30, b=10)
            )

            st.plotly_chart(fig, use_container_width=True)

            # Prepare flat export
            flat_rows = []
            for row_idx, week in enumerate(heat_values):
                for col_idx, amt in enumerate(week):
                    day_label = day_labels[row_idx][col_idx]
                    if day_label != "":
                        flat_rows.append({
                            "date": f"{year}-{month:02d}-{int(day_label):02d}",
                            "amount": amt
                        })
            cal_df = pd.DataFrame(flat_rows)
            download_df(cal_df, "calendar_heatmap")

        except Exception as e:
            st.error(f"Failed to generate calendar heatmap: {e}")
            st.markdown("---")        

            # Recurring & anomalies (collapsible)
            rec = data.get('recurring', pd.DataFrame())
            anom = data.get('anomalies', pd.DataFrame())
            with st.expander("Recurring expenses (auto-detected)", expanded=False):
                if rec is None or (hasattr(rec,'empty') and rec.empty):
                    st.info("No recurring items detected.")
                else:
                    st.dataframe(rec.head(200))
                    download_df(rec, "recurring_expenses")
            with st.expander("Anomalies / Outliers", expanded=False):
                if anom is None or (hasattr(anom,'empty') and anom.empty):
                    st.info("No anomalies detected.")
                else:
                    cols = [c for c in ['Date','Amount','Description','Category','z'] if c in anom.columns]
                    st.dataframe(anom[cols].sort_values('z', ascending=False).head(200))
                    download_df(anom[cols], "anomalies")

        st.markdown("---")

        # Budget insights
        st.subheader("Budget insights")
        b_ins = data.get('budget_insights', [])
        if not b_ins:
            st.info("No budget insights available.")
        else:
            for sg in b_ins:
                color = WARNING if ("exceed" in sg.lower() or "overspent" in sg.lower() or "⚠" in sg) else POSITIVE
                st.markdown(f"<div style='color:{color}'>• {sg}</div>", unsafe_allow_html=True)

    # ----------------- TRENDS -----------------
    with tabs[1]:
        st.subheader(f"Trends — last {trend_months} months")
        exp_tr = data.get('trend', {}).get('expense_trend', pd.DataFrame())
        inc_tr = data.get('trend', {}).get('income_trend', pd.DataFrame())
        cat_tr = data.get('trend', {}).get('category_trend', pd.DataFrame())
        port_tr = data.get('trend', {}).get('portfolio_trend', pd.DataFrame())

        if (exp_tr is None or (hasattr(exp_tr,'empty') and exp_tr.empty)) and (inc_tr is None or (hasattr(inc_tr,'empty') and inc_tr.empty)):
            st.info("Not enough data for trend charts.")
        else:
            fig = go.Figure()
            if exp_tr is not None and not (hasattr(exp_tr,'empty') and exp_tr.empty):
                fig.add_trace(go.Scatter(x=exp_tr.index.to_pydatetime(), y=exp_tr['total'].values, mode='lines+markers', name='Expenses', line=dict(color="#ff7b6b")))
            if inc_tr is not None and not (hasattr(inc_tr,'empty') and inc_tr.empty):
                fig.add_trace(go.Scatter(x=inc_tr.index.to_pydatetime(), y=inc_tr['total'].values, mode='lines+markers', name='Income', line=dict(color=ACCENT)))
            fig.update_layout(template=PLOTLY_TEMPLATE, height=360, paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG, xaxis_title="Month", yaxis_title="Amount (₹)")
            st.plotly_chart(fig, use_container_width=True)
            if exp_tr is not None and not (hasattr(exp_tr,'empty') and exp_tr.empty):
                download_df(exp_tr.reset_index().rename(columns={'index':'period','total':'expense'}), "expense_trend")
            if inc_tr is not None and not (hasattr(inc_tr,'empty') and inc_tr.empty):
                download_df(inc_tr.reset_index().rename(columns={'index':'period','total':'income'}), "income_trend")

        st.markdown("---")
        st.subheader("Category trend (stacked area)")
        if cat_tr is None or (hasattr(cat_tr,'empty') and cat_tr.empty):
            st.info("No category trend data.")
        else:
            fig = go.Figure()
            for col in cat_tr.columns:
                fig.add_trace(go.Scatter(x=cat_tr.index.to_pydatetime(), y=cat_tr[col].values, stackgroup='one', name=col))
            fig.update_layout(template=PLOTLY_TEMPLATE, height=420, paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG, xaxis_title="Month", yaxis_title="Amount (₹)")
            st.plotly_chart(fig, use_container_width=True)
            download_df(cat_tr.reset_index().rename(columns={'index':'month'}).melt(id_vars='month', var_name='category', value_name='amount'), "category_trend")

        st.markdown("---")
        st.subheader("Portfolio value trend")
        if port_tr is None or (hasattr(port_tr,'empty') and port_tr.empty):
            st.info("No portfolio trend snapshots available.")
        else:
            try:
                fig = px.line(port_tr, x='Date', y='value', title='Portfolio Value', template=PLOTLY_TEMPLATE)
                st.plotly_chart(fig, use_container_width=True)
                download_df(port_tr, "portfolio_trend")
            except Exception as e:
                st.error(f"Unable to render portfolio trend: {e}")

    # ----------------- ACCOUNTS -----------------
    with tabs[2]:
        st.subheader("Accounts snapshot")
        accounts = data.get('accounts', pd.DataFrame())
        if accounts is None or (hasattr(accounts,'empty') and accounts.empty):
            st.info("No accounts configured.")
        else:
            if 'balance' in accounts.columns:
                accounts['balance'] = pd.to_numeric(accounts['balance'], errors='coerce').fillna(0.0)
            st.dataframe(accounts[['id','name','balance','currency','kind']].sort_values(by='balance', ascending=False), use_container_width=True)
            if accounts['balance'].sum() > 0:
                series = accounts.set_index('name')['balance'].fillna(0)
                fig = px.pie(values=series.values, names=series.index, hole=0.45, template=PLOTLY_TEMPLATE, color_discrete_sequence=px.colors.sequential.Teal)
                fig.update_traces(textinfo='percent+label', hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>")
                st.plotly_chart(fig, use_container_width=True)
                download_df(accounts[['name','balance']], "accounts")
            else:
                st.info("No meaningful balances to show.")

    # ----------------- INVESTMENTS -----------------
    with tabs[3]:
        st.subheader("Investments")
        inv = data.get('investments', {})
        inv_summary = inv.get('summary', {'total_principal':0,'total_remaining':0,'current_value':0})
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Principal", fmt_cur(inv_summary.get('total_principal',0)))
        c2.metric("Principal Remaining", fmt_cur(inv_summary.get('total_remaining',0)))
        c3.metric("Current Value", fmt_cur(inv_summary.get('current_value',0)))
        st.markdown("---")
        gain_tbl = inv.get('gain_table', pd.DataFrame())
        if gain_tbl is None or (hasattr(gain_tbl,'empty') and gain_tbl.empty):
            st.info("No gain/loss data available.")
        else:
            st.dataframe(gain_tbl.sort_values('gain', ascending=False).head(200))
            download_df(gain_tbl, "investment_gain_loss")
        st.markdown("---")
        inv_dist = inv.get('distribution', pd.Series(dtype=float))
        if inv_dist is None or (hasattr(inv_dist,'empty') and inv_dist.empty) or inv_dist.sum() == 0:
            st.info("No distribution data.")
        else:
            inv_dist = inv_dist.fillna(0)
            fig = px.pie(values=inv_dist.values, names=inv_dist.index, hole=0.45, template=PLOTLY_TEMPLATE, color_discrete_sequence=px.colors.sequential.Agsunset)
            fig.update_traces(textinfo="percent+label", hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>")
            st.plotly_chart(fig, use_container_width=True)
            download_df(pd.DataFrame({'type':inv_dist.index, 'value':inv_dist.values}), "investment_distribution")

    # ----------------- LEDGER & INSIGHTS -----------------
    with tabs[4]:
        st.subheader("Ledger & Insights")
        ledger = data.get('ledger', {})
        st.write(ledger)
        st.markdown("---")
        st.subheader("Budget insights")
        ins = data.get('budget_insights', [])
        if not ins:
            st.info("No budget insights.")
        else:
            for it in ins:
                color = WARNING if ("exceed" in it.lower() or "overspent" in it.lower() or "⚠" in it) else POSITIVE
                st.markdown(f"<div style='color:{color}'>• {it}</div>", unsafe_allow_html=True)

        st.markdown("---")
        raw = data.get('raw', {})
        st.write("Expenses rows:", 0 if raw.get('expenses') is None else (len(raw.get('expenses')) if hasattr(raw.get('expenses'),'__len__') else 0))
        st.write("Income rows:", 0 if raw.get('income') is None else (len(raw.get('income')) if hasattr(raw.get('income'),'__len__') else 0))
        st.write("Budget rows:", 0 if raw.get('budgets') is None else (len(raw.get('budgets')) if hasattr(raw.get('budgets'),'__len__') else 0))

    # ----------------- DATA EXPORT (Simple mode) -----------------
    with tabs[5]:
        st.subheader("Data Export")
        exp_df = data.get('raw', {}).get('expenses', pd.DataFrame())
        inc_df = data.get('raw', {}).get('income', pd.DataFrame())
        bud_df = data.get('raw', {}).get('budgets', pd.DataFrame())

        export_mode = st.radio("Export Mode", ["Current Period", "Custom Range", "Monthly Export", "Yearly Export", "Full Dataset"], index=0)

        if export_mode == "Current Period":
            st.markdown("Download data for the currently selected period (Overview).")
            exp_period = data.get('exp_period', pd.DataFrame())
            inc_period = data.get('inc_period', pd.DataFrame())
            download_df(exp_period.reset_index(drop=True), "expenses_current_period")
            download_df(inc_period.reset_index(drop=True), "income_current_period")
        elif export_mode == "Custom Range":
            rs, re = st.date_input("Choose range (start, end)", value=(ss.dashboard_range[0].date(), ss.dashboard_range[1].date()))
            rs_dt = datetime(rs.year, rs.month, rs.day); re_dt = datetime(re.year, re.month, re.day)
            # filter raw frames safely
            try:
                exp_f = exp_df[(pd.to_datetime(exp_df['Date']) >= rs_dt) & (pd.to_datetime(exp_df['Date']) <= re_dt)].reset_index(drop=True) if (exp_df is not None and not getattr(exp_df,'empty',True)) else pd.DataFrame()
                inc_f = inc_df[(pd.to_datetime(inc_df['date']) >= rs_dt) & (pd.to_datetime(inc_df['date']) <= re_dt)].reset_index(drop=True) if (inc_df is not None and not getattr(inc_df,'empty',True)) else pd.DataFrame()
            except Exception:
                exp_f = pd.DataFrame(); inc_f = pd.DataFrame()
            download_df(exp_f, f"expenses_{rs_dt.date()}_{re_dt.date()}")
            download_df(inc_f, f"income_{rs_dt.date()}_{re_dt.date()}")
        elif export_mode == "Monthly Export":
            m = st.selectbox("Month", list(range(1,13)), index=ss.dashboard_ref_date.month-1)
            y = st.number_input("Year", min_value=1970, max_value=2100, value=ss.dashboard_ref_date.year)
            ms = datetime(y, m, 1)
            # compute month end
            if m == 12:
                me = datetime(y+1, 1, 1) - pd.Timedelta(days=1)
            else:
                me = datetime(y, m+1, 1) - pd.Timedelta(days=1)
            exp_f = exp_df[(pd.to_datetime(exp_df['Date']) >= ms) & (pd.to_datetime(exp_df['Date']) <= me)].reset_index(drop=True) if (exp_df is not None and not getattr(exp_df,'empty',True)) else pd.DataFrame()
            inc_f = inc_df[(pd.to_datetime(inc_df['date']) >= ms) & (pd.to_datetime(inc_df['date']) <= me)].reset_index(drop=True) if (inc_df is not None and not getattr(inc_df,'empty',True)) else pd.DataFrame()
            download_df(exp_f, f"expenses_{y}_{m:02d}")
            download_df(inc_f, f"income_{y}_{m:02d}")
        elif export_mode == "Yearly Export":
            y = st.number_input("Year (export)", min_value=1970, max_value=2100, value=ss.dashboard_ref_date.year)
            ys = datetime(y,1,1); ye = datetime(y,12,31)
            exp_f = exp_df[(pd.to_datetime(exp_df['Date']) >= ys) & (pd.to_datetime(exp_df['Date']) <= ye)].reset_index(drop=True) if (exp_df is not None and not getattr(exp_df,'empty',True)) else pd.DataFrame()
            inc_f = inc_df[(pd.to_datetime(inc_df['date']) >= ys) & (pd.to_datetime(inc_df['date']) <= ye)].reset_index(drop=True) if (inc_df is not None and not getattr(inc_df,'empty',True)) else pd.DataFrame()
            download_df(exp_f, f"expenses_{y}")
            download_df(inc_f, f"income_{y}")
        else:  # Full Dataset
            st.markdown("Export the full raw datasets (use with caution).")
            download_df(exp_df.reset_index(drop=True) if exp_df is not None else pd.DataFrame(), "expenses_full")
            download_df(inc_df.reset_index(drop=True) if inc_df is not None else pd.DataFrame(), "income_full")
            download_df(bud_df.reset_index(drop=True) if bud_df is not None else pd.DataFrame(), "budgets_full")

# End of block

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
