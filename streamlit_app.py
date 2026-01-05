
# Import python packages
import streamlit as st
import requests
from snowflake.snowpark.functions import col

# ---------- Streamlit page ----------
st.set_page_config(page_title="Smoothie Bar", page_icon="🥤", layout="centered")
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.write("Choose the fruits you want in your custom Smoothie!")

# ---------- Helper functions ----------
def safe_sql_value(s: str) -> str:
    """
    Escape single quotes for SQL string literals.
    Example: O'Connor -> O''Connor
    """
    if s is None:
        return ""
    return str(s).replace("'", "''")

@st.cache_data(ttl=300)
def load_fruits(session):
    """
    Load FRUIT_NAME and SEARCH_ON from Snowflake once, return:
      - display list (list[str])
      - mapping dict: FRUIT_NAME -> SEARCH_ON (str or None)
    """
    df = (
        session.table("smoothies.public.fruit_options")
               .select(col("FRUIT_NAME"), col("SEARCH_ON"))
               .sort(col("FRUIT_NAME"))
               .collect()
    )
    display_list = []
    mapping = {}
    for row in df:
        fn = row["FRUIT_NAME"]
        so = row["SEARCH_ON"]
        display_list.append(fn)
        mapping[fn] = so
    return display_list, mapping

def fetch_nutrition(api_name: str) -> dict | None:
    """
    Call SmoothieFroot API for a given fruit API name.
    Returns JSON dict or None on error.
    """
    try:
        url = f"https://my.smoothiefroot.com/api/fruit/{api_name}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Could not load nutrition for '{api_name}'. Error: {e}")
        return None

# ---------- Inputs ----------
name_on_order = st.text_input("Name on Smoothie:")
if name_on_order:
    st.write("The name on your Smoothie will be:", name_on_order)

# ---------- Snowflake connection ----------
cnx = st.connection("snowflake")
session = cnx.session()

# Load fruits (cached)
fruit_display_list, fruit_to_searchon = load_fruits(session)

# Ingredient selector
ingredients_list = st.multiselect(
    "Choose up to 5 ingredients:",
    fruit_display_list,
    max_selections=5
)

# ---------- Main logic ----------
if ingredients_list:
    # Build readable string for storage (what the user saw/selected)
    ingredients_string = " ".join(ingredients_list).strip()

    # Show nutrition for each chosen fruit (using SEARCH_ON or fallback)
    for fruit_chosen in ingredients_list:
        # Prefer SEARCH_ON; if missing/None/empty, fallback to FRUIT_NAME
        api_name = fruit_to_searchon.get(fruit_chosen) or fruit_chosen

        st.subheader(f"{fruit_chosen} • Nutrition Information")

        data = fetch_nutrition(api_name)
        if data is not None:
            st.dataframe(data=data, use_container_width=True)

    # Compose INSERT statement (escape values!)
    ingredients_sql = safe_sql_value(ingredients_string)
    name_sql = safe_sql_value(name_on_order or "")

    my_insert_stmt = f"""
        INSERT INTO smoothies.public.orders (INGREDIENTS, NAME_ON_ORDER)
        VALUES ('{ingredients_sql}', '{name_sql}')
    """

    # Submit button
    time_to_insert = st.button("Submit Order")

    if time_to_insert:
        try:
            session.sql(my_insert_stmt).collect()
            st.success("Your Smoothie is ordered!", icon="✅")
        except Exception as e:
            st.error(f"Order submission failed. Error: {e}")





