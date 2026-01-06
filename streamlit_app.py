
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

# -----------------------------
# Snowflake connection & setup
# -----------------------------
cnx = st.connection("snowflake")
session = cnx.session()

# 1) Add SEARCH_ON column if it doesn't exist
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

# 3) Apply requested specific mappings
mappings = {
    'Apple': 'Apples',
    'Blueberry': 'Blueberries',
    'Jackfruit': 'Jack Fruit',
    'Raspberry': 'Raspberries',
    'Strawberry': 'Strawberries',
}

for src, dst in mappings.items():
    src_safe = src.replace("'", "''")
    dst_safe = dst.replace("'", "''")
    session.sql(f"""
        UPDATE smoothies.public.fruit_options
        SET SEARCH_ON = '{dst_safe}'
        WHERE FRUIT_NAME = '{src_safe}'
    """).collect()

# -----------------------------
# Load fruit options
# -----------------------------
snow_df = session.table("smoothies.public.fruit_options").select(
    col("FRUIT_NAME"), col("SEARCH_ON")
)

# Convert to Pandas
pd_df: pd.DataFrame = snow_df.to_pandas()

# Show DataFrame for verification (optional)
st.dataframe(pd_df, use_container_width=True)

# Build UI labels
fruit_labels = pd_df["FRUIT_NAME"].tolist()

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
        # ✅ Use .loc and .iloc[0] to get SEARCH_ON value
        search_on = pd_df.loc[pd_df['FRUIT_NAME'] == fruit_label, 'SEARCH_ON'].iloc[0]

        # Show helper line
        st.write(f"The search value for {fruit_label} is {search_on}.")

        # Show nutrition info
        st.subheader(f"{fruit_label} Nutrition Information")
        try:
            response = requests.get(
                f"https://my.smoothiefroot.com/api/fruit/{search_on}",
                timeout=15,
            )
            if response.ok:
                st.dataframe(response.json(), use_container_width=True)
            else:
                st.warning(f"Could not fetch info for '{fruit_label}' (searched as '{search_on}').")
        except Exception as e:
            st.error(f"Error fetching data for '{fruit_label}': {e}")

    # Prepare INSERT statement safely
    safe_ingredients = ingredients_string.replace("'", "''")
    safe_name = (name_on_order or "").replace("'", "''")

    my_insert_stmt = f"""
        INSERT INTO smoothies.public.orders (INGREDIENTS, NAME_ON_ORDER)
        VALUES ('{safe_ingredients}', '{safe_name}')
    """

    # Submit button
    if st.button("Submit Order"):
        try:
            session.sql(my_insert_stmt).collect()
            st.success("Your Smoothie is ordered!", icon="✅")
        except Exception as e:
            st.error(f"Order submission failed: {e}")


