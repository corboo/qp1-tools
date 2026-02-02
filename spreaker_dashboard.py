"""
Spreaker Analytics Dashboard
Shows podcast analytics by Spreaker categories.
"""

import streamlit as st
import pandas as pd
import urllib.request
import json
from collections import defaultdict
import time

# ============================================================================
# Configuration
# ============================================================================

st.set_page_config(
    page_title="Spreaker Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

# Google Sheet URL (public export)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1sNGZ03EeEtqqR4qgNmCpXgc4XebtUtjqCkctiax-uoA/export?format=csv"

# Spreaker API
SPREAKER_API_KEY = "c5e07e8373932ea7d0276c77f73837c768b83c98"

# ============================================================================
# Data Loading Functions
# ============================================================================

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

@st.cache_data(ttl=3600, show_spinner=False)
def enrich_with_categories(show_ids):
    """Fetch Spreaker categories for a list of show IDs."""
    categories = {}
    for show_id in show_ids:
        categories[show_id] = fetch_spreaker_category(show_id)
    return categories

# ============================================================================
# Dashboard
# ============================================================================

def main():
    st.title("📊 Spreaker Analytics Dashboard")
    st.markdown("Podcast performance by **actual Spreaker categories**")
    
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
        
        if st.button("🔄 Fetch Spreaker Categories", help="This fetches real categories from Spreaker API"):
            with st.spinner("Fetching categories (this may take a few minutes)..."):
                progress = st.progress(0)
                status = st.empty()
                
                show_ids = df['Podcast ID'].tolist()
                categories = {}
                
                for i, show_id in enumerate(show_ids):
                    if i % 50 == 0:
                        progress.progress(i / len(show_ids))
                        status.text(f"Fetching {i}/{len(show_ids)}...")
                    categories[show_id] = fetch_spreaker_category(show_id)
                    time.sleep(0.05)  # Rate limiting
                
                progress.progress(1.0)
                status.text("Done!")
                
                # Store in session state
                st.session_state['categories'] = categories
                st.rerun()
    
    # Apply filters
    filtered_df = df.copy()
    
    if show_active_only and 'Active (Top 25%)' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Active (Top 25%)'] == True]
    
    if 'Recent 30-Day Downloads' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Recent 30-Day Downloads'] >= min_downloads]
    
    st.info(f"Showing **{len(filtered_df):,}** podcasts after filters")
    
    # Check if we have category data
    if 'categories' in st.session_state:
        categories = st.session_state['categories']
        
        # Add category columns to dataframe
        filtered_df['Spreaker Category'] = filtered_df['Podcast ID'].map(
            lambda x: categories.get(x, {}).get('category_name', 'Unknown')
        )
        filtered_df['Subcategory 1'] = filtered_df['Podcast ID'].map(
            lambda x: categories.get(x, {}).get('category_2', '')
        )
        filtered_df['Subcategory 2'] = filtered_df['Podcast ID'].map(
            lambda x: categories.get(x, {}).get('category_3', '')
        )
        
        # Main metrics row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Shows", f"{len(filtered_df):,}")
        with col2:
            total_downloads = filtered_df['Lifetime Downloads'].sum()
            st.metric("Total Lifetime Downloads", f"{total_downloads:,.0f}")
        with col3:
            recent_downloads = filtered_df['Recent 30-Day Downloads'].sum()
            st.metric("30-Day Downloads", f"{recent_downloads:,.0f}")
        with col4:
            num_categories = filtered_df['Spreaker Category'].nunique()
            st.metric("Categories", num_categories)
        
        st.divider()
        
        # Category breakdown
        st.header("📊 Performance by Spreaker Category")
        
        # Aggregate by category
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
        
        # Display options
        view_mode = st.radio(
            "Sort by:",
            ["30-Day Downloads", "Show Count", "Avg Downloads/Show"],
            horizontal=True
        )
        
        sort_col = {
            "30-Day Downloads": "30-Day DLs",
            "Show Count": "Shows",
            "Avg Downloads/Show": "Avg DLs/Show"
        }[view_mode]
        
        cat_stats = cat_stats.sort_values(sort_col, ascending=False)
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Bar chart
            st.bar_chart(cat_stats[sort_col].head(20))
        
        with col2:
            # Top categories table
            st.dataframe(
                cat_stats.head(20).style.format({
                    'Shows': '{:,.0f}',
                    'Lifetime DLs': '{:,.0f}',
                    '30-Day DLs': '{:,.0f}',
                    'Avg DLs/Show': '{:,.0f}'
                }),
                use_container_width=True
            )
        
        st.divider()
        
        # Category deep dive
        st.header("🔍 Category Deep Dive")
        
        selected_category = st.selectbox(
            "Select a category to explore:",
            options=['All'] + sorted(filtered_df['Spreaker Category'].unique().tolist())
        )
        
        if selected_category != 'All':
            cat_df = filtered_df[filtered_df['Spreaker Category'] == selected_category]
        else:
            cat_df = filtered_df
        
        # Show top podcasts in category
        st.subheader(f"Top Podcasts in {selected_category}")
        
        display_df = cat_df.nlargest(20, 'Recent 30-Day Downloads')[[
            'Podcast Title', 'Spreaker Category', 'Recent 30-Day Downloads', 
            'Lifetime Downloads', 'Activity Percentile'
        ]]
        
        st.dataframe(
            display_df.style.format({
                'Recent 30-Day Downloads': '{:,.0f}',
                'Lifetime Downloads': '{:,.0f}',
                'Activity Percentile': '{:.1%}'
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # Download full data
        st.divider()
        
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            "📥 Download Full Data (CSV)",
            csv,
            "spreaker_analytics.csv",
            "text/csv",
            use_container_width=True
        )
    
    else:
        # No category data yet
        st.warning("👆 Click **'Fetch Spreaker Categories'** in the sidebar to load real category data from Spreaker API")
        
        # Show preview with existing bundle data
        st.header("📋 Current Data (using 'Primary Bundle')")
        
        if 'Primary Bundle' in df.columns:
            bundle_stats = filtered_df.groupby('Primary Bundle').agg({
                'Podcast ID': 'count',
                'Lifetime Downloads': 'sum',
                'Recent 30-Day Downloads': 'sum'
            }).rename(columns={
                'Podcast ID': 'Shows',
                'Lifetime Downloads': 'Lifetime DLs',
                'Recent 30-Day Downloads': '30-Day DLs'
            }).sort_values('30-Day DLs', ascending=False)
            
            st.dataframe(
                bundle_stats.style.format({
                    'Shows': '{:,.0f}',
                    'Lifetime DLs': '{:,.0f}',
                    '30-Day DLs': '{:,.0f}'
                }),
                use_container_width=True
            )
        
        # Preview table
        st.subheader("📄 Data Preview")
        st.dataframe(filtered_df.head(100), use_container_width=True)

if __name__ == "__main__":
    main()
