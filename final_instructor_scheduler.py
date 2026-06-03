
import calendar
import json
from pathlib import Path

import pandas as pd
import numpy as np
import streamlit as st
from supabase import create_client


from streamlit_extras.stylable_container import stylable_container

# ---------- CONFIG ----------
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)


#DATA_FILE = "instructor_planning.pkl"  # rename your uploaded file to this
#STATE_FILE = "schedule_selections.json"

BASE_DIR = Path(__file__).parent

STATE_FILE = BASE_DIR.parent / "schedule_selections.json"
DATA_FILE = BASE_DIR / "instructor_planning.pkl"

VISIBLE_INSTRUCTORS = 5
DAY_PANEL_HEIGHT = 185

# ---------- APP ----------

st.set_page_config(layout="wide")

@st.cache_data
def load_data():
    df = pd.read_pickle(DATA_FILE).copy()
    df["Date"] = pd.to_datetime(df["Date"])
    return df

df = load_data()

def load_state():
    p = Path(STATE_FILE)
    if p.exists():
        return json.loads(p.read_text())
    return {}

def save_state():
    Path(STATE_FILE).write_text(json.dumps(st.session_state.selected))

def format_for_save():
    return [
        {
            'Date': k.split('|')[0],
            'Name': k.split('|')[1],
            'Active': v
        }
        for k, v in st.session_state.selected.items()
    ]


def save_to_db():
    (
        supabase
        .table('schedule_state')
    #    .upsert(format_for_save())
        .insert({
            'id': 'current_state',
            'selected': json.dumps(st.session_state.selected)
        })
        .execute()
    )


#if "selected" not in st.session_state:
if not hasattr(st.session_state, 'selected'):
    st.session_state.selected = load_state()

# ---------- RULES ----------
# test
def assignment_hours(dt):
    dt = pd.Timestamp(dt)
    
    # Mon-Thu = 4 hours
    if dt.dayofweek:
        return 4

    # Sat-Sun = 3 hours
    if dt.dayofweek >= 5:
        return 3

    # Friday = 0
    return 0

def week_key(dt):
    iso = pd.Timestamp(dt).isocalendar()
    return f"{iso.year}-{iso.week + (iso.weekday == 7)}"

def weekly_hours(name, day):
    wk = week_key(day)
    total = 0

    for key, selected in st.session_state.selected.items():
        if not selected:
            continue

        d, instructor = key.split("|", 1)

        if instructor != name:
            continue

        if week_key(pd.to_datetime(d)) == wk:
            total += assignment_hours(pd.to_datetime(d))

    return total

def selected_count(day):
    return sum(
        1
        for key, selected in st.session_state.selected.items()
        if selected and key.startswith(str(day) + "|")
    )

def reliability_color(reliability):
    return {
        3: "#ff9800",  # orange
        4: "#ffeb3b",  # yellow
        5: "#8bc34a",  # green
    }.get(int(reliability), "#d3d3d3")

def tile_css(bg):
    return f"""
    button {{
        background: {bg} !important;
        color: black !important;
        border: 1px solid #999 !important;
        border-radius: 6px !important;
        min-height: 28px !important;
        height: 28px !important;
        padding: 2px 6px !important;
        font-size: 10px !important;
        text-align: left !important;
        margin-bottom: 2px !important;
    }}
    """

# ---------- TOGGLE ----------

def toggle(day, instructor, max_hours):

    key = f"{day}|{instructor}"

    currently_selected = st.session_state.selected.get(
        key,
        False
    )

    if currently_selected:
        st.session_state.selected[key] = False
        save_state()
        st.rerun()

    # 5 instructors max per day
    if selected_count(day) >= 5:
        return

    current_hours = weekly_hours(
        instructor,
        day
    )

    # allow crossing max once
    if current_hours >= max_hours:
        return

    st.session_state.selected[key] = True

    save_state()
    st.rerun()

# ---------- MONTH PICKER ----------

months = sorted(
    df["Date"].dt.to_period("M").unique()
)

month = st.selectbox(
    "Month",
    months,
    format_func=lambda p: p.strftime("%B %Y")
)

month_df = df[
    df["Date"].dt.to_period("M") == month
]

st.title(
    f"Instructor Scheduler — {month.strftime('%B %Y')}"
)

# ---------- HEADERS ----------

headers = st.columns(7)

for c, day_name in zip(
    headers,
    ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
):
    c.markdown(f"**{day_name}**")

cal = calendar.Calendar(firstweekday=6)

# ---------- CALENDAR ----------

for week in cal.monthdatescalendar(
    month.year,
    month.month
):

    cols = st.columns(7)

    for col, day in zip(cols, week):

        with col:

            if day.month != month.month:
                st.empty()
                continue

            assigned_today = selected_count(day)

            st.markdown(
                f"**{day.day}**  •  "
                f"**{assigned_today}/5**"
            )

            day_rows = month_df[
                month_df["Date"].dt.date == day
            ].copy()

            if len(day_rows) == 0:
                continue

            day_rows["selected_sort"] = (
                day_rows["Name"]
                .apply(
                    lambda n:
                    st.session_state.selected.get(
                        f"{day}|{n}",
                        False
                    )
                )
            )

            day_rows = day_rows.sort_values(
                ["selected_sort", "Name"],
                ascending=[False, True]
            )

            with st.container(height=DAY_PANEL_HEIGHT):

                for _, row in day_rows.iterrows():

                    instructor = row["Name"]
                    reliability = int(row["Reliability"])
                    max_hours = float(row["max_hours"])

                    key = f"{day}|{instructor}"

                    is_selected = (
                        st.session_state.selected.get(
                            key,
                            False
                        )
                    )

                    week_hours = weekly_hours(
                        instructor,
                        day
                    )

                    disabled = (
                        not is_selected
                        and (
                            assigned_today >= 5
                            or week_hours >= max_hours
                        )
                    )

                    label = (
                        f"{'✓ ' if is_selected else ''}"
                        f"{instructor}  "
                        f"{week_hours:.0f}/{max_hours:.0f}"
                    )

                    bg = (
                        reliability_color(reliability)
                        if is_selected
                        else "#d9d9d9"
                    )

                    with stylable_container(
                        key=f"tile_{key}",
                        css_styles=tile_css(bg)
                    ):
                        if st.button(
                            label,
                            key=f"btn_{key}",
                            disabled=disabled,
                            use_container_width=True
                        ):
                            toggle(
                                day,
                                instructor,
                                max_hours
                            )

with st.expander("Assignments"):

    records = []

    for key, selected in (
        st.session_state.selected.items()
    ):
        if selected:
            d, instructor = key.split("|", 1)

            records.append({
                "Date": d,
                "Instructor": instructor
            })

    if records:
        st.dataframe(
            pd.DataFrame(records)
            .sort_values(
                ["Date", "Instructor"]
            ),
            use_container_width=True
        )

if st.button('Save'):
    save_to_db()

st.caption(
    "Selected instructors appear first. "
    "Panels show ~5 instructors before scrolling. "
    "Weekly totals are displayed on every card in the week. "
    "A selection may exceed max_hours, but once an instructor "
    "is at or above max_hours, further assignments are blocked."
)
