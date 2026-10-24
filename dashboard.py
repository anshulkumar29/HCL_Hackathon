"""ShopSphere dashboard (Phase 6).

Run from this folder:   streamlit run dashboard.py

It only READS the files made by the pipeline (kpi_outputs/*.csv, silver/rejects.csv, before_after_counts.csv, pipeline.log).
If a file is missing, run:  python 04_pipeline.py
"""
import pandas as pd
import plotly.express as px
import streamlit as st

import kpi_lib as k

st.set_page_config(page_title='ShopSphere Analytics', page_icon=':bar_chart:', layout='wide')


# ------------------------------------------------------------------ loading data
@st.cache_data
def load_csv(path):
    return pd.read_csv(path)


def kpi(name):
    """Read one KPI result file from kpi_outputs/"""
    return load_csv(k.OUT_DIR / f'{name}.csv')


def inr(x):
    """Format a number as rupees, e.g. 1234567 -> Rs 12.35 L (lakh)"""
    if abs(x) >= 1e7:
        return f'Rs {x / 1e7:,.2f} Cr'
    if abs(x) >= 1e5:
        return f'Rs {x / 1e5:,.2f} L'
    return f'Rs {x:,.0f}'


# ------------------------------------------------------------------ page 1: overview
def page_overview():
    st.title('ShopSphere - E-Commerce Analytics')
    st.caption('HCL Hackathon | raw files -> clean tables -> KPIs -> dashboard')

    rev = kpi('kpi_01_net_revenue_by_category_month')
    seg = kpi('kpi_03_segment_profile')
    rep = kpi('kpi_07_repeat_purchase_rate').iloc[0]
    risk = kpi('kpi_09_margin_risk_total').iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Net revenue', inr(rev.net_revenue.sum()))
    c2.metric('Approved refunds', inr(rev.approved_refunds.sum()))
    c3.metric('Customers', int(seg.customers.sum()))
    c4.metric('Repeat-purchase rate (90 days)', f'{rep.repeat_rate_pct:.1f}%')

    left, right = st.columns(2)
    by_cat = rev.groupby('category', as_index=False).net_revenue.sum().sort_values('net_revenue', ascending=False)
    fig = px.bar(by_cat, x='category', y='net_revenue', color='category', title='Net revenue by category')
    fig.update_layout(showlegend=False, yaxis_title='Net revenue', xaxis_title='')
    left.plotly_chart(fig, width='stretch')

    fig = px.pie(seg, names='segment', values='customers', title='Customers by segment', hole=0.45)
    right.plotly_chart(fig, width='stretch')

    st.info(f"Stretch KPI: {int(risk.products_affected)} products were sold below cost, "
            f"a total loss of {inr(risk.total_loss)} (before returns).")

    st.subheader('How the numbers are built')
    st.markdown(
        "- **Revenue** = recomputed line total of *Completed* and *Returned* orders, minus *Approved* refunds.\n"
        "- **Cancelled and Pending** orders are not revenue.\n"
        "- Use the menu on the left to open each KPI, the data-quality page and the pipeline page.")


# ------------------------------------------------------------------ page 2: KPI 1
def page_revenue():
    st.title('KPI 1 - Net revenue by category and month')
    df = kpi('kpi_01_net_revenue_by_category_month')
    df['year'] = df.order_month.str[:4]

    col1, col2 = st.columns(2)
    years = col1.multiselect('Year', sorted(df.year.unique()), default=sorted(df.year.unique()))
    cats = col2.multiselect('Category', sorted(df.category.unique()), default=sorted(df.category.unique()))
    view = df[df.year.isin(years) & df.category.isin(cats)]

    a, b, c = st.columns(3)
    a.metric('Gross revenue', inr(view.gross_revenue.sum()))
    b.metric('Approved refunds', inr(view.approved_refunds.sum()))
    c.metric('Net revenue', inr(view.net_revenue.sum()))

    fig = px.bar(view, x='order_month', y='net_revenue', color='category', title='Net revenue per month (stacked by category)')
    fig.update_layout(xaxis_title='Month', yaxis_title='Net revenue')
    st.plotly_chart(fig, width='stretch')

    summary = (view.groupby('category')[['gross_revenue', 'approved_refunds', 'net_revenue']].sum()
                   .sort_values('net_revenue', ascending=False).round(2))
    st.subheader('Totals by category')
    st.dataframe(summary, width='stretch')

    with st.expander('See the detailed table'):
        st.dataframe(view.drop(columns='year'), width='stretch')
    st.caption('Refunds are counted in the month of the order. Almost all orders are in 2024-2025, so earlier months are thin.')


# ------------------------------------------------------------------ page 3: customers (KPI 2, 3, 7)
def page_customers():
    st.title('Customers - KPI 2, KPI 3 and KPI 7')

    # KPI 2
    st.subheader('KPI 2 - Top 10 customers by net lifetime value')
    top = kpi('kpi_02_top10_customers_ltv')
    fig = px.bar(top.sort_values('net_lifetime_value'), x='net_lifetime_value', y='customer_name',
                 color='segment', orientation='h', hover_data=['customer_id', 'city', 'completed_orders'])
    fig.update_layout(xaxis_title='Net lifetime value', yaxis_title='')
    st.plotly_chart(fig, width='stretch')
    st.dataframe(top, width='stretch', hide_index=True)
    st.caption('Only Completed orders, net of approved returns. Orders of customers missing from the customer table are excluded.')

    # KPI 3
    st.subheader('KPI 3 - Segment profile')
    seg = kpi('kpi_03_segment_profile')
    left, right = st.columns(2)
    fig = px.bar(seg, x='segment', y='customers', color='segment', title='Customers per segment', text='customers')
    fig.update_layout(showlegend=False, xaxis_title='')
    left.plotly_chart(fig, width='stretch')
    fig = px.bar(seg, x='segment', y='avg_order_value', color='segment', title='Average order value (AOV)')
    fig.update_layout(showlegend=False, xaxis_title='')
    right.plotly_chart(fig, width='stretch')
    st.dataframe(seg, width='stretch', hide_index=True)

    # KPI 7
    st.subheader('KPI 7 - Repeat-purchase rate (second order within 90 days)')
    rep = kpi('kpi_07_repeat_purchase_rate').iloc[0]
    detail = kpi('kpi_07_repeat_purchase_detail')
    a, b, c = st.columns(3)
    a.metric('Customers with a completed order', int(rep.customers_with_completed_order))
    b.metric('Repeat customers', int(rep.repeat_customers))
    c.metric('Repeat rate', f'{rep.repeat_rate_pct:.2f}%')

    gaps = detail.dropna(subset=['days_to_second_order'])
    fig = px.histogram(gaps, x='days_to_second_order', nbins=20, title='Days between first and second order (customers with 2+ orders)')
    fig.add_vline(x=90, line_dash='dash', line_color='red', annotation_text='90-day limit')
    fig.update_layout(xaxis_title='Days', yaxis_title='Customers')
    st.plotly_chart(fig, width='stretch')
    st.caption(f'{int(rep.repeat_customers_with_ambiguous_dates)} of the repeat customers depend on a date that could be read two ways (MM/DD or DD/MM).')


# ------------------------------------------------------------------ page 4: margin risk (stretch)
def page_margin():
    st.title('Stretch KPI - Margin risk')
    st.write('Lines where the **cost price is higher than the selling price after discount** (sold at a loss).')
    df = kpi('kpi_09_margin_risk_by_product')
    tot = kpi('kpi_09_margin_risk_total').iloc[0]

    a, b, c, d = st.columns(4)
    a.metric('Products affected', int(tot.products_affected))
    b.metric('Units sold at a loss', int(tot.units_affected))
    c.metric('Revenue exposed', inr(tot.revenue_exposed))
    d.metric('Total loss', inr(tot.total_loss))

    n = st.slider('Show top N products by loss', 5, len(df), 10)
    fig = px.bar(df.head(n).sort_values('total_loss'), x='total_loss', y='product_name', color='category', orientation='h')
    fig.update_layout(xaxis_title='Loss', yaxis_title='')
    st.plotly_chart(fig, width='stretch')

    by_cat = df.groupby('category', as_index=False).total_loss.sum()
    st.plotly_chart(px.pie(by_cat, names='category', values='total_loss', title='Loss by category', hole=0.45), width='stretch')
    st.dataframe(df, width='stretch', hide_index=True)
    st.caption('Loss = units x (cost price - price after discount). It is calculated before returns.')


# ------------------------------------------------------------------ page 5: data quality
def page_quality():
    st.title('Data quality - what cleaning did')
    counts = pd.read_csv(k.BASE / 'before_after_counts.csv')
    rejects = pd.read_csv(k.BASE / 'silver' / 'rejects.csv')

    a, b, c = st.columns(3)
    a.metric('Raw rows', int(counts.raw_rows.sum()))
    b.metric('Clean rows', int(counts.silver_rows.sum()))
    c.metric('Rows removed / quarantined', int(counts.raw_rows.sum() - counts.silver_rows.sum()))

    long = counts.melt(id_vars='table', value_vars=['raw_rows', 'silver_rows'], var_name='stage', value_name='rows')
    fig = px.bar(long, x='table', y='rows', color='stage', barmode='group', title='Rows before and after cleaning')
    st.plotly_chart(fig, width='stretch')

    st.subheader('Why rows were removed or flagged')
    reasons = rejects.groupby(['reason', 'action']).size().reset_index(name='rows').sort_values('rows', ascending=False)
    left, right = st.columns(2)
    fig = px.bar(reasons, x='rows', y='reason', color='action', orientation='h')
    fig.update_layout(yaxis_title='')
    left.plotly_chart(fig, width='stretch')
    right.dataframe(reasons, width='stretch', hide_index=True)

    st.subheader('Before / after table')
    st.dataframe(counts, width='stretch', hide_index=True)

    st.subheader('Main cleaning decisions')
    st.markdown(
        "- **Labels** made consistent (segment, city, status, channel, category) and typos fixed.\n"
        "- **Dates** in 3 formats read into one. Dates like 03/04/2024 are read as MM/DD and flagged as *ambiguous*.\n"
        "- **Amounts**: currency symbols and commas removed. `$` amounts were **not** converted (they match INR order totals).\n"
        "- **line_total** was wrong on 50 rows, so it was recomputed as quantity x price x (1 - discount).\n"
        "- **Duplicates** dropped; **orphan rows** (child with no parent) quarantined in the rejects file.\n"
        "- **Orders with unknown customer** (15) kept and flagged, because the revenue is real.\n"
        "- **Supplier ratings** above 5 were on a 0-10 scale and were halved.")


# ------------------------------------------------------------------ page 6: pipeline
def page_pipeline():
    st.title('Pipeline and assumptions')
    st.markdown("""
| Step | What happens | Where |
|---|---|---|
| 1. Clean | raw files -> clean tables + rejects | `02_clean.py` |
| 2. Check silver | keys unique, no broken links, no impossible values | `04_pipeline.py` |
| 3. Build KPIs | SQL queries run on `silver.db` | `sql/*.sql`, `kpi_lib.py` |
| 4. Check KPIs | totals tie together, row counts as expected | `04_pipeline.py` |
| 5. Dashboard | reads the KPI result files | `dashboard.py` |
""")
    st.subheader('Assumptions')
    st.markdown(
        "- Revenue orders = **Completed + Returned**. Cancelled and Pending are not revenue.\n"
        "- Only **Approved** returns reduce revenue; refund counted in the **order** month (return dates are unreliable).\n"
        "- A return means the **whole order line** was returned (the returns table has no quantity).\n"
        "- Customer KPIs exclude the 15 orders whose customer is not in the customer table.\n"
        "- Repeat purchase window = **90 days**.")

    st.subheader('Last pipeline run')
    log = k.BASE / 'pipeline.log'
    if log.exists():
        st.code(log.read_text(encoding='utf-8'), language='text')
    else:
        st.warning('pipeline.log not found. Run: python 04_pipeline.py')


# ------------------------------------------------------------------ EDA page
def page_eda():
    st.title('Exploratory Data Analysis')
    st.caption('Four basic views built from the cleaned silver tables.')

    customers = load_csv(k.BASE / 'silver' / 'customers.csv')
    orders = load_csv(k.BASE / 'silver' / 'orders.csv')
    items = load_csv(k.BASE / 'silver' / 'order_items.csv')
    products = load_csv(k.BASE / 'silver' / 'products.csv')
    returns = load_csv(k.BASE / 'silver' / 'returns.csv')

    orders['order_date'] = pd.to_datetime(orders['order_date'], errors='coerce')

    st.subheader('Orders by status')
    status_counts = (orders['order_status'].value_counts()
                     .rename_axis('Order status').reset_index(name='Orders'))
    fig = px.bar(status_counts, x='Order status', y='Orders', color='Order status',
                 title='Orders by status', text='Orders')
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width='stretch')

    approved_refunds = (returns.loc[returns['return_status'].eq('Approved')]
                        .groupby('order_item_id', as_index=False)['refund_amount'].sum())
    sales = (items.merge(orders[['order_id', 'order_status', 'order_date']], on='order_id')
             .loc[lambda df: df['order_status'].isin(['Completed', 'Returned'])]
             .merge(products[['product_id', 'category']], on='product_id')
             .merge(approved_refunds, on='order_item_id', how='left'))
    sales['refund_amount'] = sales['refund_amount'].fillna(0).clip(upper=sales['line_total'])
    sales['net_revenue'] = sales['line_total'] - sales['refund_amount']

    left, right = st.columns(2)
    with left:
        st.subheader('Net revenue by category')
        category_sales = (sales.groupby('category', as_index=False)['net_revenue'].sum()
                          .sort_values('net_revenue', ascending=False))
        fig = px.bar(category_sales, x='category', y='net_revenue', color='category',
                     title='Net revenue by category')
        fig.update_layout(showlegend=False, xaxis_title='', yaxis_title='Net revenue')
        st.plotly_chart(fig, width='stretch')

    with right:
        st.subheader('Customers by segment')
        segment_counts = (customers['customer_segment'].fillna('Unknown').value_counts()
                          .rename_axis('Segment').reset_index(name='Customers'))
        fig = px.pie(segment_counts, names='Segment', values='Customers', hole=0.4,
                     title='Customer segment mix')
        st.plotly_chart(fig, width='stretch')

    st.subheader('Monthly net revenue by category')
    sales['order_month'] = sales['order_date'].dt.to_period('M').astype(str)
    monthly_sales = sales.groupby(['order_month', 'category'], as_index=False)['net_revenue'].sum()
    fig = px.line(monthly_sales, x='order_month', y='net_revenue', color='category', markers=True,
                  title='Monthly net revenue by category')
    fig.update_layout(xaxis_title='Order month', yaxis_title='Net revenue')
    st.plotly_chart(fig, width='stretch')


# ------------------------------------------------------------------ menu
PAGES = {
    'Overview': page_overview,
    'EDA - Exploratory analysis': page_eda,
    'KPI 1 - Revenue by category': page_revenue,
    'Customers (KPI 2, 3, 7)': page_customers,
    'Stretch - Margin risk': page_margin,
    'Data quality': page_quality,
    'Pipeline and assumptions': page_pipeline,
}

st.sidebar.title('ShopSphere')
choice = st.sidebar.radio('Go to', list(PAGES))
st.sidebar.caption('Data comes from kpi_outputs/ (made by 04_pipeline.py)')

if not (k.OUT_DIR / 'kpi_01_net_revenue_by_category_month.csv').exists():
    st.error('KPI files not found. Run  python 04_pipeline.py  first.')
else:
    PAGES[choice]()
