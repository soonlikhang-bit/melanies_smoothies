
# Import packages
import streamlit as st
import requests
import pandas as pd
import re
import unicodedata
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

# Ensure SEARCH_ON column exists and is seeded
session.sql("""
    ALTER TABLE IF EXISTS smoothies.public.fruit_options
    ADD COLUMN IF NOT EXISTS SEARCH_ON STRING
""").collect()

session.sql("""
    UPDATE smoothies.public.fruit_options
    SET SEARCH_ON = FRUIT_NAME
    WHERE SEARCH_ON IS NULL
""").collect()

# Apply mappings for API search terms
search_mappings = {
    'Apples': 'Apple',
    'Blueberries': 'Blueberry',
    'Cantaloupe': 'Cantaloupe',
    'Dragon Fruit': 'Dragonfruit',
    'Elderberries': 'Elderberry',
    'Figs': 'Figs',
    'Guava': 'Guava',
    'Honeydew': 'Honeydew',
    'Jackfruit': 'Jackfruit',
    'Kiwi': 'Kiwi',
    'Lime': 'Lime',
    'Mango': 'Mango',
    'Nectarine': 'Nectarine',
    'Orange': 'Orange',
    'Papaya': 'Papaya',
    'Quince': 'Quince',
    'Raspberries': 'Raspberry',
    'Strawberries': 'Strawberry',
    'Tangerine': 'Tangerine',
    'Ugli Fruit': 'Ugli Fruit (Jamaican Tangelo)',
    'Vanilla Fruit': 'Vanilla Fruit',
    'Watermelon': 'Watermelon',
    'Ximenia': 'Ximenia (Hog Plum)',
    'Yerba Mate': 'Yerba Mate',
    'Ziziphus Jujube': 'Ziziphus Jujube',
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
pd_df: pd.DataFrame = snow_df.to_pandas()
st.dataframe(pd_df, use_container_width=True)

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
# Normalization helper
# -----------------------------
def normalize_text(s: str) -> str:
    # Normalize Unicode
    s = unicodedata.normalize('NFC', s)
    # Replace non-breaking spaces and zero-width spaces
    s = s.replace('\u00A0', ' ').replace('\u200B', '').replace('\u200D', '')
    # Collapse multiple spaces
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

# -----------------------------
# Handle selection
# -----------------------------
if ingredients_list:
    # Build normalized ingredient string
    display_ingredients = " ".join(ingredients_list)
    canonical_ingredients = normalize_text(display_ingredients)

    # Debug info
    st.write(f"Ingredients (normalized): {canonical_ingredients}")
    st.write(f"UTF-8 HEX: {canonical_ingredients.encode('utf-8').hex()}")
    st.write(f"Char LEN: {len(canonical_ingredients)}")

    # Show nutrition info
    for fruit_label in ingredients_list:
        row_match = pd_df.loc[pd_df["FRUIT_NAME"] == fruit_label, "SEARCH_ON"]
        search_on = str(row_match.iloc[0]) if not row_match.empty else fruit_label
        st.subheader(f"{fruit_label} Nutrition Information")
        try:
            response = requests.get(f"https://my.smoothiefroot.com/api/fruit/{search_on}")
            if response.ok:
                st.dataframe(response.json(), use_container_width=True)
            else:
                st.warning(f"Could not fetch info for '{fruit_label}' (searched as '{search_on}'). Status: {response.status_code}")
        except Exception as e:
            st.error(f"Error fetching data for '{fruit_label}': {e}")

    # Prepare safe SQL insert
    safe_display = display_ingredients.replace("'", "''")
    safe_canon = canonical_ingredients.replace("'", "''")
    safe_name = (name_on_order or "").replace("'", "''")

    my_insert_stmt = f"""
        INSERT INTO smoothies.public.orders (INGREDIENTS, INGREDIENTS_CANON, NAME_ON_ORDER)
        VALUES ('{safe_display}', '{safe_canon}', '{safe_name}')
    """

    if st.button("Submit Order"):
        try:
            session.sql(my_insert_stmt).collect()
            st.success("Your Smoothie is ordered!", icon="✅")
        except Exception as e:
            st.error(f"Order submission failed: {e}")




