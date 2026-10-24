"""Simple ShopSphere dashboard with Overview and KPI 1 pages."""
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import streamlit as st

PROJECT = Path(__file__).resolve().parent
RESULTS = PROJECT / "kpi_outputs"
revenue = pd.read_csv(RESULTS / "kpi_01_net_revenue_by_category_month.csv")
segments = pd.read_csv(RESULTS / "kpi_03_segment_profile.csv")
customer_ltv = pd.read_csv(RESULTS / "kpi_02_top10_customers_ltv.csv")
repeat = pd.read_csv(RESULTS / "kpi_07_repeat_purchase_rate.csv")
product_returns = pd.read_csv(RESULTS / "kpi_05_product_return_rate.csv")
repeat_detail = pd.read_csv(RESULTS / "kpi_07_repeat_purchase_detail.csv")

st.set_page_config(page_title="ShopSphere Overview", page_icon="📊", layout="wide")


def show_overview():
    st.title("ShopSphere — E-Commerce Overview")

    st.subheader("Case study")
    st.write(
        "The business has online-store information spread across several files. "
        "The goal is to organize that information and present useful business results "
        "so people can understand sales and customer activity."
    )

    st.subheader("What the datasets contain")
    left, right = st.columns(2)
    left.markdown(
        "- **Customers:** customer details and segment\n"
        "- **Orders:** order date, status, and sales channel\n"
        "- **Order items:** products, quantities, and prices in each order\n"
        "- **Products:** product names, categories, and prices"
    )
    right.markdown(
        "- **Payments:** payment records linked to orders\n"
        "- **Returns:** returned items and refund details\n"
        "- **Suppliers:** businesses that provide the products"
    )

    st.subheader("Why the data needed preparation")
    st.write(
        "The source files contained duplicate rows, inconsistent names and labels, "
        "missing values, mixed date formats, and some incorrect line totals. "
        "Preparing the data made the results more consistent and easier to interpret."
    )

    st.subheader("Business overview")
    net_revenue = revenue["net_revenue"].sum()
    refunds = revenue["approved_refunds"].sum()
    customer_count = segments["customers"].sum()
    repeat_rate = repeat.loc[0, "repeat_rate_pct"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net revenue", f"₹{net_revenue:,.0f}")
    c2.metric("Approved refunds", f"₹{refunds:,.0f}")
    c3.metric("Customers", f"{customer_count:,.0f}")
    c4.metric("Repeat purchase rate", f"{repeat_rate:.2f}%")

    revenue_by_category = revenue.groupby("category", as_index=False)["net_revenue"].sum()
    customers_by_segment = segments[["segment", "customers"]]
    left, right = st.columns(2)
    left.subheader("Revenue by product category")
    left.bar_chart(revenue_by_category, x="category", y="net_revenue")
    right.subheader("Customers by segment")
    right.bar_chart(customers_by_segment, x="segment", y="customers")

    st.info(
        "Panel summary: This project brings customer, order, product, payment, return, "
        "and supplier information together to make store performance easier to understand."
    )


def show_kpi1():
    st.title("KPI 1 — Revenue by category and month")

    st.subheader("Problem statement")
    st.write("How much revenue did each product category generate each month after approved refunds?")

    total_net_revenue = revenue["net_revenue"].sum()
    total_refunds = revenue["approved_refunds"].sum()
    col1, col2 = st.columns(2)
    col1.metric("Net revenue", f"₹{total_net_revenue:,.0f}")
    col2.metric("Approved refunds", f"₹{total_refunds:,.0f}")

    st.subheader("Output: total net revenue by category")
    category_revenue = revenue.groupby("category", as_index=False)["net_revenue"].sum()
    st.bar_chart(category_revenue, x="category", y="net_revenue")

    st.subheader("Monthly output")
    st.dataframe(
        revenue[["order_month", "category", "gross_revenue", "net_revenue"]],
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Simple method")
    st.write(
        "Start with sales from Completed and Returned orders. Subtract approved refunds, "
        "then group the result by product category and order month."
    )
    st.info("Net revenue = sales − approved refunds. Refunds are counted in the order month.")


def show_kpi2():
    st.title("KPI 2 — Top customers by lifetime value")

    st.subheader("Problem statement")
    st.write("Which customers have generated the highest net value for the business?")

    st.subheader("Output: top 10 customers")
    top_customers = customer_ltv[["customer_id", "customer_name", "net_lifetime_value"]]
    st.bar_chart(top_customers, x="customer_name", y="net_lifetime_value")
    st.dataframe(top_customers, hide_index=True, use_container_width=True)

    st.subheader("Simple method")
    st.write(
        "For each known customer, add the value of their Completed orders, "
        "subtract approved refunds, and rank customers from highest value to lowest."
    )
    st.info("Net lifetime value = completed-order value − approved refunds.")


def show_kpi3():
    st.title("KPI 3 — Customer segment profile")

    st.subheader("Problem statement")
    st.write("How many customers belong to each segment, and what is the average completed-order value for each segment?")

    st.subheader("Output by customer segment")
    segment_output = segments[["segment", "customers", "avg_order_value"]].rename(columns={
        "segment": "Customer segment",
        "customers": "Customer count",
        "avg_order_value": "Average order value (₹)",
    })
    st.bar_chart(segment_output, x="Customer segment", y="Average order value (₹)")
    st.dataframe(segment_output, hide_index=True, use_container_width=True)

    st.subheader("Simple method")
    st.write(
        "Group customers and Completed orders by customer segment. Count the customers, "
        "then divide the segment's total completed-order value by its number of Completed orders."
    )
    st.info("Average order value = completed-order value ÷ Completed orders.")



def show_kpi5():
    st.title("KPI 5 — Product return rate")

    st.subheader("Problem statement")
    st.write("Which products have the highest and lowest return rates?")

    st.subheader("Output")
    list_choice = st.selectbox(
        "Choose products to view",
        ["Top 10 - highest return rate", "Bottom 10 - lowest return rate"],
    )
    output = product_returns.loc[
        product_returns["list_name"] == list_choice,
        ["rank_no", "product_id", "product_name", "category", "ordered_qty", "returned_qty", "return_rate_pct"],
    ].rename(columns={
        "rank_no": "Rank",
        "product_id": "Product ID",
        "product_name": "Product name",
        "category": "Category",
        "ordered_qty": "Units ordered",
        "returned_qty": "Units returned",
        "return_rate_pct": "Return rate (%)",
    })
    st.dataframe(output, hide_index=True, use_container_width=True)

    st.subheader("Simple method")
    st.write("For products with enough sales to make comparison useful, divide returned units by ordered units and rank the results.")
    st.info("Return rate = returned units ÷ ordered units × 100. This KPI uses a minimum sales volume of 18 units.")


def show_kpi7():
    st.title("KPI 7 — Repeat purchase rate")

    st.subheader("Problem statement")
    st.write("What share of customers placed a second Completed order within 90 days of their first Completed order?")

    st.subheader("Output")
    customers_count = int(repeat.loc[0, "customers_with_completed_order"])
    repeat_count = int(repeat.loc[0, "repeat_customers"])
    rate = float(repeat.loc[0, "repeat_rate_pct"])
    ambiguous_count = int(repeat.loc[0, "repeat_customers_with_ambiguous_dates"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Customers with Completed orders", f"{customers_count}")
    col2.metric("Repeat customers within 90 days", f"{repeat_count}")
    col3.metric("Repeat purchase rate", f"{rate:.2f}%")

    detail = repeat_detail[[
        "customer_id", "first_order_date", "second_order_date",
        "days_to_second_order", "is_repeat_within_window",
    ]].rename(columns={
        "customer_id": "Customer ID",
        "first_order_date": "First order date",
        "second_order_date": "Second order date",
        "days_to_second_order": "Days to second order",
        "is_repeat_within_window": "Repeat within 90 days (1 = yes)",
    })
    st.dataframe(detail, hide_index=True, use_container_width=True)
    st.caption(f"{ambiguous_count} repeat customers have a date flagged as ambiguous in the source data.")

    st.subheader("Simple method")
    st.write("For each customer, find their first two Completed orders. Count customers whose second order was within 90 days, then divide by all customers with a Completed order.")
    st.info("Repeat purchase rate = repeat customers within 90 days ÷ customers with Completed orders × 100.")


def show_eda_statistics():
    st.title("EDA and Statistics")
    st.write("This section follows eda5.ipynb only: customer distributions, product price comparisons, and its statistical tests.")

    customers = pd.read_csv(PROJECT / "silver" / "customers.csv")
    products = pd.read_csv(PROJECT / "silver" / "products.csv")

    st.header("Customer data overview")
    for column in ["customer_segment", "city", "state", "is_active"]:
        counts = customers[column].value_counts().rename_axis(column).reset_index(name="Count")
        st.subheader(f"Distribution of {column}")
        st.bar_chart(counts, x=column, y="Count")

    st.header("Product prices by active status")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    products.boxplot(column="unit_price", by="is_active", ax=axes[0])
    axes[0].set_title("Active Status vs Unit Price")
    axes[0].set_xlabel("Active status")
    axes[0].set_ylabel("Unit price")
    products.boxplot(column="cost_price", by="is_active", ax=axes[1])
    axes[1].set_title("Active Status vs Cost Price")
    axes[1].set_xlabel("Active status")
    axes[1].set_ylabel("Cost price")
    fig.suptitle("")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    st.header("Statistical tests from eda5.ipynb")
    st.subheader("Test assumptions")
    st.markdown(
        """
        Before interpreting the tests, keep these assumptions in mind:

        1. **Independent observations:** Each customer or product should appear as an independent observation in its analysis.
        2. **Normality for the price comparison:** Unit-price values in each active-status group should be approximately normal. Shapiro-Wilk checks this; p > 0.05 means there is not enough evidence to call the group non-normal.
        3. **Variance check:** Levene's test checks whether group variances are similar. This comparison uses Welch's t-test, which does not require equal variances.
        4. **Categorical data for chi-square:** Customer segment and city, state, or active status must be categorical. Expected counts should generally be at least 5 for the chi-square approximation to be reliable.
        5. **Significance level:** Use α = 0.05. If p < 0.05, reject the null hypothesis; if p ≥ 0.05, fail to reject it.

        **Conclusion:** These tests assess associations in this dataset. They do not prove cause and effect or establish a churn cause.
        """
    )
    st.subheader("Chi-square tests: customer segment relationships")
    st.write("These tests check whether customer segment is associated with city, state, or active status.")
    chi_results = []
    for column in ["city", "state", "is_active"]:
        table = pd.crosstab(customers[column], customers["customer_segment"])
        chi2, p_value, dof, expected = stats.chi2_contingency(table)
        chi_results.append({
            "Comparison": f"Customer segment vs {column}",
            "Chi-square": round(chi2, 2),
            "p-value": round(p_value, 4),
            "Conclusion at 0.05": "Association detected" if p_value < 0.05 else "No significant association detected",
        })
    st.dataframe(pd.DataFrame(chi_results), hide_index=True, use_container_width=True)
    st.caption("A p-value below 0.05 indicates evidence of an association. These tests do not prove cause and effect.")

    st.subheader("Unit price: active vs inactive products")
    products["unit_price"] = pd.to_numeric(products["unit_price"], errors="coerce")
    active_prices = products.loc[products["is_active"] == True, "unit_price"].dropna()
    inactive_prices = products.loc[products["is_active"] == False, "unit_price"].dropna()
    st.write(f"Products in groups: {len(active_prices)} active and {len(inactive_prices)} inactive.")

    if len(active_prices) >= 3 and len(inactive_prices) >= 3:
        active_normality = stats.shapiro(active_prices)
        inactive_normality = stats.shapiro(inactive_prices)
        variance_test = stats.levene(active_prices, inactive_prices)
        price_test = stats.ttest_ind(active_prices, inactive_prices, equal_var=False)

        st.write(f"Shapiro-Wilk p-values — active: {active_normality.pvalue:.4f}; inactive: {inactive_normality.pvalue:.4f}")
        st.write(f"Levene test p-value: {variance_test.pvalue:.4f}")
        st.write(f"Welch t-test — t-statistic: {price_test.statistic:.4f}; p-value: {price_test.pvalue:.4f}")
        if price_test.pvalue < 0.05:
            st.info("The data shows a statistically significant difference in average unit price between active and inactive products. This does not show that active status causes the difference.")
        else:
            st.info("The data does not show a statistically significant difference in average unit price between active and inactive products.")
        st.caption("Shapiro-Wilk checks normality and Levene checks whether group variances differ. The Welch t-test compares the group averages without assuming equal variances. Interpret carefully when one group is small.")
    else:
        st.warning("There are too few products in one status group to run the Shapiro-Wilk, Levene, and Welch t-tests reliably.")


page = st.sidebar.radio("Go to", ["Overview", "KPI 1 — Revenue by category", "KPI 2 — Top customers", "KPI 3 — Segments", "KPI 5 — Product returns", "KPI 7 — Repeat purchases", "EDA and Statistics"])
if page == "Overview":
    show_overview()
elif page == "KPI 1 — Revenue by category":
    show_kpi1()
elif page == "KPI 2 — Top customers":
    show_kpi2()
elif page == "KPI 3 — Segments":
    show_kpi3()
elif page == "KPI 5 — Product returns":
    show_kpi5()
elif page == "KPI 7 — Repeat purchases":
    show_kpi7()
else:
    show_eda_statistics()

