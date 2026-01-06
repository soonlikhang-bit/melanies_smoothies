

# Import python packages
import streamlit as st
import requests
import pandas as pd
from snowflake.snowpark.functions import col

# -----------------------------
# App Header
# -----------------------------
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.write("Choose the fruits you want in your custom Smoothie!")

name_on_order = st.text_input("Name on Smoothie:")
st.write("The name on your Smoothie will be:", name_on_order)

# Optional: enable a "show DataFrame & pause" view like the lab screenshot
debug_mode = st.checkbox("Show fruit options (Pandas) and pause (debug)", value=False)

# -----------------------------
# Snowflake connection & setup
# -----------------------------
cnx = st.connection("snowflake")
session = cnx.session()

# 1) Add SEARCH_ON column if it doesn't exist (single statement per call)
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.fruit_options
    ADD COLUMN IF NOT EXISTS SEARCH_ON STRING
""").collect()

# 2) Seed SEARCH_ON = FRUIT_NAME where SEARCH_ON is NULL
session.sql("""
    UPDATE smoothies.public.fruit_options
    SET SEARCH_ON = FRUIT_NAME
    WHERE SEARCH_ON IS NULL
""").collect()

# 3) Apply requested specific mappings (run each UPDATE as its own statement)
mappings = {
    "Apple": "Apples",
    "Blueberry": "Blueberries",
    "Jackfruit": "Jack Fruit",
    "Raspberry": "Raspberries",
    "Strawberry": "Strawberries",
}

for src, dst in mappings.items():
    # Escape single quotes just in case (defensive)
    src_safe = src.replace("'", "''")
    dst_safe = dst.replace("'", "''")
    session.sql(f"""
        UPDATE smoothies.public.fruit_options
        SET SEARCH_ON = '{dst_safe}'
        WHERE FRUIT_NAME = '{src_safe}'
    """).collect()

# -----------------------------
# Load fruit options (label + search key)
# -----------------------------
# Snowpark DataFrame with both columns
snow_df = session.table("smoothies.public.fruit_options").select(
    col("FRUIT_NAME"), col("SEARCH_ON")
)

# Convert to Pandas for display & for building Python lists/dicts
pd_df: pd.DataFrame = snow_df.to_pandas()

# Debug view like the attachment (uses Pandas)
if debug_mode:
    st.dataframe(pd_df, use_container_width=True)
    st.info("Debug mode is ON. Turn it off to continue the app.")
    st.stop()  # Pause just like the lab screenshot

# Build UI labels and API lookup dict
fruit_labels = pd_df["FRUIT_NAME"].tolist()
label_to_search = dict(zip(pd_df["FRUIT_NAME"], pd_df["SEARCH_ON"]))

# -----------------------------
# Ingredient picker
# -----------------------------
ingredients_list = st.multiselect(
    "Choose up to 5 ingredients:",
    fruit_labels,
    max_selections=5,
)

# -----------------------------
# Handle selection, show nutrition, and submit order
# -----------------------------
if ingredients_list:
    ingredients_string = " ".join(ingredients_list)

    for fruit_label in ingredients_list:
        search_term = label_to_search.get(fruit_label, fruit_label)

        st.subheader(f"{fruit_label} Nutrition Information")
        try:
            smoothiefroot_response = requests.get(
                f"https://my.smoothiefroot.com/api/fruit/{search_term}",
                timeout=15,
            )
            if smoothiefroot_response.ok:
                st.dataframe(
                    data=smoothiefroot_response.json(),
                    use_container_width=True,
                )
            else:
                st.warning(
                    f"Could not fetch nutrition info for '{fruit_label}' "
                    f"(searched as '{search_term}'). Status: {smoothiefroot_response.status_code}"
                )
        except Exception as e:
            st.error(f"Error fetching data for '{fruit_label}' (searched as '{search_term}'): {e}")

    # Prepare INSERT statement safely
    safe_ingredients = ingredients_string.replace("'", "''")
    safe_name = (name_on_order or "").replace("'", "''")

    my_insert_stmt = f"""
        INSERT INTO smoothies.public.orders (INGREDIENTS, NAME_ON_ORDER)
        VALUES ('{safe_ingredients}', '{safe_name}')
    """

    time_to_insert = st.button("Submit Order")

    if time_to_insert:
        try:
            session.sql(my_insert_stmt).collect()
            st.success("Your Smoothie is ordered!", icon="✅")
        except Exception as e:
            st.error(f"Order submission failed: {e}")
