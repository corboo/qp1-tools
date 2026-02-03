"""
Spreaker Analytics Dashboard
Shows podcast analytics and revenue stats.
"""

import streamlit as st
import pandas as pd
import urllib.request
import json
from collections import defaultdict
from datetime import datetime
import time
import os

# ============================================================================
# Configuration
# ============================================================================

st.set_page_config(
    page_title="Spreaker Dashboard",
    page_icon="📊",
    layout="wide"
)

# Google Sheet URL (public export)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1sNGZ03EeEtqqR4qgNmCpXgc4XebtUtjqCkctiax-uoA/export?format=csv"

# Spreaker API
SPREAKER_API_KEY = "c5e07e8373932ea7d0276c77f73837c768b83c98"

# Stats data file
STATS_FILE = os.path.join(os.path.dirname(__file__), "data", "spreaker_stats.json")

# ============================================================================
# Data Loading Functions
# ============================================================================

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_stats():
    """Load scraped stats from JSON file."""
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except:
        return None

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_sheet_data():
    """Load data from Google Sheet."""
    df = pd.read_csv(SHEET_URL)
    # Clean up numeric columns
    for col in ['Lifetime Downloads', 'Recent 30-Day Downloads']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(',', '').astype(float)
    # Clean up percentage column
    if 'Activity Percentile' in df.columns:
        df['Activity Percentile'] = df['Activity Percentile'].astype(str).str.replace('%', '').astype(float) / 100
    return df

@st.cache_data(ttl=3600)
def fetch_spreaker_category(show_id):
    """Fetch category for a single show from Spreaker API."""
    url = f"https://api.spreaker.com/v2/shows/{show_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {SPREAKER_API_KEY}")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            show = data["response"]["show"]
            cat = show.get("category", {})
            return {
                "category_name": cat.get("name", "Uncategorized"),
                "category_id": cat.get("category_id"),
                "category_2": show.get("category_2", {}).get("name") if show.get("category_2") else None,
                "category_3": show.get("category_3", {}).get("name") if show.get("category_3") else None,
            }
    except Exception as e:
        return {"category_name": "Unknown", "category_id": None, "category_2": None, "category_3": None}

# ============================================================================
# Revenue & Stats Tab
# ============================================================================

def show_stats_tab():
    """Display revenue and stats overview."""
    st.header("💰 Revenue & Performance")
    
    stats = load_stats()
    
    if not stats:
        st.error("Stats data not found. Run the scraper to update.")
        return
    
    # Last updated
    updated = stats.get('last_updated', 'Unknown')
    st.caption(f"Last updated: {updated}")
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        downloads = stats['downloads']['last_30_days']
        change = stats['downloads']['change_pct']
        st.metric(
            "📥 Downloads (30d)", 
            f"{downloads:,}", 
            f"{change:+d}%" if change else None
        )
    
    with col2:
        impressions = stats['ad_exchange']['impressions']
        change = stats['ad_exchange']['impressions_change_pct']
        st.metric(
            "👁️ Ad Impressions (30d)", 
            f"{impressions:,}", 
            f"{change:+d}%"
        )
    
    with col3:
        revenue = stats['ad_exchange']['revenue_usd']
        change = stats['ad_exchange']['revenue_change_pct']
        st.metric(
            "💵 Ad Revenue (30d)", 
            f"${revenue:,.2f}", 
            f"{change:+d}%"
        )
    
    with col4:
        total_shows = stats['organization']['total_shows']
        total_eps = stats['organization']['total_episodes']
        st.metric("🎙️ Shows / Episodes", f"{total_shows:,} / {total_eps:,}")
    
    st.divider()
    
    # Revenue breakdown
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Revenue by Account (30d)")
        accounts = stats.get('accounts', [])
        if accounts:
            df_accounts = pd.DataFrame(accounts)
            df_accounts = df_accounts.sort_values('revenue', ascending=False)
            
            # Bar chart
            chart_data = df_accounts.set_index('name')['revenue'].head(10)
            st.bar_chart(chart_data)
            
            # Table
            st.dataframe(
                df_accounts.style.format({
                    'impressions': '{:,.0f}',
                    'revenue': '${:,.2f}'
                }),
                use_container_width=True,
                hide_index=True
            )
    
    with col2:
        st.subheader("📈 Payment History")
        payments = stats.get('payment_history', [])
        if payments:
            df_payments = pd.DataFrame(payments)
            
            # Calculate yearly totals
            df_payments['year'] = df_payments['month'].apply(lambda x: x.split('-')[0] if '-' in str(x) else '2023')
            yearly = df_payments.groupby('year')['amount'].sum().sort_index(ascending=False)
            
            # Show yearly summary
            for year, total in yearly.items():
                st.metric(f"💰 {year} Total", f"${total:,.2f}")
            
            # Chart
            df_chart = df_payments.copy()
            df_chart = df_chart[~df_chart['month'].str.contains('/')].head(12)  # Skip combined months
            df_chart['month_short'] = df_chart['month'].apply(lambda x: x[5:7] + '/' + x[2:4] if len(x) >= 7 else x)
            
            chart_data = df_chart.set_index('month_short')['amount'].iloc[::-1]  # Reverse for chronological
            st.line_chart(chart_data)
            
            # Table
            st.dataframe(
                df_payments[['month', 'amount', 'status', 'paid_date']].head(12).style.format({
                    'amount': '${:,.2f}'
                }),
                use_container_width=True,
                hide_index=True
            )

# ============================================================================
# Analytics Tab
# ============================================================================

def show_analytics_tab():
    """Display podcast analytics by category."""
    st.header("📊 Podcast Analytics")
    
    # Load data
    with st.spinner("Loading sheet data..."):
        df = load_sheet_data()
    
    st.success(f"Loaded **{len(df):,}** podcasts from sheet")
    
    # Sidebar filters
    with st.sidebar:
        st.header("🎛️ Filters")
        
        # Activity filter
        show_active_only = st.checkbox("Active podcasts only (Top 25%)", value=False)
        
        # Download threshold
        min_downloads = st.slider(
            "Minimum 30-day downloads",
            min_value=0,
            max_value=1000,
            value=0,
            step=10
        )
        
        st.divider()
        
        # Category enrichment
        st.header("📂 Category Data")
        
        if st.button("🔄 Fetch Spreaker Categories"):
            with st.spinner("Fetching categories..."):
                progress = st.progress(0)
                status = st.empty()
                
                show_ids = df['Podcast ID'].tolist()[:500]  # Limit for speed
                categories = {}
                
                for i, show_id in enumerate(show_ids):
                    if i % 50 == 0:
                        progress.progress(i / len(show_ids))
                        status.text(f"Fetching {i}/{len(show_ids)}...")
                    categories[show_id] = fetch_spreaker_category(show_id)
                    time.sleep(0.02)
                
                progress.progress(1.0)
                status.text("Done!")
                st.session_state['categories'] = categories
                st.rerun()
    
    # Apply filters
    filtered_df = df.copy()
    
    if show_active_only and 'Active (Top 25%)' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Active (Top 25%)'] == True]
    
    if 'Recent 30-Day Downloads' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Recent 30-Day Downloads'] >= min_downloads]
    
    st.info(f"Showing **{len(filtered_df):,}** podcasts after filters")
    
    # Show category analysis or preview
    if 'categories' in st.session_state:
        categories = st.session_state['categories']
        filtered_df['Spreaker Category'] = filtered_df['Podcast ID'].map(
            lambda x: categories.get(x, {}).get('category_name', 'Unknown')
        )
        
        # Category breakdown
        cat_stats = filtered_df.groupby('Spreaker Category').agg({
            'Podcast ID': 'count',
            'Lifetime Downloads': 'sum',
            'Recent 30-Day Downloads': 'sum'
        }).rename(columns={
            'Podcast ID': 'Shows',
            'Lifetime Downloads': 'Lifetime DLs',
            'Recent 30-Day Downloads': '30-Day DLs'
        })
        
        cat_stats['Avg DLs/Show'] = (cat_stats['30-Day DLs'] / cat_stats['Shows']).round(0)
        cat_stats = cat_stats.sort_values('30-Day DLs', ascending=False)
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.bar_chart(cat_stats['30-Day DLs'].head(15))
        
        with col2:
            st.dataframe(
                cat_stats.head(15).style.format({
                    'Shows': '{:,.0f}',
                    'Lifetime DLs': '{:,.0f}',
                    '30-Day DLs': '{:,.0f}',
                    'Avg DLs/Show': '{:,.0f}'
                }),
                use_container_width=True
            )
    else:
        st.warning("👆 Click **'Fetch Spreaker Categories'** in the sidebar to load category data")
        
        if 'Primary Bundle' in df.columns:
            bundle_stats = filtered_df.groupby('Primary Bundle').agg({
                'Podcast ID': 'count',
                'Recent 30-Day Downloads': 'sum'
            }).rename(columns={
                'Podcast ID': 'Shows',
                'Recent 30-Day Downloads': '30-Day DLs'
            }).sort_values('30-Day DLs', ascending=False)
            
            st.dataframe(bundle_stats, use_container_width=True)
    
    # Download button
    csv = filtered_df.to_csv(index=False)
    st.download_button("📥 Download Data", csv, "spreaker_analytics.csv", "text/csv")

# ============================================================================
# Main App
# ============================================================================

def main():
    st.title("📊 QP-1 Spreaker Dashboard")
    
    # Tabs
    tab1, tab2 = st.tabs(["💰 Revenue & Stats", "📈 Podcast Analytics"])
    
    with tab1:
        show_stats_tab()
    
    with tab2:
        show_analytics_tab()

if __name__ == "__main__":
    main()
