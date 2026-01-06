
# Import python packages
import streamlit as st
import requests
from snowflake.snowpark.functions import col

# -----------------------------
# App Header
# -----------------------------
st.title(":cup_with_straw: Customize Your Smoothie! :cup_with_straw:")
st.write(
    """Choose the fruits you want in your custom Smoothie!"""
)

name_on_order = st.text_input("Name on Smoothie:")
st.write("The name on your Smoothie will be:", name_on_order)

# -----------------------------
# Snowflake connection & setup
# -----------------------------
cnx = st.connection("snowflake")
session = cnx.session()

# Ensure the SEARCH_ON column exists and is correctly populated
# 1) Add column if it doesn't exist
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
#    Apple -> Apples, Blueberry -> Blueberries, Jackfruit -> Jack Fruit,
#    Raspberry -> Raspberries, Strawberry -> Strawberries
session.sql("""
    UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Apples'      WHERE FRUIT_NAME = 'Apple';
    UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Blueberries' WHERE FRUIT_NAME = 'Blueberry';
    UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Jack Fruit'  WHERE FRUIT_NAME = 'Jackfruit';
    UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Raspberries' WHERE FRUIT_NAME = 'Raspberry';
    UPDATE smoothies.public.fruit_options SET SEARCH_ON = 'Strawberries'WHERE FRUIT_NAME = 'Strawberry';
""").collect()

# -----------------------------
# Load fruit options (both label and search key)
# -----------------------------
# Keep FRUIT_NAME for display; use SEARCH_ON for API lookups
options_df = session.table("smoothies.public.fruit_options").select(
    col("FRUIT_NAME"), col("SEARCH_ON")
).collect()  # returns a list of Row; easy to convert to Python structures

# Build helper structures for Streamlit multiselect and lookups
fruit_labels = [row["FRUIT_NAME"] for row in options_df]  # display names
label_to_search = {row["FRUIT_NAME"]: row["SEARCH_ON"] for row in options_df}  # lookup

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
    # Prepare a space-separated list for the order record (use labels)
    ingredients_string = " ".join(ingredients_list)

    for fruit_label in ingredients_list:
        # Get the API search term from SEARCH_ON
        search_term = label_to_search.get(fruit_label, fruit_label)

        st.subheader(f"{fruit_label} Nutrition Information")
        # Use SEARCH_ON in the API call to match SmoothieFroot spellings
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

    # Prepare INSERT statement safely (escape single quotes)
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







