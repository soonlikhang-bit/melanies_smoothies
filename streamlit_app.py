
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

# 3) Apply search mappings so SEARCH_ON matches the API's expected spellings (singulars)
#    If your FRUIT_NAME values are plural in the UI (Apples, Blueberries, etc.),
#    this mapping will set SEARCH_ON to the singular form for API calls.
search_mappings = {
    'Apples': 'Apple',
    'Blueberries': 'Blueberry',
    'Raspberries': 'Raspberry',
    'Strawberries': 'Strawberry',
    'Jack Fruit': 'Jackfruit',   # API often uses 'Jackfruit' without a space
    # Add other special cases here if needed, e.g., 'Dragon Fruit': 'Dragon Fruit' (no change)
}

for label_value, api_term in search_mappings.items():
    label_safe = label_value.replace("'", "''")
    api_safe = api_term.replace("'", "''")
    session.sql(f"""
        UPDATE smoothies.public.fruit_options
        SET SEARCH_ON = '{api_safe}'
        WHERE FRUIT_NAME = '{label_safe}'
    """).collect()

# -----------------------------
# Load fruit options
# -----------------------------
snow_df = session.table("smoothies.public.fruit_options").select(
    col("FRUIT_NAME"), col("SEARCH_ON")
)

# Convert to Pandas
pd_df: pd.DataFrame = snow_df.to_pandas()

# Optional: show what's in the table (helps verify singular vs plural)
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
        # Use Pandas .loc to fetch SEARCH_ON term for the chosen label
        row_match = pd_df.loc[pd_df["FRUIT_NAME"] == fruit_label, "SEARCH_ON"]
        if not row_match.empty:
            search_on = str(row_match.iloc[0])
        else:
            search_on = fruit_label  # fallback

        # Helper line (should now show singulars for plural labels)
        st.write(f"The search value for {fruit_label} is {search_on}.")

        st.subheader(f"{fruit_label} Nutrition Information")
        try:
            response = requests.get(
                f"https://my.smoothiefroot.com/api/fruit/{search_on}",
            )
            if response.ok:
                st.dataframe(response.json(), use_container_width=True)
            else:
                st.warning(
                    f"Could not fetch info for '{fruit_label}' (searched as '{search_on}'). "
                    f"Status: {response.status_code}"
                )
        except Exception as e:
            st.error(f"Error fetching data for '{fruit_label}': {e}")

    # Prepare INSERT statement safely
    safe_ingredients = ingredients_string.replace("'", "''")
    safe_name = (name_on_order or "").replace("'", "''")

    my_insert_stmt = f"""
        INSERT INTO smoothies.public.orders (INGREDIENTS, NAME_ON_ORDER)
        VALUES ('{safe_ingredients}', '{safe_name}')
    """

    if st.button("Submit Order"):
        try:
            session.sql(my_insert_stmt).collect()
            st.success("Your Smoothie is ordered!", icon="✅")
        except Exception as e:
            st.error(f"Order submission failed: {e}")



