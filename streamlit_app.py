
# Import python packages
import streamlit as st
import requests
from snowflake.snowpark.functions import col

# ------------------- UI Header -------------------
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.write("Choose the fruits you want in your custom Smoothie!")

# Name input
name_on_order = st.text_input("Name on Smoothie:")
if name_on_order:
    st.write("The name on your Smoothie will be:", name_on_order)

# ------------------- Snowflake connection -------------------
cnx = st.connection("snowflake")
session = cnx.session()

# Pull both FRUIT_NAME (display) and SEARCH_ON (API key)
sf_df = (
    session.table("smoothies.public.fruit_options")
           .select(col("FRUIT_NAME"), col("SEARCH_ON"))
           .sort(col("FRUIT_NAME"))
)

# Collect once and build lists/mapping using positional access to Row
rows = sf_df.collect()
fruit_display_list = [r[0] for r in rows]  # r[0] == FRUIT_NAME
# Map FRUIT_NAME -> SEARCH_ON (fallback to FRUIT_NAME if SEARCH_ON is None/empty)
fruit_to_searchon = {r[0]: (r[1] if (r[1] is not None and str(r[1]).strip() != "") else r[0]) for r in rows}

# ------------------- Ingredient selector -------------------
ingredients_list = st.multiselect(
    "Choose up to 5 ingredients:",
    fruit_display_list,
    max_selections=5
)

# ------------------- Helpers -------------------
def safe_sql_value(s: str) -> str:
    """Escape single quotes for SQL string literals."""
    if s is None:
        return ""
    return str(s).replace("'", "''")

def fetch_nutrition(api_name: str):
    """Return JSON dict/list from SmoothieFroot; None on error."""
    try:
        url = f"https://my.smoothiefroot.com/api/fruit/{api_name}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Could not load nutrition for '{api_name}'. Error: {e}")
        return None

# ------------------- Main logic -------------------
if ingredients_list:
    # Store what the user selected (readable)
    ingredients_string = " ".join(ingredients_list).strip()

    # Show nutrition for each chosen fruit using SEARCH_ON
    for fruit_chosen in ingredients_list:
        api_name = fruit_to_searchon.get(fruit_chosen, fruit_chosen)
        st.subheader(f"{fruit_chosen} • Nutrition Information")

        data = fetch_nutrition(api_name)
        if data is not None:
            # JSON viewer is robust for nested structures
            st.json(data)

    # Build INSERT (escape to avoid SQL errors with quotes)
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






