
import calendar
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client
from streamlit_extras.stylable_container import stylable_container

# ---------- CONFIG ----------

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
JOSH_PASSWORD = st.secrets["JOSH_PASSWORD"]

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "instructor_planning.pkl"

DAY_PANEL_HEIGHT = 185

# ---------- APP ----------

st.set_page_config(layout="wide")

@st.cache_data
def load_data():
    df = pd.read_pickle(DATA_FILE).copy()
    df["Date"] = pd.to_datetime(df["Date"])
    return df

df = load_data()

# ---------- STATE ----------

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

def load_from_db():
    rows = (
        supabase
        .table("schedule_state")
        .select("*")
        .execute()
        .data
    )

    if rows:
        st.session_state.selected = json.loads(
            rows[0]["selected"]
        )
    else:
        st.session_state.selected = {}

def save_to_db():
    (
        supabase
        .table("schedule_state")
        .upsert({
            "id": "current_state",
            "selected": json.dumps(
                st.session_state.selected
            )
        })
        .execute()
    )

if "selected" not in st.session_state:
    load_from_db()


password = st.text_input(
    "Admin Password",
    type="password"
)

st.session_state.is_admin = (
    password in {
        ADMIN_PASSWORD,
        JOSH_PASSWORD
    }
)

# ---------- RULES ----------

def assignment_hours(dt):
    dt = pd.Timestamp(dt)

    if dt.dayofweek < 4:
        return 4

    if dt.dayofweek >= 5:
        return 3

    return 0

def week_key(dt):
    iso = pd.Timestamp(dt).isocalendar()
    return f"{iso.year}-{iso.week}"

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
            total += assignment_hours(d)

    return total

def selected_count(day):
    return sum(
        1
        for k, v in st.session_state.selected.items()
        if v and k.startswith(f"{day}|")
    )

def reliability_color(r):
    return {
        3: "#ff9800",
        4: "#ffeb3b",
        5: "#8bc34a"
    }.get(int(r), "#d9d9d9")

def tile_css(bg):
    return f"""
    button {{
        background:{bg} !important;
        color:black !important;
        border:1px solid #999 !important;
        border-radius:6px !important;
        min-height:28px !important;
        height:28px !important;
        font-size:10px !important;
        padding:2px 6px !important;
        text-align:left !important;
    }}
    """

# ---------- TOGGLE ----------

def toggle(day, instructor, max_hours):

    # Admins only
    if not st.session_state.is_admin:
        st.warning(
            "Admin password required to modify assignments."
        )
        return

    key = f"{day}|{instructor}"

    currently_selected = st.session_state.selected.get(
        key,
        False
    )

    # --------------------
    # Unassign
    # --------------------

    if currently_selected:

        st.session_state.selected[key] = False

        save_to_db()

        st.rerun()

    # --------------------
    # Daily limit
    # --------------------

    if selected_count(day) >= 5:
        return

    current_hours = weekly_hours(
        instructor,
        day
    )

    # --------------------
    # Allow one assignment
    # beyond max_hours
    # Example:
    # 4/7 -> 8/7 allowed
    # 8/7 -> next blocked
    # --------------------

    if current_hours > max_hours:
        return

    # --------------------
    # Assign
    # --------------------

    st.session_state.selected[key] = True

    save_to_db()

    st.rerun()
    
# ---------- MONTH ----------

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

for c, d in zip(
    headers,
    ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
):
    c.markdown(f"**{d}**")

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
                f"**{day.day}** • **{assigned_today}/5**"
            )

            day_rows = month_df[
                month_df["Date"].dt.date == day
            ].copy()

            available_names = set(
                day_rows["Name"]
            )

            assigned_names = set()

            for selection_key, selected in (
                st.session_state.selected.items()
            ):

                if not selected:
                    continue

                d, instructor = (
                    selection_key.split("|", 1)
                )

                if d == str(day):
                    assigned_names.add(
                        instructor
                    )

            display_names = (
                available_names |
                assigned_names
            )

            if not display_names:
                continue

            rows = []

            for instructor in display_names:

                match = day_rows[
                    day_rows["Name"] == instructor
                ]

                if len(match):

                    rows.append(
                        match.iloc[0].to_dict()
                    )

                else:

                    master = (
                        df[
                            df["Name"] == instructor
                        ]
                        .drop_duplicates("Name")
                    )

                    if len(master):

                        info = (
                            master.iloc[0]
                            .to_dict()
                        )

                        info["Date"] = pd.Timestamp(day)

                        rows.append(info)

            display_df = pd.DataFrame(rows)

            if len(display_df) == 0:
                continue

            display_df["selected_sort"] = (
                display_df["Name"]
                .apply(
                    lambda n:
                    st.session_state.selected.get(
                        f"{day}|{n}",
                        False
                    )
                )
            )

            display_df = display_df.sort_values(
                ["selected_sort", "Name"],
                ascending=[False, True]
            )

            with st.container(
                height=DAY_PANEL_HEIGHT
            ):

                for _, row in display_df.iterrows():

                    instructor = row["Name"]
                    reliability = int(
                        row["Reliability"]
                    )
                    max_hours = float(
                        row["max_hours"]
                    )

                    key = (
                        f"{day}|{instructor}"
                    )

                    selected = (
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
                        (not st.session_state.is_admin)
                        or (
                            not selected
                            and (
                                assigned_today >= 5
                                or week_hours > max_hours
                            )
                        )
                        )

                    label = (
                        f"{'✓ ' if selected else ''}"
                        f"{instructor} "
                        f"{week_hours:.0f}/"
                        f"{max_hours:.0f}"
                    )

                    bg = (
                        reliability_color(
                            reliability
                        )
                        if selected
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

# ---------- ASSIGNMENTS ----------

with st.expander("Assignments"):

    rows = []

    for key, selected in (
        st.session_state.selected.items()
    ):

        if selected:

            d, instructor = (
                key.split("|", 1)
            )

            rows.append({
                "Date": d,
                "Instructor": instructor
            })

    if rows:

        st.dataframe(
            pd.DataFrame(rows)
            .sort_values(
                ["Date", "Instructor"]
            ),
            use_container_width=True
        )

# ---------- SAVE ----------

if st.button("Refresh"):
    load_from_db()
    st.rerun()

password = st.text_input(
    "Admin Password",
    type="password"
)

st.session_state.is_admin = (
    password in {
        ADMIN_PASSWORD,
        JOSH_PASSWORD
    }
)

st.caption(
    "Selected instructors appear first. "
    "Weekly totals are shown on every tile. "
    "One assignment beyond max_hours is allowed."
)

# ---------- ADMIN OVERRIDES ----------

if st.session_state.is_admin:

    with st.expander("Admin Overrides"):

        override_day = st.date_input(
            "Date"
        )

        all_instructors = sorted(
            df["Name"].unique()
        )

        assigned = sorted([
            name
            for name in all_instructors
            if st.session_state.selected.get(
                f"{override_day}|{name}",
                False
            )
        ])

        # =====================
        # SWAP
        # =====================

        st.subheader(
            "Swap Instructor"
        )

        if assigned:

            old_name = st.selectbox(
                "Replace",
                assigned,
                key=f"swap_old_{override_day}"
            )

            new_name = st.selectbox(
                "With",
                all_instructors,
                key=f"swap_new_{override_day}"
            )

            if st.button(
                "Swap",
                key=f"swap_btn_{override_day}"
            ):

                st.session_state.selected.pop(
                    f"{override_day}|{old_name}",
                    None
                )

                st.session_state.selected[
                    f"{override_day}|{new_name}"
                ] = True

                save_to_db()

                st.toast(
                    f"Replaced {old_name} "
                    f"with {new_name}"
                )

                st.rerun()

        else:

            st.info(
                "No instructors assigned "
                "on this date."
            )

        st.divider()

        # =====================
        # ADD
        # =====================

        st.subheader(
            "Add Instructor Assignment"
        )

        add_name = st.selectbox(
            "Instructor",
            [
                instructor for instructor
                in all_instructors
                if instructor
                not in assigned
            ],
            key=f"add_name_{override_day}"
        )

        if st.button(
            "Add Assignment",
            key=f"add_btn_{override_day}"
        ):

            assignment_key = (
                f"{override_day}|{add_name}"
            )

            if not st.session_state.selected.get(
                assignment_key,
                False
            ):

                st.session_state.selected[
                    assignment_key
                ] = True

                save_to_db()

                st.toast(
                    f"Added {add_name}"
                )

                st.rerun()

        st.divider()

        # =====================
        # REMOVE
        # =====================

        st.subheader(
            "Remove Instructor Assignment"
        )

        if assigned:

            remove_name = st.selectbox(
                "Assigned Instructor",
                assigned,
                key=f"remove_name_{override_day}"
            )

            if st.button(
                "Remove Assignment",
                key=f"remove_btn_{override_day}"
            ):

                st.session_state.selected.pop(
                    f"{override_day}|{remove_name}",
                    None
                )

                save_to_db()

                st.toast(
                    f"Removed {remove_name}"
                )

                st.rerun()