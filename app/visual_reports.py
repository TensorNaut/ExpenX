# app/visual_reports.py
import io
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Frame, Spacer

# ----------------- Multi-month aggregation -----------------
def build_multi_month_agg(exp_raw: pd.DataFrame, months: int = 6, today=None):
    """
    Return aggregated monthly totals and category totals for the last `months`.
    Output:
      - month_index (list of month start datetimes)
      - totals_df: DataFrame with columns ['month','total_spent']
      - cat_month_df: DataFrame indexed by month with category columns (month x categories)
    """
    if today is None:
        today = pd.Timestamp.today().normalize()
    # normalize
    df = exp_raw.copy()
    df.columns = [c.lower() for c in df.columns]
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['amount'] = pd.to_numeric(df.get('amount', 0), errors='coerce').fillna(0)
    df['category'] = df.get('category', 'Uncategorized').fillna('Uncategorized')

    # compute month starts
    months_list = []
    first_of_this_month = today.replace(day=1)
    for i in reversed(range(months)):
        mstart = (first_of_this_month - pd.DateOffset(months=i)).replace(day=1)
        months_list.append(pd.Timestamp(mstart))

    # produce month label (YYYY-MM)
    df['month'] = df['date'].values.astype('datetime64[M]')

    totals = []
    cat_frames = []
    for mstart in months_list:
        # start and end
        start = pd.Timestamp(mstart)
        end = (start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
        mask = (df['date'] >= start) & (df['date'] <= end)
        slice_df = df.loc[mask]
        totals.append({'month': start, 'total_spent': float(slice_df['amount'].sum())})
        if not slice_df.empty:
            p = slice_df.groupby('category')['amount'].sum().rename(start)
            cat_frames.append(p)
        else:
            cat_frames.append(pd.Series(name=start, dtype=float))

    totals_df = pd.DataFrame(totals)
    # cat_month_df: rows=month, cols=categories
    if cat_frames:
        cat_month_df = pd.concat(cat_frames, axis=1).T.fillna(0)
    else:
        cat_month_df = pd.DataFrame()

    # ensure months order ascending (old -> new)
    totals_df = totals_df.sort_values('month')
    if not cat_month_df.empty:
        cat_month_df = cat_month_df.sort_index()
    return months_list, totals_df, cat_month_df


# ----------------- Plot builders -----------------
def plot_multi_month_total(totals_df):
    """
    Plotly figure: line chart of monthly totals.
    """
    fig = px.line(totals_df, x='month', y='total_spent', markers=True, title='Monthly Spend (Total)')
    fig.update_layout(xaxis_title='Month', yaxis_title='Amount (₹)', template='plotly_dark')
    return fig

def plot_top_categories_trend(cat_month_df, top_n=6):
    """
    Select top N categories by recent total and plot their monthly trends.
    """
    if cat_month_df.empty:
        fig = go.Figure()
        fig.update_layout(title="No category data")
        return fig

    # compute recent totals (last row is most recent month)
    recent_sum = cat_month_df.sum(axis=1)  # sums per month -> not needed, we need category totals across window
    # category totals across months:
    cat_totals = cat_month_df.sum(axis=0).sort_values(ascending=False)
    top_cats = cat_totals.head(top_n).index.tolist()
    trimmed = cat_month_df[top_cats]

    # plot
    fig = go.Figure()
    for c in trimmed.columns:
        fig.add_trace(go.Scatter(x=trimmed.index, y=trimmed[c], mode='lines+markers', name=str(c)))
    fig.update_layout(title=f"Top {len(trimmed.columns)} Category Trends", xaxis_title='Month', yaxis_title='Amount (₹)', template='plotly_dark')
    return fig

def plot_monthly_stacked(cat_month_df):
    """
    Stacked bar showing categories across months.
    """
    if cat_month_df.empty:
        fig = go.Figure()
        fig.update_layout(title="No category data")
        return fig
    df = cat_month_df.copy()
    df.index = df.index.astype(str)
    fig = px.bar(df, x=df.index, y=df.columns, title='Monthly Category Stacked', labels={'value':'Amount (₹)','x':'Month'})
    fig.update_layout(template='plotly_dark', barmode='stack')
    return fig

# ----------------- PDF generation -----------------
def _plotly_fig_to_png_bytes(fig, width=1200, height=600):
    """
    Convert a plotly figure to PNG bytes by writing to an in-memory PNG via kaleido.
    (Plotly's to_image requires kaleido.)
    """
    # This relies on plotly.kaleido (should be available), otherwise fall back to to_image (kaleido)
    try:
        img_bytes = fig.to_image(format="png", width=width, height=height, scale=2)
        return img_bytes
    except Exception as e:
        # As a fallback, try to write HTML then render? For simplicity, raise for now.
        raise

def generate_monthly_report_pdf(exp_raw: pd.DataFrame, budgets_data: dict, months=6):
    """
    Generate a multi-page PDF report as bytes.
    Contents:
      - Cover (title, date range)
      - Monthly totals chart
      - Top category trends chart
      - Stacked category chart
      - Small numeric summary & table
    Returns: bytes of PDF
    """
    # Build aggregated data
    months_list, totals_df, cat_month_df = build_multi_month_agg(exp_raw, months=months)
    # build figures
    fig_total = plot_multi_month_total(totals_df)
    fig_top = plot_top_categories_trend(cat_month_df, top_n=6)
    fig_stack = plot_monthly_stacked(cat_month_df)

    # Render figures to PNG bytes
    img_total = _plotly_fig_to_png_bytes(fig_total, width=1000, height=450)
    img_top = _plotly_fig_to_png_bytes(fig_top, width=1000, height=450)
    img_stack = _plotly_fig_to_png_bytes(fig_stack, width=1000, height=450)

    # Prepare PDF in memory
    buffer = io.BytesIO()
    # use landscape A4 for charts
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    styles = getSampleStyleSheet()
    title_style = styles['Title']
    normal = styles['Normal']

    # --- COVER PAGE ---
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, height - 50, "ExpenX — Monthly Budget Report")
    c.setFont("Helvetica", 12)
    c.drawString(40, height - 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # summary small box
    total_span = totals_df['total_spent'].sum()
    c.drawString(40, height - 110, f"Total across last {months} months: ₹{total_span:,.2f}")
    c.showPage()

    # --- TOTAL CHART PAGE ---
    img = ImageReader(io.BytesIO(img_total))
    c.drawImage(img, 30, 50, width - 60, height - 120, preserveAspectRatio=True, anchor='c')
    c.showPage()

    # --- TOP CATEGORIES CHART PAGE ---
    img = ImageReader(io.BytesIO(img_top))
    c.drawImage(img, 30, 50, width - 60, height - 120, preserveAspectRatio=True, anchor='c')
    c.showPage()

    # --- STACKED CHART PAGE ---
    img = ImageReader(io.BytesIO(img_stack))
    c.drawImage(img, 30, 50, width - 60, height - 120, preserveAspectRatio=True, anchor='c')
    c.showPage()

    # --- SUMMARY TABLE PAGE ---
    # Use portrait A4 for table
    c.setPageSize(A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30, h - 40, "Monthly Totals (summary)")
    c.setFont("Helvetica", 10)
    y = h - 70
    # write header
    c.drawString(40, y, "Month")
    c.drawString(200, y, "Total Spent (₹)")
    y -= 20
    for _, row in totals_df.iterrows():
        c.drawString(40, y, row['month'].strftime("%Y-%m"))
        c.drawString(200, y, f"{row['total_spent']:,.2f}")
        y -= 16
        if y < 80:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = h - 80
    c.showPage()

    c.save()
    buffer.seek(0)
    pdf_bytes = buffer.read()
    buffer.close()
    return pdf_bytes
