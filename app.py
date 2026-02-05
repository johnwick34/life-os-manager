import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time, date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="My Routine OS", page_icon="☁️", layout="wide")

# --- CONFIGURATION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1fYu8ws8PZF-36oseUNXvcoT_zO0xVfYbL6vScYWbhdk/edit"

# --- TIMEZONE HANDLER (BANGLADESH) ---
def get_bd_time():
    """Returns the current time in Bangladesh (UTC+6)"""
    return datetime.utcnow() + timedelta(hours=6)

def get_bd_date():
    """Returns the current date in Bangladesh"""
    return get_bd_time().date()

# --- GOOGLE SHEETS CONNECTION HANDLER ---
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    if os.path.exists('service_account.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
    else:
        try:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except:
            st.error("🚨 Authentication Error: Could not find 'service_account.json' locally, and no Secrets found on Cloud.")
            st.stop()
        
    client = gspread.authorize(creds)
    return client

def init_sheets():
    client = get_google_sheet_client()
    sheet = client.open_by_url(SHEET_URL)
    
    try:
        ws_tasks = sheet.worksheet("Tasks")
    except:
        ws_tasks = sheet.add_worksheet(title="Tasks", rows=1000, cols=10)
        ws_tasks.append_row(["Task", "Category", "Location", "Date", "StartTime", "Duration", "Priority", "Status", "Notes"])
        
    try:
        ws_travel = sheet.worksheet("Travel")
    except:
        ws_travel = sheet.add_worksheet(title="Travel", rows=1000, cols=6)
        ws_travel.append_row(["Date", "From", "To", "DistanceKM", "Mode"])
        
    return sheet

def load_data(worksheet_name):
    try:
        sheet = init_sheets()
        worksheet = sheet.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        expected_cols = ["Task", "Category", "Location", "Date", "StartTime", "Duration", "Priority", "Status", "Notes"]
        if worksheet_name == "Tasks":
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = pd.Series(dtype='object')

        if not df.empty and 'Date' in df.columns:
            df = df[df['Date'] != ''] 
            df['Date'] = pd.to_datetime(df['Date']).dt.date
            
        return df
    except Exception as e:
        return pd.DataFrame(columns=["Task", "Category", "Location", "Date", "StartTime", "Duration", "Priority", "Status", "Notes"])

def save_entry(worksheet_name, entry_dict):
    sheet = init_sheets()
    worksheet = sheet.worksheet(worksheet_name)
    
    row_values = list(entry_dict.values())
    row_values_str = [str(x) if isinstance(x, (datetime, date, time)) else x for x in row_values]
    
    worksheet.append_row(row_values_str)

def bulk_save_entries(worksheet_name, list_of_dicts):
    sheet = init_sheets()
    worksheet = sheet.worksheet(worksheet_name)
    
    rows_to_add = []
    for entry in list_of_dicts:
        row = [str(x) if isinstance(x, (datetime, date, time)) else x for x in entry.values()]
        rows_to_add.append(row)
        
    worksheet.append_rows(rows_to_add)

def update_status_in_sheet(task_name, date_str, new_status):
    sheet = init_sheets()
    ws = sheet.worksheet("Tasks")
    try:
        cell_list = ws.findall(task_name)
        for cell in cell_list:
            # Column 4 is Date
            date_cell = ws.cell(cell.row, 4) 
            if date_cell.value == str(date_str):
                # Column 8 is Status
                ws.update_cell(cell.row, 8, new_status)
    except:
        st.warning("Could not update status. Task might be duplicated or not found.")

def delete_task_from_sheet(task_name, date_obj, time_str):
    """Finds a task by Name + Date + Time and deletes the row."""
    sheet = init_sheets()
    ws = sheet.worksheet("Tasks")
    
    cell_list = ws.findall(task_name)
    
    for cell in cell_list:
        row_num = cell.row
        row_values = ws.row_values(row_num)
        
        try:
            # Columns in sheet are 1-indexed. Date is col 4, StartTime is col 5.
            # Python list is 0-indexed. Date is index 3, StartTime is index 4.
            sheet_date = row_values[3] 
            sheet_time = row_values[4]
            
            if sheet_date == str(date_obj) and sheet_time == str(time_str):
                ws.delete_rows(row_num)
                return True
        except IndexError:
            continue
            
    return False

def add_recurring_schedule(task, cat, loc, start_t, dur, priority, notes, days_selected, weeks_to_plan=4):
    today = get_bd_date()
    new_entries = []
    
    for i in range(weeks_to_plan * 7):
        current_date = today + timedelta(days=i)
        day_name = current_date.strftime("%A")
        
        if day_name in days_selected:
            new_entries.append({
                "Task": task,
                "Category": cat,
                "Location": loc,
                "Date": current_date,
                "StartTime": start_t.strftime("%H:%M"),
                "Duration": dur,
                "Priority": priority,
                "Status": "Pending",
                "Notes": notes
            })
            
    if new_entries:
        bulk_save_entries("Tasks", new_entries)
        return len(new_entries)
    return 0

# --- APP START ---
if 'data_loaded' not in st.session_state:
    with st.spinner("Connecting to Google Drive..."):
        st.session_state.df = load_data("Tasks")
        st.session_state.df_travel = load_data("Travel")
        st.session_state.data_loaded = True

df = st.session_state.df
df_travel = st.session_state.df_travel

# --- SIDEBAR: NEW INPUT FORM ---
with st.sidebar:
    st.header("📝 Create Routine")
    st.caption(f"📅 BD Date: {get_bd_date()}")
    
    is_recurring = st.toggle("🔄 Repeating Task?", value=False)
    
    with st.form("routine_form", clear_on_submit=True):
        st.subheader("Task Details")
        task_name = st.text_input("Task Name", placeholder="e.g., Physics Tuition")
        location = st.text_input("Location", placeholder="e.g., Ghoshnagar")
        category = st.selectbox("Category", ["Tuition", "University", "Club Work", "Study", "Personal"])
        
        st.subheader("Time & Schedule")
        col_t1, col_t2 = st.columns(2)
        start_time = col_t1.time_input("Start Time", time(10, 0))
        duration_mins = col_t2.number_input("Duration (Mins)", min_value=15, value=60, step=15)
        
        days = []
        specific_date = get_bd_date()
        
        if is_recurring:
            st.write("Repeating Days:")
            c1, c2, c3, c4 = st.columns(4)
            if c1.checkbox("Mon"): days.append("Monday")
            if c2.checkbox("Tue"): days.append("Tuesday")
            if c3.checkbox("Wed"): days.append("Wednesday")
            if c4.checkbox("Thu"): days.append("Thursday")
            c5, c6, c7 = st.columns(3)
            if c5.checkbox("Fri"): days.append("Friday")
            if c6.checkbox("Sat"): days.append("Saturday")
            if c7.checkbox("Sun"): days.append("Sunday")
        else:
            specific_date = st.date_input("Date", get_bd_date())
        
        st.subheader("Details")
        priority = st.select_slider("Priority", options=["Low", "Medium", "High"], value="Medium")
        notes = st.text_area("Notes")
        
        submitted = st.form_submit_button("Add to Schedule")
        
        if submitted and task_name:
            with st.spinner("Syncing with Google Cloud..."):
                if is_recurring and days:
                    count = add_recurring_schedule(task_name, category, location, start_time, duration_mins, priority, notes, days)
                    st.success(f"Added {count} recurring tasks!")
                else:
                    new_entry = {
                        "Task": task_name,
                        "Category": category,
                        "Location": location,
                        "Date": specific_date, 
                        "StartTime": start_time.strftime("%H:%M"),
                        "Duration": duration_mins,
                        "Priority": priority,
                        "Status": "Pending",
                        "Notes": notes
                    }
                    save_entry("Tasks", new_entry)
                    st.success("Task Added!")
                
                del st.session_state.data_loaded
                st.rerun()

# --- MAIN DASHBOARD ---
st.title("🚀 My Daily Driver (Cloud)")

if not df.empty:
    tmrw = get_bd_date() + timedelta(days=1)
    tmrw_high = df[(df['Date'] == tmrw) & (df['Priority'] == 'High')].sort_values(by="StartTime")
else:
    tmrw_high = pd.DataFrame()

col_alert1, col_alert2 = st.columns(2)

with col_alert1:
    st.markdown("### 🔮 Tomorrow's Highlight")
    if not tmrw_high.empty:
        next_big = tmrw_high.iloc[0]
        st.error(f"**{next_big['Task']}** @ {next_big['StartTime']}")
        st.caption(f"📍 {next_big['Location']}")
    else:
        st.success("No High Priority tasks tomorrow!")

with col_alert2:
    st.markdown("### 🚗 Travel Tracker (Today)")
    if not df_travel.empty:
        today_travel = df_travel[df_travel['Date'] == get_bd_date()]
        total_km = today_travel['DistanceKM'].sum()
    else:
        total_km = 0
    st.metric("Distance Traveled Today", f"{total_km} km")

st.divider()

# --- TABS ---
tab_timeline, tab_stats, tab_log, tab_manage = st.tabs(["🕒 24-Hour Timeline", "📊 Analytics", "🚗 Travel Log", "🗑️ Manage Tasks"])

# 1. TIMELINE
with tab_timeline:
    selected_date = st.date_input("View Schedule For:", get_bd_date())
    
    if not df.empty:
        daily_tasks = df[df['Date'] == selected_date].sort_values(by="StartTime")
    else:
        daily_tasks = pd.DataFrame()
    
    if daily_tasks.empty:
        st.info("Nothing scheduled for this date.")
    else:
        st.markdown(f"### Agenda for {selected_date.strftime('%A, %d %B')}")
        
        for index, row in daily_tasks.iterrows():
            try:
                start_dt = datetime.strptime(row['StartTime'], "%H:%M")
                end_dt = start_dt + timedelta(minutes=row['Duration'])
                time_str = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"
            except:
                time_str = "Time Error"

            border_color = "red" if row['Priority'] == "High" else "#ddd"
            bg_color = "rgba(255, 0, 0, 0.05)" if row['Priority'] == "High" else "transparent"
            
            with st.container():
                c1, c2, c3 = st.columns([1, 4, 1])
                with c1:
                    st.markdown(f"**{time_str}**")
                
                with c2:
                    st.markdown(f"""
                    <div style="border-left: 5px solid {border_color}; padding-left: 10px; background-color: {bg_color};">
                        <h4 style="margin:0">{row['Task']} <span style="font-size:0.8em; color:gray; font-weight:normal">({row['Category']})</span></h4>
                        <p style="margin:0; font-size:0.95em">📍 <b>{row['Location']}</b></p>
                        <p style="margin-top:4px; font-size:0.85em; font-style:italic; color:#555">📝 {row['Notes']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                with c3:
                    if row['Status'] != "Done":
                        if st.button("Finish", key=f"fin_{index}"):
                            with st.spinner("Updating..."):
                                update_status_in_sheet(row['Task'], row['Date'], "Done")
                                del st.session_state.data_loaded
                                st.rerun()
                    else:
                        st.write("✅")

# 2. ANALYTICS (RESTORED!)
with tab_stats:
    st.subheader("Work Distribution")
    if not df.empty:
        # Pie Chart of Categories
        fig = px.pie(df, names='Category', title='Tasks by Category')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Add data to see stats.")

# 3. TRAVEL LOG
with tab_log:
    st.subheader("Log Your Travel")
    with st.form("travel_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        t_from = c1.text_input("From")
        t_to = c2.text_input("To")
        t_km = c3.number_input("Distance (KM)", step=0.1)
        
        if st.form_submit_button("Log Trip"):
            new_trip = {
                "Date": get_bd_date(),
                "From": t_from,
                "To": t_to,
                "DistanceKM": t_km,
                "Mode": "Commute"
            }
            save_entry("Travel", new_trip)
            del st.session_state.data_loaded
            st.rerun()
            
    if not df_travel.empty:
        st.dataframe(df_travel[df_travel['Date'] == get_bd_date()], hide_index=True)

# 4. MANAGE (DELETE)
with tab_manage:
    st.subheader("Manage Tasks (Delete)")
    
    manage_date = st.date_input("Select Date to Edit:", get_bd_date(), key="manage_date")
    
    if not df.empty:
        tasks_to_edit = df[df['Date'] == manage_date].sort_values(by="StartTime")
        
        if tasks_to_edit.empty:
            st.info("No tasks scheduled for this day.")
        else:
            for index, row in tasks_to_edit.iterrows():
                col_det, col_del = st.columns([4, 1])
                
                with col_det:
                    st.markdown(f"**{row['StartTime']}** — {row['Task']}")
                    st.caption(f"📍 {row['Location']} | 📂 {row['Category']}")
                    if row['Notes']:
                        st.caption(f"📝 {row['Notes']}")
                
                with col_del:
                    if st.button("🗑️ Delete", key=f"del_{index}"):
                        with st.spinner("Deleting from Cloud..."):
                            success = delete_task_from_sheet(row['Task'], row['Date'], row['StartTime'])
                            if success:
                                st.success("Deleted!")
                                del st.session_state.data_loaded
                                st.rerun()
                            else:
                                st.error("Could not find task in sheet.")
                                
    else:
        st.write("Database is empty.")
